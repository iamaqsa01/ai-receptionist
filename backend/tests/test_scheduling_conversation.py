"""Phase 7 — availability/confirmation flow at the engine level: the
confirm-with-caller gate, provider selection, and confirmation-answer
classification. Pure in-memory simulated conversations, no DB."""

import uuid

import pytest

from app.ai.conversation.effects import BookAppointmentEffect
from app.ai.conversation.engine import ConversationEngine
from app.ai.conversation.instructions import WorkspaceAIProfile
from app.ai.conversation.state import ConversationState
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.nlu.confirmation import classify_confirmation
from app.ai.nlu.engine import NLUEngine


@pytest.fixture()
def profile():
    return WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="Sunrise Dental",
        instructions="...",
        supported_languages=["en", "es"],
        services=["Cleaning"],
        timezone="America/New_York",
    )


@pytest.fixture()
def profile_with_providers(profile):
    profile.providers = ["Dr. Lee", "Dr. Patel"]
    return profile


@pytest.fixture()
def engine():
    llm = MockLLMProvider()
    return ConversationEngine(nlu=NLUEngine(llm), llm=llm)


def new_state(profile) -> ConversationState:
    return ConversationState(session_id=uuid.uuid4(), workspace_id=profile.workspace_id)


def say(engine, state, profile, message):
    return engine.handle_message(state, message, profile)


# -- confirmation classifier (pure) -----------------------------------------------


def test_classify_confirmation_recognizes_yes_in_each_language():
    assert classify_confirmation("Yes, that's right", "en") == "yes"
    assert classify_confirmation("Sí, correcto", "es") == "yes"
    assert classify_confirmation("Oui, d'accord", "fr") == "yes"
    assert classify_confirmation("Ja, genau", "de") == "yes"


def test_classify_confirmation_recognizes_no():
    assert classify_confirmation("No, that's wrong", "en") == "no"
    assert classify_confirmation("No, incorrecto", "es") == "no"


def test_classify_confirmation_unclear_for_unrelated_text():
    assert classify_confirmation("What's the weather like?", "en") == "unclear"


# -- confirm-with-caller gate ------------------------------------------------------


_BASE_TURNS = ["Hi", "book an appointment", "My name is Jane Doe", "My phone is 415-555-0100", "Cleaning"]


def test_no_booking_effect_until_caller_confirms(engine, profile):
    state = new_state(profile)
    for msg in _BASE_TURNS:
        say(engine, state, profile, msg)
    r = say(engine, state, profile, "tomorrow at 3pm")

    assert state.pending_booking_confirmation is True
    assert all(not isinstance(e, BookAppointmentEffect) for e in r.effects)
    assert "book it" in r.reply.lower() or "shall i" in r.reply.lower()


def test_confirming_yes_emits_the_booking_effect(engine, profile):
    state = new_state(profile)
    for msg in [*_BASE_TURNS, "tomorrow at 3pm"]:
        say(engine, state, profile, msg)

    r = say(engine, state, profile, "Yes, that's correct")
    assert state.pending_booking_confirmation is False
    booking = next(e for e in r.effects if isinstance(e, BookAppointmentEffect))
    assert booking.service == "Cleaning"
    # The engine's own reply is only ever a provisional placeholder — it
    # never says "booked" or "confirmed" itself.
    assert "book" not in r.reply.lower() and "confirm" not in r.reply.lower()


def test_declining_clears_datetime_and_asks_again_keeping_other_info(engine, profile):
    state = new_state(profile)
    for msg in [*_BASE_TURNS, "tomorrow at 3pm"]:
        say(engine, state, profile, msg)

    r = say(engine, state, profile, "No, that's not right")
    assert state.pending_booking_confirmation is False
    assert state.appointment.when is None
    assert state.caller.name == "Jane Doe"  # kept
    assert state.caller.phone == "+14155550100"  # kept
    assert state.appointment.service == "Cleaning"  # kept
    assert "day" in r.reply.lower() or "time" in r.reply.lower()
    assert r.effects == []


def test_unclear_answer_asks_yes_or_no_and_keeps_waiting(engine, profile):
    state = new_state(profile)
    for msg in [*_BASE_TURNS, "tomorrow at 3pm"]:
        say(engine, state, profile, msg)

    r = say(engine, state, profile, "What's the weather like today?")
    assert state.pending_booking_confirmation is True  # still waiting
    assert r.effects == []
    assert "yes" in r.reply.lower() or "no" in r.reply.lower()

    # A clear answer on the next turn still works.
    r = say(engine, state, profile, "Yes")
    assert any(isinstance(e, BookAppointmentEffect) for e in r.effects)


# -- provider selection -------------------------------------------------------------


def test_provider_is_asked_for_when_workspace_has_configured_providers(engine, profile_with_providers):
    state = new_state(profile_with_providers)
    for msg in [*_BASE_TURNS, "tomorrow at 3pm"]:
        say(engine, state, profile_with_providers, msg)
    # datetime given before provider — provider must still be asked before confirming.
    assert state.pending_booking_confirmation is False
    assert "provider" in state.missing_fields
    last_reply = state.history[-1].text
    assert "provider" in last_reply.lower() or "Dr." in last_reply


def test_provider_not_asked_when_workspace_has_none_configured(engine, profile):
    state = new_state(profile)
    for msg in _BASE_TURNS:
        say(engine, state, profile, msg)
    say(engine, state, profile, "tomorrow at 3pm")
    assert state.pending_booking_confirmation is True  # went straight to confirmation


def test_caller_can_name_a_specific_provider(engine, profile_with_providers):
    state = new_state(profile_with_providers)
    for msg in ["Hi", "book an appointment", "My name is Jane Doe", "My phone is 415-555-0100"]:
        say(engine, state, profile_with_providers, msg)
    say(engine, state, profile_with_providers, "Dr. Lee please")
    assert state.appointment.provider == "Dr. Lee"


def test_caller_can_say_no_preference(engine, profile_with_providers):
    state = new_state(profile_with_providers)
    for msg in ["Hi", "book an appointment", "My name is Jane Doe", "My phone is 415-555-0100"]:
        say(engine, state, profile_with_providers, msg)
    say(engine, state, profile_with_providers, "no preference")
    assert state.appointment.provider == "no_preference"


# -- timezone handling ---------------------------------------------------------------


def test_extracted_datetime_is_anchored_to_workspace_timezone(engine, profile):
    state = new_state(profile)
    for msg in ["Hi", "book an appointment", "My name is Jane Doe", "My phone is 415-555-0100"]:
        say(engine, state, profile, msg)
    say(engine, state, profile, "tomorrow at 3pm")

    assert state.appointment.when is not None
    assert state.appointment.when.tzinfo is not None
    assert state.appointment.when.hour == 15  # 3pm in the workspace's own timezone, not UTC
