"""Phase 6 — caller qualification wired into the conversation engine:
service/department identification, information validation, and the
'never invent missing information' / 'business rules outside the LLM'
guarantees. Pure in-memory simulated conversations, no DB."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.ai.conversation.effects import BookAppointmentEffect, UpsertLeadEffect
from app.ai.conversation.engine import ConversationEngine
from app.ai.conversation.instructions import WorkspaceAIProfile
from app.ai.conversation.state import ConversationState
from app.ai.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.nlu.engine import NLUEngine


@pytest.fixture()
def profile():
    return WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="Sunrise Dental",
        instructions="You are a receptionist for a dental clinic.",
        supported_languages=["en", "es"],
        services=["Cleaning", "Root Canal"],
        service_departments={"Cleaning": "Hygiene", "Root Canal": "Endodontics"},
    )


@pytest.fixture()
def engine():
    llm = MockLLMProvider()
    return ConversationEngine(nlu=NLUEngine(llm), llm=llm)


def new_state(profile) -> ConversationState:
    return ConversationState(session_id=uuid.uuid4(), workspace_id=profile.workspace_id)


def say(engine, state, profile, message):
    return engine.handle_message(state, message, profile)


def run_booking_up_to_datetime(engine, state, profile, service="Root Canal", phone="415-555-0100"):
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "I would like to book an appointment")
    say(engine, state, profile, "My name is Jane Doe")
    say(engine, state, profile, f"My phone is {phone}")
    return say(engine, state, profile, service)


# -- service/department identification -------------------------------------------


def test_service_and_department_are_identified_from_workspace_config(engine, profile):
    state = new_state(profile)
    run_booking_up_to_datetime(engine, state, profile, service="Root Canal")
    assert state.appointment.service == "Root Canal"
    assert state.appointment.department == "Endodontics"


def test_department_is_none_when_service_has_no_configured_mapping(engine):
    profile = WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="No Departments Clinic",
        instructions="...",
        supported_languages=["en"],
        services=["Cleaning"],
        service_departments={},  # workspace never configured a mapping
    )
    state = new_state(profile)
    run_booking_up_to_datetime(engine, state, profile, service="Cleaning")
    assert state.appointment.service == "Cleaning"
    assert state.appointment.department is None  # never guessed


def test_unrecognized_service_is_not_accepted(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "I would like to book an appointment")
    say(engine, state, profile, "My name is Jane Doe")
    say(engine, state, profile, "My phone is 415-555-0100")
    r = say(engine, state, profile, "I need a massage")
    assert state.appointment.service is None
    assert "service" in r.reply.lower()


# -- validation ------------------------------------------------------------------


def test_past_datetime_is_rejected_with_explanation_and_not_booked(engine, profile):
    state = new_state(profile)
    run_booking_up_to_datetime(engine, state, profile, service="Cleaning")
    r = say(engine, state, profile, "yesterday at 3pm")

    assert state.appointment.when is None
    assert r.effects == []
    assert "future" in r.reply.lower() or "passed" in r.reply.lower()


def test_after_past_datetime_rejection_a_valid_future_one_completes_booking(engine, profile):
    state = new_state(profile)
    run_booking_up_to_datetime(engine, state, profile, service="Cleaning")
    say(engine, state, profile, "yesterday at 3pm")
    r = say(engine, state, profile, "tomorrow at 3pm")
    assert state.pending_booking_confirmation is True

    r = say(engine, state, profile, "Yes")
    booking_effects = [e for e in r.effects if isinstance(e, BookAppointmentEffect)]
    assert len(booking_effects) == 1
    when = booking_effects[0].when
    now = datetime.now(when.tzinfo) if when.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
    assert when > now


# -- lead creation/update ---------------------------------------------------------


def test_lead_is_created_once_phone_is_known_mid_booking(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "I would like to book an appointment")
    say(engine, state, profile, "My name is Jane Doe")
    r = say(engine, state, profile, "My phone is 415-555-0100")

    lead_effects = [e for e in r.effects if isinstance(e, UpsertLeadEffect)]
    assert len(lead_effects) == 1
    assert lead_effects[0].status == "qualifying"
    assert lead_effects[0].phone == "+14155550100"


def test_no_lead_effect_before_phone_is_known(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "I would like to book an appointment")
    assert all(not isinstance(e, UpsertLeadEffect) for e in r.effects)

    r = say(engine, state, profile, "My name is Jane Doe")
    assert all(not isinstance(e, UpsertLeadEffect) for e in r.effects)


def test_lead_stays_qualifying_through_confirmation_engine_never_marks_converted(engine, profile):
    """Lead status only ever escalates to "converted" once the database
    write actually succeeds (receptionist_service.py, tested in
    test_qualification_service.py) — the engine itself, having no DB
    access, never claims a lead converted on its own."""
    state = new_state(profile)
    run_booking_up_to_datetime(engine, state, profile, service="Cleaning")
    r = say(engine, state, profile, "tomorrow at 3pm")

    lead_effects = [e for e in r.effects if isinstance(e, UpsertLeadEffect)]
    assert len(lead_effects) == 1
    assert lead_effects[0].status == "qualifying"

    # Even after the caller confirms, the engine's own effect stream for
    # that turn carries no lead-conversion effect — only the booking
    # attempt (see test_qualification_service.py for the DB-level proof
    # that a successful write is what actually converts the lead).
    r = say(engine, state, profile, "Yes")
    assert all(not isinstance(e, UpsertLeadEffect) for e in r.effects)


def test_general_inquiry_with_known_phone_creates_a_new_lead(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi, my phone is 415-555-0199, do you take walk-ins?")
    # A phone-bearing general inquiry is a prospect worth capturing.
    found = [t for t in state.history if t.role == "caller"]
    assert found

    state2 = new_state(profile)
    say(engine, state2, profile, "Hi")
    r = say(engine, state2, profile, "My phone number is 415-555-0199, just asking about your hours")
    lead_effects = [e for e in r.effects if isinstance(e, UpsertLeadEffect)]
    assert len(lead_effects) == 1
    assert lead_effects[0].status == "new"


def test_cancellation_caller_never_produces_a_lead_effect(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "I need to cancel my appointment")
    r = say(engine, state, profile, "My phone is 415-555-0100")
    assert all(not isinstance(e, UpsertLeadEffect) for e in r.effects)


# -- never invent missing information --------------------------------------------


class LyingLLMProvider(LLMProvider):
    """A fake LLM that fabricates plausible-looking caller details in its
    free-text reply — simulating the exact failure mode 'never invent
    missing patient information' guards against."""

    name = "lying"

    def is_available(self) -> bool:
        return True

    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        return LLMResponse(
            content="Sure thing! I've got you down as John Fabricated at 555-000-1111, see you then."
        )


