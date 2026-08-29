"""Phase 15 — the full end-to-end scenario:

  Caller -> AI Receptionist -> STT -> LLM -> TTS -> qualification
  -> appointment -> database -> calendar -> WhatsApp -> email -> dashboard

Drives one inbound call all the way through the real WebSocket telephony
pipeline (mock STT/TTS/telephony adapter, mock LLM — same architecture a
real Twilio+Deepgram+ElevenLabs+OpenAI call would use, just swapped for
deterministic offline providers), then verifies every downstream system a
successful booking is supposed to touch: the Patient/Appointment/Lead rows,
the external calendar event, the WhatsApp + email confirmation messages,
and finally that the staff dashboard's own HTTP API (not just the DB
directly) can read all of it back.

This test is what caught a real, shipped bug while building Phase 15:
NotificationService (built in Phase 9) was never actually called from
ReceptionistService's booking/cancellation/reschedule flow, so no
WhatsApp/email confirmation was ever sent by a real booking — see the fix
in app/ai/receptionist_service.py (the `self.notifications` wiring)."""

import asyncio
import base64
import json

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.receptionist_service import ReceptionistService
from app.ai.speech.stt.mock_provider import MockSTTProvider
from app.ai.speech.tts.mock_provider import MockTTSProvider
from app.integrations.calendar.mock_provider import MockCalendarProvider
from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.models.ai_agent import AIAgent
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.integration_log import IntegrationLog
from app.models.lead import Lead
from app.models.notification_message import NotificationMessage
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.telephony.providers.mock_adapter import MockTelephonyAdapter
from app.telephony.session import CallSession
from tests.conftest import auth_headers, create_workspace, register_and_login


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def __call__(self, message: str) -> None:
        self.sent.append(message)


def decode(raw: str) -> str:
    return base64.b64decode(json.loads(raw)["payload"]).decode()


async def _wait_for_reply(sender, expected_count, *, timeout=3.0):
    elapsed, step = 0.0, 0.02
    while len(sender.sent) < expected_count and elapsed < timeout:
        await asyncio.sleep(step)
        elapsed += step


