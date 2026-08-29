"""Phase 10 — telephony-layer live call transfer: capability flags,
provider_call_id capture (Twilio's CallSid vs. streamSid), and CallSession
wiring the adapter + provider_call_id through to ReceptionistService so a
human handoff can actually move the live call, not just record it."""

import asyncio
import base64
import json

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.receptionist_service import ReceptionistService
from app.ai.speech.stt.mock_provider import MockSTTProvider
from app.ai.speech.tts.mock_provider import MockTTSProvider
from app.models.ai_agent import AIAgent
from app.models.human_handoff import HumanHandoff
from app.models.service import Service
from app.models.workspace import Workspace
from app.telephony.providers.base import TransferResult
from app.telephony.providers.mock_adapter import MockTelephonyAdapter
from app.telephony.providers.twilio_adapter import TwilioAdapter
from app.telephony.providers.vapi_adapter import VapiAdapter
from app.telephony.session import CallSession


async def _wait_for_reply(sender, *, timeout=3.0):
    """Each caller turn is processed on a worker thread (asyncio.to_thread)
    and can take a while on a cold process — language detection's first
    call loads its model data, which alone has measured up to several
    hundred ms. Poll for the actual reply landing rather than a fixed
    sleep guess (see the equivalent helper in test_telephony_session.py)."""
    elapsed = 0.0
    step = 0.02
    while not sender.sent and elapsed < timeout:
        await asyncio.sleep(step)
        elapsed += step


# -- capability flags / unavailable-without-credentials -----------------------------


def test_mock_adapter_supports_live_transfer_and_records_it():
    adapter = MockTelephonyAdapter()
    assert adapter.supports_live_transfer() is True

    result = adapter.transfer_call("CA123", "+15551234567")
    assert result.success is True
    assert adapter.transfers == [{"provider_call_id": "CA123", "target_number": "+15551234567"}]


def test_twilio_adapter_transfer_unavailable_without_credentials():
    adapter = TwilioAdapter(account_sid="", auth_token="")
    assert adapter.supports_live_transfer() is False
    result = adapter.transfer_call("CA123", "+15551234567")
    assert result.success is False


def test_twilio_adapter_supports_live_transfer_once_configured():
    adapter = TwilioAdapter(account_sid="AC123", auth_token="secret")
    assert adapter.supports_live_transfer() is True


def test_vapi_adapter_transfer_unavailable_without_credentials():
    adapter = VapiAdapter(api_key="")
    assert adapter.supports_live_transfer() is False
    result = adapter.transfer_call("call-123", "+15551234567")
    assert result.success is False


def test_vapi_adapter_supports_live_transfer_once_configured():
    adapter = VapiAdapter(api_key="key123")
    assert adapter.supports_live_transfer() is True


def test_base_adapter_default_has_no_live_transfer():
    from app.telephony.providers.base import TelephonyAdapter

    class BareAdapter(TelephonyAdapter):
        name = "bare"

        def is_available(self):
            return True

        def parse_message(self, raw):
            raise NotImplementedError

        def encode_audio_message(self, call_id, audio):
            raise NotImplementedError

    adapter = BareAdapter()
    assert adapter.supports_live_transfer() is False
    with pytest.raises(NotImplementedError):
        adapter.transfer_call("x", "+15551234567")


# -- provider_call_id capture --------------------------------------------------------


def test_twilio_adapter_captures_call_sid_distinct_from_stream_sid():
    adapter = TwilioAdapter(account_sid="AC1", auth_token="secret")
    raw = json.dumps(
        {
            "event": "start",
            "streamSid": "MZ_streamsid_123",
            "start": {
                "streamSid": "MZ_streamsid_123",
                "callSid": "CA_callsid_456",
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                "customParameters": {"From": "+15551230000", "To": "+15559990000"},
            },
        }
    )
    event = adapter.parse_message(raw)
    assert event.call_id == "MZ_streamsid_123"
    assert event.provider_call_id == "CA_callsid_456"
    assert event.call_id != event.provider_call_id


def test_vapi_adapter_call_id_has_no_separate_provider_call_id():
    adapter = VapiAdapter(api_key="key123")
    raw = json.dumps({"type": "start", "call": {"id": "call-abc", "customer": {"number": "+15551230000"}}})
    event = adapter.parse_message(raw)
    assert event.call_id == "call-abc"
    assert event.provider_call_id is None  # CallSession falls back to call_id itself


# -- CallSession wiring: adapter + provider_call_id reach ReceptionistService --------


@pytest.fixture()
def workspace_with_transfer_number(db_session):
    ws = Workspace(name="Transfer Clinic", slug="transfer-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="AI",
            is_active=True,
            config={"supported_languages": ["en"], "human_transfer_number": "+15559990000"},
        )
    )
    db_session.commit()
    return ws


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def __call__(self, message: str) -> None:
        self.sent.append(message)


def test_call_session_attempts_live_transfer_on_human_transfer_request(db_session, workspace_with_transfer_number):
    adapter = MockTelephonyAdapter()
    sender = RecordingSender()
    session = CallSession(
        workspace_id=workspace_with_transfer_number.id,
        adapter=adapter,
        stt=MockSTTProvider(),
        tts=MockTTSProvider(),
        receptionist=ReceptionistService(db=db_session, store=InMemoryConversationStore()),
        send=sender,
    )

    def start_msg(call_id="call-x", call_sid="CA-real-999"):
        return json.dumps({"event": "start", "call_id": call_id, "call_sid": call_sid, "from": "+15551230000", "to": "+15559990000"})

    def media_msg(text, call_id="call-x"):
        return json.dumps({"event": "media", "call_id": call_id, "payload": base64.b64encode(text.encode()).decode()})

    async def run():
        await session.handle_raw_message(start_msg())
        await session.handle_raw_message(media_msg("Can I speak to a human please"))
        await _wait_for_reply(sender)
        await session.close()

    asyncio.run(run())

    assert adapter.transfers == [{"provider_call_id": "CA-real-999", "target_number": "+15559990000"}]

    handoff = db_session.execute(
        select(HumanHandoff).where(HumanHandoff.workspace_id == workspace_with_transfer_number.id)
    ).scalar_one()
    assert handoff.status == "transferred"
    assert handoff.trigger == "caller_request"


def test_call_session_falls_back_to_call_id_when_no_call_sid_given(db_session, workspace_with_transfer_number):
    """The mock adapter's "start" message doesn't always carry a separate
    call_sid (real Twilio always does) — CallSession must still work,
    falling back to call_id as the provider_call_id."""
    adapter = MockTelephonyAdapter()
    sender = RecordingSender()
    session = CallSession(
        workspace_id=workspace_with_transfer_number.id,
        adapter=adapter,
        stt=MockSTTProvider(),
        tts=MockTTSProvider(),
        receptionist=ReceptionistService(db=db_session, store=InMemoryConversationStore()),
        send=sender,
    )

    async def run():
        await session.handle_raw_message(json.dumps({"event": "start", "call_id": "call-y", "from": "+1", "to": "+2"}))
        await session.handle_raw_message(
            json.dumps(
                {
                    "event": "media",
                    "call_id": "call-y",
                    "payload": base64.b64encode(b"Can I speak to a human please").decode(),
                }
            )
        )
        await _wait_for_reply(sender)
        await session.close()

    asyncio.run(run())

    assert adapter.transfers == [{"provider_call_id": "call-y", "target_number": "+15559990000"}]
