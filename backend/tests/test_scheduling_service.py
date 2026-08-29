"""Phase 7 — availability checking, conflict detection, duplicate-booking
prevention, cancellation, and rescheduling through ReceptionistService
against a real (SQLite) database.

Explicitly required by the phase: successful booking, unavailable slot,
duplicate booking, cancellation, rescheduling — each covered below."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.receptionist_service import ReceptionistService
from app.models.ai_agent import AIAgent
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Scheduling Clinic", slug="scheduling-clinic", timezone="America/New_York")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(Provider(workspace_id=ws.id, name="Dr. Lee", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="Front Desk AI",
            is_active=True,
            config={"instructions": "Be concise.", "supported_languages": ["en"]},
        )
    )
    db_session.commit()
    return ws


@pytest.fixture()
def service(db_session):
    return ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())


def run_turns(service, workspace_id, session_id, turns):
    result = None
    for turn in turns:
        result = service.handle_message(workspace_id, session_id, turn)
    return result


def book(service, workspace_id, phone, name, when="tomorrow at 3pm", provider_turn=None, service_name="Cleaning"):
    # The shared `workspace` fixture always has a Provider configured, so
    # the flow always asks for one — default to "no preference" unless the
    # test explicitly wants to pin a specific provider.
    state = service.start_session(workspace_id)
    turns = [
        "Hi",
        "book an appointment",
        f"My name is {name}",
        f"My phone is {phone}",
        service_name,
        provider_turn or "no preference",
        when,
        "Yes",
    ]
    return run_turns(service, workspace_id, state.session_id, turns)


# -- successful booking --------------------------------------------------------


def test_successful_booking(db_session, workspace, service):
    result = book(service, workspace.id, "415-555-0100", "Jane Doe")

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    assert appointment.status == "scheduled"
    assert "Jane Doe" in result.reply
    assert "book it" not in result.reply.lower()  # this is the outcome reply, not the confirmation prompt


def test_successful_booking_links_real_service_and_provider_rows(db_session, workspace, service):
    book(service, workspace.id, "415-555-0177", "Alex Kim", provider_turn="Dr. Lee please")

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    provider = db_session.execute(select(Provider).where(Provider.workspace_id == workspace.id)).scalar_one()
    svc = db_session.execute(select(Service).where(Service.workspace_id == workspace.id)).scalar_one()
    assert appointment.provider_id == provider.id
    assert appointment.service_id == svc.id


# -- unavailable slot (provider conflict) ---------------------------------------


def test_unavailable_slot_is_rejected_and_caller_is_never_told_confirmed(db_session, workspace, service):
    book(service, workspace.id, "415-555-0101", "First Caller", when="tomorrow at 3pm", provider_turn="Dr. Lee")

    second = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        second.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Second Caller",
            "My phone is 415-555-0202",
            "Cleaning",
            "Dr. Lee",
            "tomorrow at 3pm",
            "Yes",
        ],
    )

    appointments = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalars().all()
    assert len(appointments) == 1  # the second attempt was never created
    assert "not available" in result.reply.lower() or "no longer available" in result.reply.lower()
    assert "confirm" not in result.reply.lower()
    assert result.state.appointment.when is None  # cleared, ready to ask again
    assert result.state.missing_fields == ["datetime"]


def test_after_conflict_a_different_time_succeeds(db_session, workspace, service):
    book(service, workspace.id, "415-555-0101", "First Caller", when="tomorrow at 3pm", provider_turn="Dr. Lee")

    second = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        second.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Second Caller",
            "My phone is 415-555-0202",
            "Cleaning",
            "Dr. Lee",
            "tomorrow at 3pm",
            "Yes",
        ],
    )
    result = run_turns(service, workspace.id, second.session_id, ["tomorrow at 5pm", "Yes"])

    appointments = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalars().all()
    assert len(appointments) == 2
    assert "Second Caller" in result.reply


def test_no_conflict_check_without_a_pinned_provider(db_session, workspace, service):
    """Documented limitation: without a specific provider selected, there's
    no single resource to check for contention, so two "no preference"
    bookings at the same time both succeed."""
    book(service, workspace.id, "415-555-0301", "Caller One", when="tomorrow at 3pm", provider_turn="no preference")
    result = book(
        service, workspace.id, "415-555-0302", "Caller Two", when="tomorrow at 3pm", provider_turn="no preference"
    )

    appointments = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalars().all()
    assert len(appointments) == 2
    assert "Caller Two" in result.reply


# -- duplicate booking -----------------------------------------------------------


def test_duplicate_booking_by_the_same_caller_is_rejected(db_session, workspace, service):
    book(service, workspace.id, "415-555-0100", "Jane Doe", when="tomorrow at 3pm")

    second_attempt = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        second_attempt.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Jane Doe",
            "My phone is 415-555-0100",
            "Cleaning",
            "no preference",
            "tomorrow at 3pm",
            "Yes",
        ],
    )

    appointments = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalars().all()
    assert len(appointments) == 1  # the duplicate was never created
    assert "already have an appointment" in result.reply.lower()
    assert "confirm" not in result.reply.lower()


def test_duplicate_check_is_scoped_to_the_same_caller_not_other_patients(db_session, workspace, service):
    book(service, workspace.id, "415-555-0100", "Jane Doe", when="tomorrow at 3pm")
    result = book(service, workspace.id, "415-555-0999", "Other Patient", when="tomorrow at 3pm")

    appointments = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalars().all()
    assert len(appointments) == 2  # different patients, same time is fine (no provider pinned)
    assert "Other Patient" in result.reply


# -- cancellation ------------------------------------------------------------------


def test_cancellation_success(db_session, workspace, service):
    book(service, workspace.id, "415-555-0155", "Sam Rivera")
    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    assert appointment.status == "scheduled"

    cancel_state = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        cancel_state.session_id,
        ["Hi", "I need to cancel my appointment", "My phone is 415-555-0155"],
    )

    db_session.refresh(appointment)
    assert appointment.status == "cancelled"
    assert "cancelled" in result.reply.lower()


def test_cancellation_when_nothing_to_cancel_is_reported_honestly(db_session, workspace, service):
    state = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "I need to cancel my appointment", "My phone is 415-555-9999"],
    )
    assert "couldn't find" in result.reply.lower() or "cannot find" in result.reply.lower() or "no" in result.reply.lower()
    assert "cancelled" not in result.reply.lower()


# -- rescheduling --------------------------------------------------------------------


def test_rescheduling_success(db_session, workspace, service):
    book(service, workspace.id, "415-555-0177", "Alex Kim", when="tomorrow at 3pm")
    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    original_start = appointment.start_time

    reschedule_state = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        reschedule_state.session_id,
        ["Hi", "I want to reschedule my appointment", "My phone is 415-555-0177", "next Friday at 10am"],
    )

    db_session.refresh(appointment)
    assert appointment.start_time != original_start
    assert appointment.status == "scheduled"
    assert "moved" in result.reply.lower() or "reschedul" in result.reply.lower()


def test_rescheduling_into_a_conflicting_slot_is_rejected(db_session, workspace, service):
    book(service, workspace.id, "415-555-0101", "Patient One", when="tomorrow at 3pm", provider_turn="Dr. Lee")
    book(service, workspace.id, "415-555-0102", "Patient Two", when="tomorrow at 5pm", provider_turn="Dr. Lee")

    patient_two = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id, Patient.phone == "+14155550102")
    ).scalar_one()
    patient_two_appt = db_session.execute(
        select(Appointment).where(
            Appointment.workspace_id == workspace.id, Appointment.patient_id == patient_two.id
        )
    ).scalar_one()
    original_start = patient_two_appt.start_time

    reschedule_state = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        reschedule_state.session_id,
        ["Hi", "I want to reschedule my appointment", "My phone is 415-555-0102", "tomorrow at 3pm"],
    )

    db_session.refresh(patient_two_appt)
    # Patient Two's appointment must remain at its original time — the
    # reschedule attempt into an occupied slot must not have applied.
    assert patient_two_appt.start_time == original_start
    assert "not available" in result.reply.lower() or "no longer available" in result.reply.lower()


def test_reschedule_when_nothing_to_reschedule_is_reported_honestly(db_session, workspace, service):
    state = service.start_session(workspace.id)
    result = run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "I want to reschedule my appointment", "My phone is 415-555-9999", "tomorrow at 3pm"],
    )
    assert "couldn't find" in result.reply.lower() or "cannot find" in result.reply.lower() or "no" in result.reply.lower()
    assert "moved" not in result.reply.lower()