def test_full_scenario_caller_to_dashboard(client, db_session):
    # -- clinic setup, via the real HTTP API (staff/dashboard side) --------------
    staff_token = register_and_login(client, "e2e-owner@example.com")
    ws_id_str = create_workspace(client, staff_token, "End To End Clinic", "e2e-clinic")
    import uuid as uuid_module

    ws_id = uuid_module.UUID(ws_id_str)

    db_session.add(Service(workspace_id=ws_id, name="Cleaning", is_active=True))
    db_session.add(Provider(workspace_id=ws_id, name="Dr. Okafor", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws_id, name="Front Desk AI", is_active=True,
            config={"instructions": "Be concise.", "supported_languages": ["en"]},
        )
    )
    # Opt this workspace into calendar sync (Phase 8).
    db_session.add(
        Integration(
            workspace_id=ws_id, provider="google_calendar", is_active=True,
            config={"calendar_id": "clinic@example.com"},
        )
    )
    db_session.commit()

    # -- the call itself: caller -> telephony -> STT -> LLM -> TTS -----------------
    calendar = MockCalendarProvider()
    whatsapp = MockWhatsAppProvider()
    email = MockEmailProvider()
    receptionist = ReceptionistService(
        db=db_session,
        llm=MockLLMProvider(),
        store=InMemoryConversationStore(),
        calendar_provider=calendar,
        whatsapp_provider=whatsapp,
        email_provider=email,
    )
    sender = RecordingSender()
    session = CallSession(
        workspace_id=ws_id,
        adapter=MockTelephonyAdapter(),
        stt=MockSTTProvider(),
        tts=MockTTSProvider(),
        receptionist=receptionist,
        send=sender,
    )

    def start_msg(call_id="call-e2e"):
        return json.dumps({"event": "start", "call_id": call_id, "from": "+14155550100", "to": "+14155559990"})

    def media_msg(text, call_id="call-e2e"):
        return json.dumps({"event": "media", "call_id": call_id, "payload": base64.b64encode(text.encode()).decode()})

    caller_turns = [
        "Hi",
        "I'd like to book an appointment",
        "My name is Jane Doe",
        "My phone is 415-555-0100",
        "Cleaning",
        "no preference",
        "next Monday at 2pm",
        "Yes",
    ]

    async def run_call():
        await session.handle_raw_message(start_msg())
        for i, text in enumerate(caller_turns):
            await session.handle_raw_message(media_msg(text))
            await _wait_for_reply(sender, i + 2)  # +1 greeting, +1 per turn so far
        await session.close()

    asyncio.run(run_call())

    replies = [decode(m) for m in sender.sent]
    assert any("Jane Doe" in r for r in replies), f"booking confirmation never spoken to caller; replies={replies}"

    # -- database: patient + appointment + lead ------------------------------------
    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == ws_id, Patient.phone == "+14155550100")
    ).scalar_one()
    assert patient.first_name == "Jane"

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == ws_id, Appointment.patient_id == patient.id)
    ).scalar_one()
    assert appointment.status == "scheduled"

    lead = db_session.execute(
        select(Lead).where(Lead.workspace_id == ws_id, Lead.phone == "+14155550100")
    ).scalar_one()
    assert lead.status == "converted"  # a completed booking always escalates the lead

    # -- calendar: the mock provider actually has the event -------------------------
    assert appointment.external_calendar_event_id is not None
    assert appointment.external_calendar_provider == "mock"
    assert calendar.check_availability("clinic@example.com", appointment.start_time, appointment.end_time) is False

    # -- WhatsApp + email: the patient-facing confirmation actually sent -----------
    assert len(whatsapp.sent) == 1, "no WhatsApp confirmation was sent for the booking"
    assert whatsapp.sent[0]["to"] == "+14155550100"
    assert "confirmed" in whatsapp.sent[0]["body"].lower()

    notification_rows = db_session.execute(
        select(NotificationMessage).where(NotificationMessage.workspace_id == ws_id)
    ).scalars().all()
    channels_sent = {(row.channel, row.status) for row in notification_rows}
    assert ("whatsapp", "sent") in channels_sent
    # Patient has no email on file in this scenario (only phone was given),
    # so no email attempt should exist — NotificationService must not
    # fabricate a recipient.
    assert email.sent == []

    # -- integration logs: calendar + WhatsApp calls were both recorded ------------
    integration_rows = db_session.execute(
        select(IntegrationLog).where(IntegrationLog.workspace_id == ws_id)
    ).scalars().all()
    categories = {row.category for row in integration_rows}
    assert "calendar" in categories
    assert "whatsapp" in categories
    assert all(row.status == "success" for row in integration_rows)

    # -- dashboard: the staff-facing HTTP API reflects all of the above ------------
    appts_resp = client.get(f"/api/v1/workspaces/{ws_id}/appointments", headers=auth_headers(staff_token))
    assert appts_resp.status_code == 200
    assert len(appts_resp.json()) == 1
    assert appts_resp.json()[0]["status"] == "scheduled"

    patients_resp = client.get(f"/api/v1/workspaces/{ws_id}/patients", headers=auth_headers(staff_token))
    assert any(p["phone"] == "+14155550100" for p in patients_resp.json())

    leads_resp = client.get(f"/api/v1/workspaces/{ws_id}/leads", headers=auth_headers(staff_token))
    assert any(l["status"] == "converted" for l in leads_resp.json())

    notif_resp = client.get(f"/api/v1/workspaces/{ws_id}/notification-messages", headers=auth_headers(staff_token))
    assert notif_resp.status_code == 200
    assert any(n["channel"] == "whatsapp" and n["status"] == "sent" for n in notif_resp.json())

    analytics_resp = client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary", headers=auth_headers(staff_token))
    assert analytics_resp.status_code == 200
    summary = analytics_resp.json()
    assert summary["appointments"] == 1
    assert summary["qualified_leads"] >= 1
    assert summary["integration_failures"] == 0


# -- duplicate booking prevention, exercised through the same live pipeline -----------


def test_duplicate_booking_is_rejected_and_no_second_notification_sent(client, db_session):
    import uuid as uuid_module

    staff_token = register_and_login(client, "e2e-dup-owner@example.com")
    ws_id = uuid_module.UUID(create_workspace(client, staff_token, "Dup Clinic", "e2e-dup-clinic"))

    db_session.add(Service(workspace_id=ws_id, name="Cleaning", is_active=True))
    db_session.add(
        AIAgent(workspace_id=ws_id, name="AI", is_active=True, config={"supported_languages": ["en"]})
    )
    db_session.commit()

    whatsapp = MockWhatsAppProvider()
    receptionist = ReceptionistService(
        db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore(),
        calendar_provider=MockCalendarProvider(), whatsapp_provider=whatsapp, email_provider=MockEmailProvider(),
    )

    def book(when: str):
        state = receptionist.start_session(ws_id)
        turns = ["Hi", "book an appointment", "My name is Jane Doe", "My phone is 415-555-0100", "Cleaning", "no preference", when, "Yes"]
        result = None
        for turn in turns:
            result = receptionist.handle_message(ws_id, state.session_id, turn)
        return result

    first = book("next Monday at 2pm")
    assert "Jane Doe" in first.reply

    second = book("next Monday at 2:15pm")  # overlaps the first booking
    assert "already have" in second.reply.lower() or "duplicate" in second.reply.lower() or "you already" in second.reply.lower()

    appointments = db_session.execute(select(Appointment).where(Appointment.workspace_id == ws_id)).scalars().all()
    assert len(appointments) == 1  # the duplicate was never written

    # Only one booking confirmation was ever sent — the rejected duplicate
    # attempt must not have triggered a second WhatsApp message.
    assert len(whatsapp.sent) == 1

    resp = client.get(f"/api/v1/workspaces/{ws_id}/appointments", headers=auth_headers(staff_token))
    assert len(resp.json()) == 1


