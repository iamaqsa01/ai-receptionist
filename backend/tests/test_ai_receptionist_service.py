import uuid

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.receptionist_service import ReceptionistService, UnknownConversationSessionError
from app.models.ai_agent import AIAgent
from app.models.appointment import Appointment
from app.models.notification import Notification
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Sunrise Dental", slug="sunrise-dental")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(Service(workspace_id=ws.id, name="Checkup", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="Front Desk AI",
            is_active=True,
            config={"instructions": "Be concise.", "supported_languages": ["en", "es"]},
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


def test_booking_creates_patient_and_appointment_scoped_to_workspace(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
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

    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id, Patient.phone == "+14155550100")
    ).scalar_one()
    assert patient.first_name == "Jane"
    assert patient.last_name == "Doe"

    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id, Appointment.patient_id == patient.id)
    ).scalar_one()
    assert appointment.status == "scheduled"
    assert "Cleaning" in appointment.notes


def test_cancellation_marks_appointment_cancelled(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Sam Rivera",
            "My phone is 415-555-0155",
            "Checkup",
            "tomorrow at 3pm",
            "Yes",
        ],
    )
    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    assert appointment.status == "scheduled"

    cancel_state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        cancel_state.session_id,
        ["Hi", "I need to cancel my appointment", "My phone is 415-555-0155"],
    )

    db_session.refresh(appointment)
    assert appointment.status == "cancelled"


def test_reschedule_updates_appointment_time(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Alex Kim",
            "My phone is 415-555-0177",
            "Cleaning",
            "tomorrow at 3pm",
            "Yes",
        ],
    )
    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    original_start = appointment.start_time

    reschedule_state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        reschedule_state.session_id,
        ["Hi", "I want to reschedule my appointment", "My phone is 415-555-0177", "next Friday at 10am"],
    )

    db_session.refresh(appointment)
    assert appointment.start_time != original_start
    assert appointment.status == "scheduled"


def test_human_transfer_creates_notification(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(service, workspace.id, state.session_id, ["Hi", "I need to speak with a human"])

    notification = db_session.execute(
        select(Notification).where(Notification.workspace_id == workspace.id, Notification.type == "ai_handoff")
    ).scalar_one()
    assert notification.title


def test_session_from_another_workspace_is_rejected(db_session, workspace, service):
    other_ws = Workspace(name="Other Clinic", slug="other-clinic")
    db_session.add(other_ws)
    db_session.commit()

    state = service.start_session(workspace.id)
    with pytest.raises(UnknownConversationSessionError):
        service.handle_message(other_ws.id, state.session_id, "Hi")


def test_booking_in_one_workspace_is_invisible_to_another(db_session, workspace, service):
    other_ws = Workspace(name="Other Clinic", slug="other-clinic-2")
    db_session.add(other_ws)
    db_session.commit()

    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Pat Owen",
            "My phone is 415-555-0188",
            "Cleaning",
            "tomorrow at 3pm",
        ],
    )

    patients_in_other_workspace = db_session.execute(
        select(Patient).where(Patient.workspace_id == other_ws.id)
    ).scalars().all()
    assert patients_in_other_workspace == []


def test_workspace_specific_instructions_and_services_are_used(db_session, workspace, service):
    profile_services = service.engine  # sanity: engine exists
    assert profile_services is not None

    from app.ai.conversation.instructions import load_workspace_profile

    profile = load_workspace_profile(db_session, workspace.id)
    assert profile.instructions == "Be concise."
    assert set(profile.supported_languages) == {"en", "es"}
    assert set(profile.services) == {"Cleaning", "Checkup"}
