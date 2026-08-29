"""Phase 6 — caller qualification end-to-end through ReceptionistService and
a real (SQLite) database: Lead create/update, Patient record updates, and
department resolution landing in the persisted Appointment."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.conversation.store import InMemoryConversationStore
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.receptionist_service import ReceptionistService
from app.models.ai_agent import AIAgent
from app.models.appointment import Appointment
from app.models.lead import Lead
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Qualification Clinic", slug="qualification-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", is_active=True))
    db_session.add(Service(workspace_id=ws.id, name="Root Canal", is_active=True))
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="Front Desk AI",
            is_active=True,
            config={
                "instructions": "Be concise.",
                "supported_languages": ["en", "es"],
                "service_departments": {"Cleaning": "Hygiene", "Root Canal": "Endodontics"},
            },
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


# -- lead lifecycle ----------------------------------------------------------------


def test_lead_created_once_phone_known_then_converted_on_booking(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "I would like to book an appointment", "My name is Jane Doe", "My phone is 415-555-0100"],
    )

    lead = db_session.execute(
        select(Lead).where(Lead.workspace_id == workspace.id, Lead.phone == "+14155550100")
    ).scalar_one()
    assert lead.status == "qualifying"
    assert lead.name == "Jane Doe"

    run_turns(service, workspace.id, state.session_id, ["Cleaning", "tomorrow at 3pm", "Yes"])

    db_session.refresh(lead)
    assert lead.status == "converted"


def test_lead_status_never_downgrades(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Jane Doe",
            "My phone is 415-555-0100",
            "Cleaning",
            "tomorrow at 3pm",
            "Yes",
        ],
    )
    lead = db_session.execute(
        select(Lead).where(Lead.workspace_id == workspace.id, Lead.phone == "+14155550100")
    ).scalar_one()
    assert lead.status == "converted"

    # A brand new call from the same caller, this time just a general
    # inquiry — must not knock the lead's status back down from "converted".
    second_call = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        second_call.session_id,
        ["Hi", "My phone is 415-555-0100, just wondering about parking"],
    )
    db_session.refresh(lead)
    assert lead.status == "converted"


def test_general_inquiry_lead_is_isolated_per_workspace(db_session, workspace, service):
    other_ws = Workspace(name="Other Clinic", slug="other-clinic-qual")
    db_session.add(other_ws)
    db_session.commit()

    state = service.start_session(workspace.id)
    run_turns(service, workspace.id, state.session_id, ["Hi", "My phone is 415-555-0177, do you take walk-ins?"])

    leads_in_other_workspace = db_session.execute(
        select(Lead).where(Lead.workspace_id == other_ws.id)
    ).scalars().all()
    assert leads_in_other_workspace == []

    lead = db_session.execute(
        select(Lead).where(Lead.workspace_id == workspace.id, Lead.phone == "+14155550177")
    ).scalar_one()
    assert lead.status == "new"


# -- patient record update --------------------------------------------------------


def test_returning_caller_with_different_name_updates_existing_patient_record(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Jane Doe",
            "My phone is 415-555-0155",
            "Cleaning",
            "tomorrow at 3pm",
            "Yes",
        ],
    )
    patient = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id, Patient.phone == "+14155550155")
    ).scalar_one()
    assert patient.first_name == "Jane"
    original_id = patient.id

    # Same phone number calls again, this time giving a fuller/corrected name.
    second_call = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        second_call.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Jane Anne Doe",
            "My phone is 415-555-0155",
            "Root Canal",
            "next Friday at 10am",
            "Yes",
        ],
    )

    db_session.refresh(patient)
    assert patient.id == original_id  # same record updated, not duplicated
    assert patient.last_name == "Anne Doe"

    patients_with_this_phone = db_session.execute(
        select(Patient).where(Patient.workspace_id == workspace.id, Patient.phone == "+14155550155")
    ).scalars().all()
    assert len(patients_with_this_phone) == 1  # no duplicate created


# -- department resolution lands in the persisted appointment ---------------------


def test_department_is_recorded_on_the_persisted_appointment(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        [
            "Hi",
            "book an appointment",
            "My name is Sam Rivera",
            "My phone is 415-555-0188",
            "Root Canal",
            "tomorrow at 3pm",
            "Yes",
        ],
    )
    appointment = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalar_one()
    assert "Endodontics" in appointment.notes


# -- never invent missing information (DB-level) -----------------------------------


def test_no_patient_or_appointment_created_while_information_is_incomplete(db_session, workspace, service):
    state = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        state.session_id,
        ["Hi", "book an appointment", "My name is Incomplete Caller"],  # never gives phone/service/datetime
    )

    assert db_session.execute(select(Patient).where(Patient.workspace_id == workspace.id)).scalars().all() == []
    assert (
        db_session.execute(select(Appointment).where(Appointment.workspace_id == workspace.id)).scalars().all()
        == []
    )


# -- multiple simulated calls, end to end -----------------------------------------


def test_multiple_simulated_calls_against_the_same_workspace(db_session, workspace, service):
    """Several distinct, independent calls in a row — a completed booking,
    a Spanish-language inquiry that becomes a lead, a caller who abandons
    mid-flow, and a returning patient who reschedules — verifying they
    don't interfere with each other and the database ends up in exactly
    the state each call's outcome implies."""

    # Call 1: full English booking.
    call1 = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        call1.session_id,
        [
            "Hi",
            "I'd like to book an appointment",
            "My name is Alice Nguyen",
            "My phone is 415-555-0101",
            "Cleaning",
            "tomorrow at 9am",
            "Yes",
        ],
    )

    # Call 2: Spanish-language general inquiry — becomes a "new" lead, no booking.
    call2 = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        call2.session_id,
        ["Hola, mi telefono es 415-555-0102, quisiera saber sus precios"],
    )

    # Call 3: caller abandons after giving only a name — no lead (no phone
    # yet), no patient, nothing persisted.
    call3 = service.start_session(workspace.id)
    run_turns(service, workspace.id, call3.session_id, ["Hi", "book an appointment", "My name is Bob Stone"])

    # Call 4: Alice (from Call 1) calls back later and reschedules.
    call4 = service.start_session(workspace.id)
    run_turns(
        service,
        workspace.id,
        call4.session_id,
        ["Hi", "I need to reschedule my appointment", "My phone is 415-555-0101", "next Friday at 2pm"],
    )

    patients = db_session.execute(select(Patient).where(Patient.workspace_id == workspace.id)).scalars().all()
    assert {p.phone for p in patients} == {"+14155550101"}  # only Alice ever became a patient

    appointments = db_session.execute(
        select(Appointment).where(Appointment.workspace_id == workspace.id)
    ).scalars().all()
    assert len(appointments) == 1
    assert appointments[0].status == "scheduled"
    assert appointments[0].start_time.weekday() == 4  # rescheduled to a Friday

    leads = db_session.execute(select(Lead).where(Lead.workspace_id == workspace.id)).scalars().all()
    lead_phones = {lead.phone: lead.status for lead in leads}
    assert lead_phones.get("+14155550101") == "converted"  # Alice's booking converted her lead
    assert lead_phones.get("+14155550102") == "new"  # the Spanish inquiry
    assert "+14155550188" not in lead_phones  # Bob never gave a phone — no ghost lead
    assert len(leads) == 2
