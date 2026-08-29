import asyncio
import base64
import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.receptionist_service import ReceptionistService
from app.ai.speech.stt.base import STTStreamSession, SpeechToTextProvider, TranscriptResult
from app.ai.speech.stt.mock_provider import MockSTTProvider
from app.ai.speech.tts.base import TextToSpeechProvider
from app.ai.speech.tts.mock_provider import MockTTSProvider
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from app.telephony.providers.mock_adapter import MockTelephonyAdapter
from app.telephony.session import CallSession


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Session Test Clinic", slug="session-test-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.commit()
    return ws


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def __call__(self, message: str) -> None:
        self.sent.append(message)


def make_session(db_session, workspace, *, tts=None, stt=None):
    sender = RecordingSender()
    session = CallSession(
        workspace_id=workspace.id,
        adapter=MockTelephonyAdapter(),
        stt=stt or MockSTTProvider(),
        tts=tts or MockTTSProvider(),
        receptionist=ReceptionistService(db=db_session, store=InMemoryConversationStore()),
        send=sender,
    )
    return session, sender


def start_msg(call_id="call-x"):
    return json.dumps({"event": "start", "call_id": call_id, "from": "+15551230000", "to": "+15559990000"})


def media_msg(text, call_id="call-x"):
    return json.dumps(
        {"event": "media", "call_id": call_id, "payload": base64.b64encode(text.encode()).decode()}
    )


def decode(raw: str) -> str:
    return base64.b64decode(json.loads(raw)["payload"]).decode()


async def _wait_for_reply_count(sender, expected_count, *, timeout=3.0):
    """Each caller turn is processed on a worker thread (asyncio.to_thread,
    see CallSession._handle_final_transcript) — how long that takes varies
    a lot (language detection's one-time model load on a cold process
    alone has measured up to several hundred ms; a turn that also books an
    appointment does several more DB round-trips, calendar sync, and a
    notification send on top of that). `sender.sent` growing is the actual
    completion signal: TTS synthesis + send only happens once
    ReceptionistService.handle_message has fully returned, including every
    side effect — the conversation-history length was tried first and is
    NOT equivalent, since the engine appends a provisional reply to
    history *before* those side effects run, so waiting on history length
    alone raced ahead of a booking turn's calendar/notification writes
    while CallSession.close() concurrently touched the same DB session
    (IllegalStateChangeError) — a real bug this test helper needs to avoid
    triggering, not just a timing nicety."""
    elapsed = 0.0
    step = 0.02
    while len(sender.sent) < expected_count and elapsed < timeout:
        await asyncio.sleep(step)
        elapsed += step


async def _run_turns(session, sender, turns, call_id="call-x"):
    await session.handle_raw_message(start_msg(call_id))
    reply_count = 0
    for text in turns:
        await session.handle_raw_message(media_msg(text, call_id))
        reply_count += 1
        await _wait_for_reply_count(sender, reply_count)


def test_call_id_is_captured_from_start_event(db_session, workspace):
    session, _ = make_session(db_session, workspace)
    asyncio.run(session.handle_raw_message(start_msg("call-42")))
    assert session.call_id == "call-42"


def test_booking_persists_through_full_session(db_session, workspace):
    session, sender = make_session(db_session, workspace)

    async def run():
        await _run_turns(
            session,
            sender,
            [
                "Hi",
                "I would like to book an appointment",
                "My name is Jane Doe",
                "My phone is 415-555-0100",
                "Cleaning",
                "Next Tuesday at 3pm",
                "Yes",
            ],
        )
        await session.close()

    asyncio.run(run())

    replies = [decode(m) for m in sender.sent]
    assert any("Jane Doe" in r for r in replies)

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id, Patient.phone == "+14155550100")
    ).scalar_one()
    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)
    ).scalar_one()
    assert appointment.status == "scheduled"


class ExplodingTTSProvider(TextToSpeechProvider):
    name = "exploding"

    def is_available(self) -> bool:
        return True

    async def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        raise RuntimeError("simulated TTS outage")


def test_tts_failure_does_not_crash_session_or_block_next_turn(db_session, workspace):
    session, sender = make_session(db_session, workspace, tts=ExplodingTTSProvider())

    async def run():
        await session.handle_raw_message(start_msg())
        await session.handle_raw_message(media_msg("Hi there"))
        await asyncio.sleep(0.05)
        await session.close()

    asyncio.run(run())
    # TTS blew up, so nothing was sent — but nothing raised out of the
    # session either, and close() completed cleanly.
    assert sender.sent == []


class ExplodingSTTStreamSession(STTStreamSession):
    async def send_audio(self, chunk: bytes) -> None:
        raise RuntimeError("simulated STT connection drop")

    async def transcripts(self):
        return
        yield  # pragma: no cover - makes this an async generator

    async def finish(self) -> None:
        pass


class ExplodingSTTProvider(SpeechToTextProvider):
    name = "exploding"

    def is_available(self) -> bool:
        return True

    async def start_stream(self, *, language: str | None = None, sample_rate: int = 8000):
        return ExplodingSTTStreamSession()


def test_stt_failure_is_logged_and_does_not_crash_session(db_session, workspace):
    session, sender = make_session(db_session, workspace, stt=ExplodingSTTProvider())

    async def run():
        await session.handle_raw_message(start_msg())
        # send_audio() raises internally; handle_raw_message must not
        # propagate that up to the websocket loop and take the connection
        # down — it should be caught, logged, and the session kept alive.
        await session.handle_raw_message(media_msg("Hi there"))
        await session.close()

    asyncio.run(run())  # must not raise
    assert sender.sent == []


def test_close_is_idempotent(db_session, workspace):
    session, _ = make_session(db_session, workspace)

    async def run():
        await session.handle_raw_message(start_msg())
        await session.close()
        await session.close()  # must not raise

    asyncio.run(run())


def test_audio_before_call_start_is_dropped_not_fatal(db_session, workspace):
    session, sender = make_session(db_session, workspace)

    async def run():
        await session.handle_raw_message(media_msg("premature audio"))  # no start yet

    asyncio.run(run())
    assert sender.sent == []


def test_idle_timeout_prompt_uses_established_language(db_session, workspace):
    session, sender = make_session(db_session, workspace)

    async def run():
        await session.handle_raw_message(start_msg())
        await session.handle_raw_message(media_msg("السلام علیکم، مجھے اپائنٹمنٹ کے لیے مدد چاہیے"))
        await _wait_for_reply_count(sender, 1)
        should_close = await session.handle_idle_timeout()
        return should_close

    should_close = asyncio.run(run())
    assert should_close is False
    last_reply = decode(sender.sent[-1])
    # Idle prompt must come back in the language the caller established (Urdu),
    # not the English default.
    assert any("؀" <= ch <= "ۿ" for ch in last_reply)
    assert "repeat it?" not in last_reply
