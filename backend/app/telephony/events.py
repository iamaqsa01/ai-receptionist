from dataclasses import dataclass


@dataclass
class CallStarted:
    call_id: str
    from_number: str | None = None
    to_number: str | None = None
    sample_rate: int = 8000
    # The provider's own call identifier, when it differs from `call_id`
    # (e.g. Twilio Media Streams' streamSid, used as call_id throughout this
    # pipeline, is distinct from the CallSid a live-transfer REST call needs
    # — see TwilioAdapter.transfer_call). None means call_id doubles as
    # both (true for the mock adapter and Vapi).
    provider_call_id: str | None = None


@dataclass
class AudioChunk:
    call_id: str
    payload: bytes


@dataclass
class CallEnded:
    call_id: str


@dataclass
class UnknownEvent:
    raw: object


# The canonical, provider-agnostic event a TelephonyAdapter parses every
# inbound wire message into. The call-session orchestrator only ever
# handles these four types — it never sees a provider's raw JSON.
TelephonyEvent = CallStarted | AudioChunk | CallEnded | UnknownEvent
