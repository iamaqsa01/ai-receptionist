import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.ai.receptionist_service import ReceptionistService
from app.ai.speech.stt.factory import get_stt_provider
from app.ai.speech.tts.factory import get_tts_provider
from app.core.config import settings
from app.core.rate_limit import rate_limit, telephony_webhook_rate_limiter
from app.database.session import get_db
from app.models.workspace import Workspace
from app.telephony.providers.factory import get_telephony_adapter
from app.telephony.providers.twilio_adapter import TwilioAdapter, build_stream_twiml
from app.telephony.session import CallSession
from app.telephony.stream_token import create_stream_token, verify_stream_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telephony", tags=["telephony"])


def _twilio_signature_enforced() -> bool:
    return settings.telephony_provider.lower().strip() == "twilio" and bool(settings.twilio_auth_token)


@router.post("/twilio/{workspace_id}/voice")
async def twilio_voice_webhook(
    workspace_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(telephony_webhook_rate_limiter)),
) -> Response:
    """Twilio's initial HTTP webhook for an inbound call. Returns TwiML
    instructing Twilio to open a Media Stream to our WebSocket endpoint,
    which is where the actual audio pipeline (this file's `stream`
    endpoint) takes over."""
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    form = await request.form()
    form_fields = {key: str(value) for key, value in form.items()}

    # Phase 14: reject a request that doesn't carry a valid X-Twilio-Signature
    # — without this, anyone who knows (or guesses) a workspace_id could hit
    # this endpoint directly and be handed a live Media Stream URL, driving
    # up STT/TTS/LLM costs and interacting with the AI Receptionist as if
    # they were a real caller. Only enforced when Twilio is actually the
    # configured provider (mock/dev environments never send a real
    # signature and aren't reachable from the public internet in the first
    # place). `request.url` reflects Twilio's actual request URL only if
    # any reverse proxy in front of this app forwards the original
    # scheme/host (e.g. Starlette's ProxyHeadersMiddleware, or equivalent).
    if _twilio_signature_enforced():
        adapter = TwilioAdapter(settings.twilio_account_sid, settings.twilio_auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not adapter.verify_webhook_signature(str(request.url), form_fields, signature):
            logger.warning("workspace_id=%s rejected Twilio voice webhook: invalid or missing signature", workspace_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    from_number = form_fields.get("From", "")
    to_number = form_fields.get("To", "")

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    stream_path = f"{settings.api_v1_prefix}/telephony/stream/twilio/{workspace_id}"
    # Only appended when signature verification is actually enforced above
    # (see telephony_stream) — a token minted with no real signature check
    # behind it would be theater, not protection.
    if _twilio_signature_enforced():
        stream_path += f"?token={create_stream_token(workspace_id)}"
    websocket_url = f"{ws_scheme}://{request.url.netloc}{stream_path}"

    twiml = build_stream_twiml(websocket_url, from_number, to_number)
    logger.info("workspace_id=%s inbound Twilio call webhook from=%s to=%s", workspace_id, from_number, to_number)
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/stream/{provider}/{workspace_id}")
async def telephony_stream(
    websocket: WebSocket, provider: str, workspace_id: uuid.UUID, db: Session = Depends(get_db)
) -> None:
    """The real-time voice pipeline's WebSocket endpoint: caller audio in,
    AI Receptionist audio out. One connection = one call. `provider`
    selects the wire protocol (twilio/vapi/mock); `workspace_id` selects
    which clinic's AI Receptionist handles the call (in production this
    would be resolved from the called phone number — that mapping is out
    of this phase's scope, so it's passed explicitly here).

    Not authenticated the way a staff-facing endpoint is: real callers
    never log in. workspace_id existence is still validated below, and —
    when Twilio is the configured provider — so is a short-lived token
    minted by the voice webhook only after it verified Twilio's own
    request signature (app.telephony.stream_token), closing the gap where
    anyone who learned a workspace_id could otherwise connect here
    directly and drive the AI Receptionist as if they were a real caller.
    """
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown workspace")
        return

    if provider.lower().strip() == "twilio" and _twilio_signature_enforced():
        token = websocket.query_params.get("token", "")
        if not verify_stream_token(token, workspace_id):
            logger.warning("workspace_id=%s rejected telephony stream connection: invalid or missing token", workspace_id)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
            return

    await websocket.accept()

    adapter = get_telephony_adapter(provider)
    stt = get_stt_provider()
    tts = get_tts_provider()
    receptionist = ReceptionistService(db=db)

    session = CallSession(
        workspace_id=workspace_id,
        adapter=adapter,
        stt=stt,
        tts=tts,
        receptionist=receptionist,
        send=websocket.send_text,
    )

    logger.info(
        "workspace_id=%s telephony websocket connected (provider=%s adapter=%s stt=%s tts=%s)",
        workspace_id,
        provider,
        adapter.name,
        stt.name,
        tts.name,
    )

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=settings.call_idle_timeout_seconds
                )
            except asyncio.TimeoutError:
                should_close = await session.handle_idle_timeout()
                if should_close:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE, reason="Idle timeout")
                    break
                continue

            await session.handle_raw_message(raw)
    except WebSocketDisconnect:
        logger.info("call_id=%s caller disconnected", session.call_id)
    except Exception:
        logger.exception("call_id=%s telephony stream failed unexpectedly", session.call_id)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        await session.close()
