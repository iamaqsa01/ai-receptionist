import base64
import hashlib
import hmac
import json
from xml.sax.saxutils import quoteattr

import httpx

from app.telephony.events import AudioChunk, CallEnded, CallStarted, TelephonyEvent, UnknownEvent
from app.telephony.providers.base import TelephonyAdapter, TransferResult


class TwilioAdapter(TelephonyAdapter):
    """Twilio Media Streams (wss://.../telephony/twilio/{workspace_id}).

    Written against Twilio's documented Media Streams message shapes:
      {"event": "start", "start": {"streamSid", "callSid", "mediaFormat":
        {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
        "customParameters": {...}}, "streamSid": "..."}
      {"event": "media", "media": {"payload": "<base64 mulaw>"}, "streamSid": "..."}
      {"event": "stop", "streamSid": "..."}

    `streamSid` is used as the canonical call_id: unlike callSid, it is
    present on every message type for this connection. Caller/callee phone
    numbers arrive via TwiML `<Parameter>` custom parameters (see
    `build_stream_twiml`), since Twilio doesn't include them on `start`
    by default.

    Audio stays mulaw @ 8kHz end-to-end in both directions — that's Twilio's
    native format, and both Deepgram and ElevenLabs support it directly for
    telephony use cases, so no resampling/transcoding is needed on either
    side of this adapter.
    """

    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token

    def is_available(self) -> bool:
        return bool(self._account_sid and self._auth_token)

    def parse_message(self, raw: str | bytes) -> TelephonyEvent:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            payload = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return UnknownEvent(raw=raw)

        event = payload.get("event")

        if event == "start":
            start = payload.get("start", {})
            media_format = start.get("mediaFormat", {})
            custom_params = start.get("customParameters", {}) or {}
            call_id = payload.get("streamSid") or start.get("streamSid")
            if not call_id:
                return UnknownEvent(raw=raw)
            return CallStarted(
                call_id=call_id,
                from_number=custom_params.get("From"),
                to_number=custom_params.get("To"),
                sample_rate=int(media_format.get("sampleRate", 8000)),
                # Distinct from streamSid (call_id above) — this is what a
                # live-transfer REST call to Twilio needs (see transfer_call).
                provider_call_id=start.get("callSid"),
            )

        if event == "media":
            call_id = payload.get("streamSid")
            b64_payload = payload.get("media", {}).get("payload")
            if not call_id or not b64_payload:
                return UnknownEvent(raw=raw)
            try:
                audio = base64.b64decode(b64_payload)
            except Exception:
                return UnknownEvent(raw=raw)
            return AudioChunk(call_id=call_id, payload=audio)

        if event == "stop":
            call_id = payload.get("streamSid")
            if not call_id:
                return UnknownEvent(raw=raw)
            return CallEnded(call_id=call_id)

        # "connected" and "mark" events (and anything else) are acknowledged
        # but don't drive the call-session state machine.
        return UnknownEvent(raw=raw)

    def encode_audio_message(self, call_id: str, audio: bytes) -> str:
        return json.dumps(
            {
                "event": "media",
                "streamSid": call_id,
                "media": {"payload": base64.b64encode(audio).decode("ascii")},
            }
        )

    def encode_clear_message(self, call_id: str) -> str:
        # Twilio's documented mechanism for interrupting in-flight playback
        # (e.g. on caller barge-in).
        return json.dumps({"event": "clear", "streamSid": call_id})

    def verify_webhook_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        """Validates X-Twilio-Signature on the initial HTTP voice webhook,
        per Twilio's documented algorithm: base64(HMAC-SHA1(auth_token,
        url + sorted "key value" pairs concatenated))."""
        if not self._auth_token:
            return False
        data = url
        for key in sorted(params.keys()):
            data += key + params[key]
        expected = base64.b64encode(
            hmac.new(self._auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    def supports_live_transfer(self) -> bool:
        return self.is_available()

    def transfer_call(self, provider_call_id: str, target_number: str) -> TransferResult:
        """Redirects the *live* call (by CallSid) to a new TwiML `<Dial>`,
        per Twilio's documented "update a live call" REST API
        (`POST /Calls/{Sid}.json`) — this is what actually pulls the caller
        off the AI's Media Stream and rings the human number. Not exercised
        against a live Twilio account in this environment (no credentials
        available)."""
        if not self.is_available():
            return TransferResult(success=False, detail="Twilio credentials not configured")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls/{provider_call_id}.json"
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Dial>{target_number}</Dial></Response>'
        try:
            response = httpx.post(url, data={"Twiml": twiml}, auth=(self._account_sid, self._auth_token), timeout=10.0)
        except httpx.HTTPError as exc:
            return TransferResult(success=False, detail=str(exc))

        if response.status_code >= 400:
            return TransferResult(success=False, detail=response.text)
        return TransferResult(success=True)


def build_stream_twiml(websocket_url: str, from_number: str = "", to_number: str = "") -> str:
    """Builds the TwiML Twilio needs from the initial voice webhook to open
    a bidirectional Media Stream to our WebSocket endpoint, passing the
    caller/callee numbers through as custom parameters (see class docstring).

    `from_number`/`to_number` are properly XML-attribute-escaped: they come
    straight from the inbound webhook's form fields, and while a real
    Twilio request always sends plain E.164 numbers, this endpoint only
    rejects an unsigned request when Twilio credentials are configured
    (see app.api.telephony) — in mock/dev mode nothing stops a caller from
    posting a value containing `"` or `<`, which would otherwise corrupt
    the response XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Connect>"
        f"<Stream url={quoteattr(websocket_url)}>"
        f'<Parameter name="From" value={quoteattr(from_number)} />'
        f'<Parameter name="To" value={quoteattr(to_number)} />'
        "</Stream>"
        "</Connect>"
        "</Response>"
    )