def test_llm_generated_text_never_populates_structured_caller_fields(profile):
    engine = ConversationEngine(nlu=NLUEngine(LyingLLMProvider()), llm=LyingLLMProvider())
    state = new_state(profile)

    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "What are your hours?")

    # The LLM's fabricated name/phone appear only in prose, never as
    # structured state — because _handle_open_ended's LLM output is used
    # solely as reply text, and entity extraction only ever runs against
    # what the *caller* actually said.
    assert state.caller.name is None
    assert state.caller.phone is None
    assert r.effects == []  # nothing was created from the fabrication


def test_booking_effect_only_ever_carries_real_extracted_values(engine, profile):
    state = new_state(profile)
    r = run_booking_up_to_datetime(engine, state, profile, service="Cleaning")
    # Still missing a date/time — must not have booked with any placeholder.
    assert all(not isinstance(e, BookAppointmentEffect) for e in r.effects)
    assert state.appointment.when is None

    r = say(engine, state, profile, "tomorrow at 3pm")
    assert all(not isinstance(e, BookAppointmentEffect) for e in r.effects)  # awaiting confirmation

    r = say(engine, state, profile, "Yes")
    booking = next(e for e in r.effects if isinstance(e, BookAppointmentEffect))
    assert booking.caller_name == "Jane Doe"  # exactly what the caller said, nothing synthesized
    assert booking.phone == "+14155550100"


# -- business rules outside the LLM ------------------------------------------------


def test_qualification_decisions_are_identical_regardless_of_llm_provider(profile):
    """Validation, department resolution, missing-field ordering, and lead
    routing are all rule-based (app.ai.qualification / NLUEngine's keyword
    classifier) — swapping the LLM provider must not change any of them,
    since the LLM is never consulted for these decisions."""

    def run_with(llm: LLMProvider) -> ConversationState:
        engine = ConversationEngine(nlu=NLUEngine(llm), llm=llm)
        state = new_state(profile)
        run_booking_up_to_datetime(engine, state, profile, service="Root Canal")
        say(engine, state, profile, "yesterday at 3pm")
        say(engine, state, profile, "tomorrow at 3pm")
        return state

    mock_state = run_with(MockLLMProvider())
    lying_state = run_with(LyingLLMProvider())

    assert mock_state.appointment.service == lying_state.appointment.service == "Root Canal"
    assert mock_state.appointment.department == lying_state.appointment.department == "Endodontics"
    assert mock_state.caller.name == lying_state.caller.name == "Jane Doe"
    assert mock_state.caller.phone == lying_state.caller.phone == "+14155550100"
