import base64
import json

import httpx

from app.telephony.events import AudioChunk, CallEnded, CallStarted, TelephonyEvent, UnknownEvent
from app.telephony.providers.base import TelephonyAdapter, TransferResult


class VapiAdapter(TelephonyAdapter):
    """Vapi's server-side WebSocket transport.

    Vapi's raw-audio server transport is far less standardized in public
    documentation than Twilio's Media Streams, so this is a best-effort,
    lower-confidence implementation modeled on Vapi's publicly documented
    message conventions (a `type`-discriminated JSON envelope, a `call`
    object carrying the call id and phone numbers, 16kHz PCM audio rather
    than Twilio's 8kHz mulaw since Vapi calls aren't always PSTN-originated).
    It has not been verified against a live Vapi account or webhook in this
    environment — treat it as a structurally-complete adapter satisfying the
    same TelephonyAdapter interface as Twilio, not as a confirmed-correct
    wire-protocol implementation. MockTelephonyAdapter is what's actually
    exercised end-to-end by the test suite.

    Assumed wire format:
      {"type": "start", "call": {"id": "...", "customer": {"number": "..."},
        "phoneNumber": {"number": "..."}}}
      {"type": "media", "callId": "...", "payload": "<base64 pcm16>",
        "sampleRate": 16000}
      {"type": "end", "callId": "..."}
    """

    name = "vapi"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    def parse_message(self, raw: str | bytes) -> TelephonyEvent:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            payload = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return UnknownEvent(raw=raw)

        message_type = payload.get("type")

        if message_type == "start":
            call = payload.get("call", {}) or {}
            call_id = call.get("id")
            if not call_id:
                return UnknownEvent(raw=raw)
            return CallStarted(
                call_id=call_id,
                from_number=(call.get("customer") or {}).get("number"),
                to_number=(call.get("phoneNumber") or {}).get("number"),
                sample_rate=int(payload.get("sampleRate", 16000)),
            )

        if message_type == "media":
            call_id = payload.get("callId")
            b64_payload = payload.get("payload")
            if not call_id or not b64_payload:
                return UnknownEvent(raw=raw)
            try:
                audio = base64.b64decode(b64_payload)
            except Exception:
                return UnknownEvent(raw=raw)
            return AudioChunk(call_id=call_id, payload=audio)

        if message_type == "end":
            call_id = payload.get("callId")
            if not call_id:
                return UnknownEvent(raw=raw)
            return CallEnded(call_id=call_id)

        return UnknownEvent(raw=raw)

    def encode_audio_message(self, call_id: str, audio: bytes) -> str:
        return json.dumps(
            {"type": "media", "callId": call_id, "payload": base64.b64encode(audio).decode("ascii")}
        )

    def encode_clear_message(self, call_id: str) -> str:
        return json.dumps({"type": "clear", "callId": call_id})

    def supports_live_transfer(self) -> bool:
        return self.is_available()

    def transfer_call(self, provider_call_id: str, target_number: str) -> TransferResult:
        """Best-effort, modeled on Vapi's documented call-control API
        (`POST /call/{id}/control` with a transfer control message). Same
        caveat as the rest of this adapter (see class docstring): not
        verified against a live Vapi account in this environment."""
        if not self.is_available():
            return TransferResult(success=False, detail="Vapi API key not configured")

        url = f"https://api.vapi.ai/call/{provider_call_id}/control"
        payload = {"type": "transfer", "destination": {"type": "number", "number": target_number}}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        except httpx.HTTPError as exc:
            return TransferResult(success=False, detail=str(exc))

        if response.status_code >= 400:
            return TransferResult(success=False, detail=response.text)
        return TransferResult(success=True)