# -- Receptionist handoff, exercised through the same live pipeline -------------------


def test_human_transfer_reaches_dashboard(client, db_session):
    import uuid as uuid_module

    staff_token = register_and_login(client, "e2e-handoff-owner@example.com")
    ws_id = uuid_module.UUID(create_workspace(client, staff_token, "Handoff Clinic", "e2e-handoff-clinic"))
    db_session.add(
        AIAgent(workspace_id=ws_id, name="AI", is_active=True, config={"supported_languages": ["en"]})
    )
    db_session.commit()

    receptionist = ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())
    state = receptionist.start_session(ws_id)
    receptionist.handle_message(ws_id, state.session_id, "Hi")
    result = receptionist.handle_message(ws_id, state.session_id, "Can I speak to a human please")
    assert result.state.status.value == "needs_human"

    resp = client.get(f"/api/v1/workspaces/{ws_id}/human-handoffs", headers=auth_headers(staff_token))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["trigger"] == "caller_request"

    analytics_resp = client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary", headers=auth_headers(staff_token))
    assert analytics_resp.json()["receptionist_transfers"] == 1


# -- API/integration failure resilience: booking still succeeds end-to-end -----------


def test_calendar_and_notification_failures_never_block_the_booking(client, db_session, monkeypatch):
    """A booking must always succeed in this system's own database even if
    every downstream integration (calendar, WhatsApp, email) is down —
    those are all best-effort side effects, never a precondition."""
    import uuid as uuid_module

    from app.integrations.notifications.exceptions import NotificationAPIError

    staff_token = register_and_login(client, "e2e-fail-owner@example.com")
    ws_id = uuid_module.UUID(create_workspace(client, staff_token, "Failure Clinic", "e2e-failure-clinic"))
    db_session.add(Service(workspace_id=ws_id, name="Cleaning", is_active=True))
    db_session.add(
        AIAgent(workspace_id=ws_id, name="AI", is_active=True, config={"supported_languages": ["en"]})
    )
    db_session.add(
        Integration(workspace_id=ws_id, provider="google_calendar", is_active=True, config={"calendar_id": "primary"})
    )
    db_session.commit()

    calendar = MockCalendarProvider()

    def boom_calendar(*args, **kwargs):
        from app.integrations.calendar.exceptions import CalendarAPIError
        raise CalendarAPIError("simulated calendar outage", status_code=503)

    monkeypatch.setattr(calendar, "create_event", boom_calendar)

    class BoomWhatsApp(MockWhatsAppProvider):
        def send(self, to, body):
            raise NotificationAPIError("simulated WhatsApp outage", status_code=503)

    receptionist = ReceptionistService(
        db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore(),
        calendar_provider=calendar, whatsapp_provider=BoomWhatsApp(), email_provider=MockEmailProvider(),
    )
    state = receptionist.start_session(ws_id)
    turns = ["Hi", "book an appointment", "My name is Resilient Caller", "My phone is 415-555-0199", "Cleaning", "no preference", "next Monday at 2pm", "Yes"]
    result = None
    for turn in turns:
        result = receptionist.handle_message(ws_id, state.session_id, turn)

    assert "Resilient Caller" in result.reply  # caller still hears success

    resp = client.get(f"/api/v1/workspaces/{ws_id}/appointments", headers=auth_headers(staff_token))
    assert resp.status_code == 200
    appts = resp.json()
    assert len(appts) == 1
    assert appts[0]["status"] == "scheduled"

    analytics_resp = client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary", headers=auth_headers(staff_token))
    summary = analytics_resp.json()
    assert summary["appointments"] == 1
    assert summary["integration_failures"] >= 2  # calendar + whatsapp both failed and were logged
