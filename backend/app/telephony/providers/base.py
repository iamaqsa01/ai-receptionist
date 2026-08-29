from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.telephony.events import TelephonyEvent


@dataclass
class TransferResult:
    success: bool
    detail: str | None = None


class TelephonyAdapter(ABC):
    """Every telephony front door (Twilio Media Streams, Vapi, mock)
    implements this same interface: translate that provider's wire
    protocol to/from our canonical TelephonyEvent types. The WebSocket
    endpoint and CallSession orchestrator only ever depend on this
    abstraction — never a provider SDK or its raw message format directly."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def parse_message(self, raw: str | bytes) -> TelephonyEvent:
        """Parses one inbound websocket message into a canonical event."""

    @abstractmethod
    def encode_audio_message(self, call_id: str, audio: bytes) -> str | bytes:
        """Encodes outbound audio into the message this provider expects
        to receive over the same websocket connection to play it to the caller."""

    def encode_clear_message(self, call_id: str) -> str | bytes | None:
        """Encodes a "stop/clear playback" message (used for barge-in — the
        caller starts speaking while the AI is still talking). Returns None
        if the provider has no such concept; not every provider does."""
        return None

    def supports_live_transfer(self) -> bool:
        """Whether this adapter can actively hand a *live* call off to a
        human (Phase 10) — a real out-of-band control-plane call to the
        provider (e.g. Twilio's REST API), separate from anything sent over
        the Media Stream websocket itself. False by default; a provider
        opts in by overriding this (and transfer_call) together."""
        return False

    def transfer_call(self, provider_call_id: str, target_number: str) -> TransferResult:
        """Transfers the live call identified by `provider_call_id` to
        `target_number`. Only called when supports_live_transfer() is True;
        the default implementation exists purely so a provider that hasn't
        opted in fails loudly if it's ever called by mistake."""
        raise NotImplementedError(f"{self.name} adapter does not support live call transfer")
