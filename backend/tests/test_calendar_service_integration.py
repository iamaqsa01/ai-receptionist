"""Phase 8 — Google Calendar integration wired all the way through the AI
Receptionist conversation flow: booking, unavailable slot (calendar-sourced
this time, not just internal DB), cancellation, and rescheduling, each
verified to actually create/update/cancel a calendar event and store the
external event id — plus that a workspace which hasn't opted in sees no
calendar activity at all."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.receptionist_service import ReceptionistService
from app.integrations.calendar.mock_provider import MockCalendarProvider
from app.models.ai_agent import AIAgent
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.notification import Notification
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace


@pytest.fixture()
def calendar():
    return MockCalendarProvider()


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Sync Clinic", slug="sync-clinic", timezone="UTC")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(Provider(workspace_id=ws.id, name="Dr. Lee", is_active=True))
    db_session.add(
        AIAgent(workspace_id=ws.id, name="AI", is_active=True, config={"instructions": "Be concise.", "supported_languages": ["en"]})
    )
    db_session.add(
        Integration(
            workspace_id=ws.id, provider="google_calendar", is_active=True, config={"calendar_id": "clinic@example.com"}
        )
    )
    db_session.commit()
    return ws


@pytest.fixture()
def service(db_session, calendar):
    return ReceptionistService(
        db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore(), calendar_provider=calendar
    )


def run_turns(service, workspace_id, session_id, turns):
    result = None
    for turn in turns:
        result = service.handle_message(workspace_id, session_id, turn)
    return result


def book(service, workspace_id, phone, name, when="tomorrow at 3pm", provider_turn="no preference"):
    state = service.start_session(workspace_id)
    turns = ["Hi", "book an appointment", f"My name is {name}", f"My phone is {phone}", "Cleaning", provider_turn, when, "Yes"]
    return run_turns(service, workspace_id, state.session_id, turns)


# -- successful booking syncs to the calendar ---------------------------------------


def test_successful_booking_creates_a_calendar_event(db_session, workspace, service, calendar):
    book(service, workspace.id, "415-555-0100", "Jane Doe")

    appointment = db_session.execute(select(Appointment).where(Appointment.workspace_id == workspace.id)).scalar_one()
    assert appointment.external_calendar_event_id is not None
    assert appointment.external_calendar_provider == "mock"

    # The event genuinely exists on the (mock) calendar, blocking that slot.
    assert calendar.check_availability("clinic@example.com", appointment.start_time, appointment.end_time) is False


def test_workspace_without_calendar_integration_has_no_calendar_activity(db_session, service, calendar):
    ws = Workspace(name="Plain Clinic", slug="plain-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(AIAgent(workspace_id=ws.id, name="AI", is_active=True, config={"supported_languages": ["en"]}))
    db_session.commit()

    book(service, ws.id, "415-555-0111", "No Calendar Caller")

    appointment = db_session.execute(select(Appointment).where(Appointment.workspace_id == ws.id)).scalar_one()
    assert appointment.external_calendar_event_id is None
    assert calendar._events == {}  # the mock calendar was never touched


# -- unavailable slot, sourced from the external calendar this time ------------------


def test_calendar_only_conflict_blocks_booking_even_without_internal_conflict(db_session, workspace, service, calendar):
    """Something was placed directly on the Google Calendar (not through
    this system) — our own DB has no idea, but the external availability
    check must still catch it."""
    from datetime import datetime, timezone

    blocked_start = datetime(2026, 12, 15, 14, 0, tzinfo=timezone.utc)
    blocked_end = datetime(2026, 12, 15, 14, 30, tzinfo=timezone.utc)
    calendar.create_event(
        "clinic@example.com", summary="External meeting", description="", start=blocked_start, end=blocked_end
    )

    state = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Jane Doe",
            "My phone is 415-555-0100",
            "Cleaning",
            "no preference",
            "December 15 2026 at 2pm",
            "Yes",
        ],
    )

    appointments = db_session.execute(select(Appointment).where(Appointment.workspace_id == workspace.id)).scalars().all()
    assert appointments == []  # never created
    assert "not available" in result.reply.lower() or "no longer available" in result.reply.lower()


# -- cancellation removes the calendar event -----------------------------------------


def test_cancellation_removes_the_calendar_event(db_session, workspace, service, calendar):
    book(service, workspace.id, "415-555-0155", "Sam Rivera")
    appointment = db_session.execute(select(Appointment).where(Appointment.workspace_id == workspace.id)).scalar_one()
    event_id = appointment.external_calendar_event_id
    assert calendar.check_availability("clinic@example.com", appointment.start_time, appointment.end_time) is False

    cancel_state = service.start_session(workspace.id)
    run_turns(service, workspace.id, cancel_state.session_id, ["Hi", "I need to cancel my appointment", "My phone is 415-555-0155"])

    db_session.refresh(appointment)
    assert appointment.status == "cancelled"
    assert appointment.external_calendar_event_id is None
    # The slot is free on the calendar again.
    assert calendar.check_availability("clinic@example.com", appointment.start_time, appointment.end_time) is True
    assert event_id not in calendar._events.get("clinic@example.com", {})


# -- rescheduling updates the calendar event -----------------------------------------


def test_rescheduling_moves_the_calendar_event(db_session, workspace, service, calendar):
    book(service, workspace.id, "415-555-0177", "Alex Kim", when="tomorrow at 3pm")
    appointment = db_session.execute(select(Appointment).where(Appointment.workspace_id == workspace.id)).scalar_one()
    event_id = appointment.external_calendar_event_id
    old_start = appointment.start_time
    old_end = appointment.end_time

    reschedule_state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        reschedule_state.session_id,
        ["Hi", "I want to reschedule my appointment", "My phone is 415-555-0177", "next Friday at 10am"],
    )

    db_session.refresh(appointment)
    assert appointment.start_time != old_start
    assert appointment.external_calendar_event_id == event_id  # same event, moved — not a new one
    assert calendar.check_availability("clinic@example.com", old_start, old_end) is True
    assert calendar.check_availability("clinic@example.com", appointment.start_time, appointment.end_time) is False


# -- calendar sync failure raises a notification but never breaks the call -----------


def test_calendar_sync_failure_during_booking_still_completes_the_booking(db_session, workspace, service, calendar, monkeypatch):
    def boom(*args, **kwargs):
        from app.integrations.calendar.exceptions import CalendarAPIError

        raise CalendarAPIError("simulated outage", status_code=503)

    monkeypatch.setattr(calendar, "create_event", boom)

    result = book(service, workspace.id, "415-555-0199", "Resilient Caller")

    appointment = db_session.execute(select(Appointment).where(Appointment.workspace_id == workspace.id)).scalar_one()
    assert appointment.status == "scheduled"  # booking still succeeded
    assert appointment.external_calendar_event_id is None
    assert "Resilient Caller" in result.reply  # caller still hears a normal success message

    notification = db_session.execute(
        select(Notification).where(Notification.workspace_id == workspace.id, Notification.type == "calendar_sync_error")
    ).scalar_one()
    assert notification.title
