import base64
import json

from app.telephony.events import AudioChunk, CallEnded, CallStarted, TelephonyEvent, UnknownEvent
from app.telephony.providers.base import TelephonyAdapter, TransferResult


class MockTelephonyAdapter(TelephonyAdapter):
    """A small, self-contained JSON protocol used for local development and
    tests when no real Twilio/Vapi connection is available. It intentionally
    mirrors the shape real providers use (base64-encoded payload inside a
    JSON envelope over a text websocket frame) so tests exercise the same
    encode/decode path a real adapter would.

    Wire format (each message is one JSON object):
      {"event": "start", "call_id": "...", "from": "...", "to": "..."}
      {"event": "media", "call_id": "...", "payload": "<base64>"}
      {"event": "stop", "call_id": "..."}

    Since there's no real audio in mock mode, `payload` base64-encodes the
    UTF-8 text of what the caller "said" — see MockSTTProvider, which
    decodes it straight back into a transcript.
    """

    name = "mock"

    def __init__(self) -> None:
        # Records every attempted transfer_call() so tests can assert on it
        # without needing a real Twilio/Vapi account.
        self.transfers: list[dict] = []

    def is_available(self) -> bool:
        return True

    def parse_message(self, raw: str | bytes) -> TelephonyEvent:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            payload = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return UnknownEvent(raw=raw)

        event = payload.get("event")
        if event == "start":
            return CallStarted(
                call_id=payload["call_id"],
                from_number=payload.get("from"),
                to_number=payload.get("to"),
                sample_rate=payload.get("sample_rate", 8000),
                provider_call_id=payload.get("call_sid"),
            )
        if event == "media":
            try:
                audio = base64.b64decode(payload["payload"])
            except Exception:
                return UnknownEvent(raw=raw)
            return AudioChunk(call_id=payload["call_id"], payload=audio)
        if event == "stop":
            return CallEnded(call_id=payload["call_id"])
        return UnknownEvent(raw=raw)

    def encode_audio_message(self, call_id: str, audio: bytes) -> str:
        return json.dumps(
            {"event": "media_out", "call_id": call_id, "payload": base64.b64encode(audio).decode("ascii")}
        )

    def encode_clear_message(self, call_id: str) -> str:
        return json.dumps({"event": "clear", "call_id": call_id})

    def supports_live_transfer(self) -> bool:
        return True

    def transfer_call(self, provider_call_id: str, target_number: str) -> TransferResult:
        self.transfers.append({"provider_call_id": provider_call_id, "target_number": target_number})
        return TransferResult(success=True)
