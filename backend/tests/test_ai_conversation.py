import uuid

import pytest

from app.ai.conversation.effects import BookAppointmentEffect, TransferToHumanEffect
from app.ai.conversation.engine import ConversationEngine
from app.ai.conversation.instructions import WorkspaceAIProfile
from app.ai.conversation.state import ConversationState, ConversationStatus
from app.ai.llm.base import LLMMessage
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.nlu.engine import NLUEngine
from app.ai.nlu.schema import Intent


@pytest.fixture()
def profile():
    return WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="Sunrise Dental",
        instructions="You are a receptionist for a dental clinic.",
        supported_languages=["en", "es"],
        services=["Cleaning", "Checkup"],
    )


@pytest.fixture()
def engine():
    llm = MockLLMProvider()
    return ConversationEngine(nlu=NLUEngine(llm), llm=llm)


def new_state(profile) -> ConversationState:
    return ConversationState(session_id=uuid.uuid4(), workspace_id=profile.workspace_id)


def say(engine, state, profile, message):
    return engine.handle_message(state, message, profile)


# -- booking ---------------------------------------------------------------


def test_booking_flow_collects_missing_info_in_order_then_confirms(engine, profile):
    state = new_state(profile)

    r = say(engine, state, profile, "Hi")
    assert "Sunrise Dental" in r.reply

    r = say(engine, state, profile, "I would like to book an appointment")
    assert "name" in r.reply.lower()
    assert state.missing_fields == ["name", "phone", "service", "datetime"]

    r = say(engine, state, profile, "My name is Jane Doe")
    assert "phone" in r.reply.lower()

    r = say(engine, state, profile, "My phone is 415-555-0100")
    assert "service" in r.reply.lower()
    assert "Cleaning" in r.reply

    r = say(engine, state, profile, "Cleaning")
    assert "day" in r.reply.lower() or "time" in r.reply.lower()

    r = say(engine, state, profile, "Next Tuesday at 3pm")
    # All info collected: the engine asks for confirmation before booking
    # anything (Phase 7) — no BookAppointmentEffect is emitted yet (a
    # qualifying Lead upsert still is — see test_qualification*.py).
    assert all(not isinstance(e, BookAppointmentEffect) for e in r.effects)
    assert "book it" in r.reply.lower() or "shall i" in r.reply.lower()
    assert state.pending_booking_confirmation is True

    r = say(engine, state, profile, "Yes")
    # A completed booking also emits a Lead-conversion effect (Phase 6 —
    # see test_qualification.py for dedicated lead-lifecycle coverage).
    booking_effects = [e for e in r.effects if isinstance(e, BookAppointmentEffect)]
    assert len(booking_effects) == 1
    effect = booking_effects[0]
    assert effect.caller_name == "Jane Doe"
    assert effect.phone == "+14155550100"
    assert effect.service == "Cleaning"
    assert effect.when is not None
    # The engine's own reply here is only ever a provisional placeholder —
    # it never claims success. See test_qualification_service.py /
    # test_scheduling_* for the outcome-aware reply produced after the
    # actual database write.
    assert "Jane Doe" not in r.reply


def test_appointment_datetime_is_preserved_as_structured_value_not_just_text(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "book an appointment")
    say(engine, state, profile, "My name is Ana Lee")
    say(engine, state, profile, "My phone is 415-555-0111")
    say(engine, state, profile, "Checkup")
    say(engine, state, profile, "tomorrow at 3pm")

    assert state.appointment.when is not None
    assert state.appointment.when.hour == 15


# -- cancellation ------------------------------------------------------------


def test_cancellation_flow(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "I need to cancel my appointment")
    assert "phone" in r.reply.lower()

    r = say(engine, state, profile, "My phone is 415-555-0100")
    assert len(r.effects) == 1
    assert r.effects[0].phone == "+14155550100"


# -- reschedule ---------------------------------------------------------------


def test_reschedule_flow_targets_new_when_not_when(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "I want to reschedule my appointment")
    say(engine, state, profile, "My phone is 415-555-0100")
    r = say(engine, state, profile, "Move it to next Wednesday at 10am")

    assert state.appointment.when is None  # never touched — no local record of the old time
    assert state.appointment.new_when is not None
    assert len(r.effects) == 1
    assert r.effects[0].new_when == state.appointment.new_when


# -- human transfer ------------------------------------------------------------


def test_human_transfer_intent(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "Can I speak to a human please")

    assert state.status == ConversationStatus.NEEDS_HUMAN
    assert len(r.effects) == 1
    assert r.effects[0].reason
    assert r.effects[0].trigger == "caller_request"


# -- Phase 10: the other escalation triggers ------------------------------------


def test_unsupported_request_transfers_to_human(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "I have a billing question about my last invoice")

    assert state.status == ConversationStatus.NEEDS_HUMAN
    assert len(r.effects) == 1
    assert r.effects[0].trigger == "unsupported_request"


def test_clinic_escalation_keyword_transfers_to_human():
    profile = WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="Sunrise Dental",
        instructions="You are a receptionist for a dental clinic.",
        supported_languages=["en"],
        services=["Cleaning"],
        escalation_keywords=["emergency"],
    )
    llm = MockLLMProvider()
    engine = ConversationEngine(nlu=NLUEngine(llm), llm=llm)
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "This is an emergency, my tooth is bleeding badly")

    assert state.status == ConversationStatus.NEEDS_HUMAN
    assert len(r.effects) == 1
    assert r.effects[0].trigger == "clinic_rule"
    assert "emergency" in r.effects[0].reason


def test_clinic_escalation_rule_is_not_triggered_without_matching_keyword(engine, profile):
    # Default `profile` fixture has no escalation_keywords configured.
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "This is an emergency")

    assert state.status != ConversationStatus.NEEDS_HUMAN
    assert r.effects == []


def test_repeated_unclear_messages_before_any_intent_transfers_to_human(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "asdkfj qwoeiru random gibberish one")
    say(engine, state, profile, "another confusing thing zzz")
    r = say(engine, state, profile, "still not making sense blah")

    assert state.status == ConversationStatus.NEEDS_HUMAN
    assert len(r.effects) == 1
    assert r.effects[0].trigger == "repeated_misunderstanding"


def test_unclear_message_strikes_do_not_fire_mid_booking_flow(engine, profile):
    """Slot-filling answers ("Jane Doe", a phone number, ...) naturally have
    no intent keywords of their own and must never be mistaken for
    "repeated misunderstanding" once a real request is already underway —
    regression guard for the bug this exact scenario caused during Phase 10
    development (see engine.py's `state.intent is None` guard)."""
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    say(engine, state, profile, "I would like to book an appointment")
    say(engine, state, profile, "My name is Jane Doe")
    say(engine, state, profile, "My phone is 415-555-0100")
    r = say(engine, state, profile, "Cleaning")

    assert state.status != ConversationStatus.NEEDS_HUMAN
    assert not any(isinstance(e, TransferToHumanEffect) for e in r.effects)


# -- clinical guardrail --------------------------------------------------------


def test_clinical_request_is_refused_not_answered(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "Can you diagnose my headache and prescribe something for it")

    assert r.effects == []
    lowered = r.reply.lower()
    assert "not able to give medical advice" in lowered
    assert "clinical staff" in lowered


def test_clinical_request_in_spanish_is_also_refused(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hola, quiero agendar una cita")
    r = say(engine, state, profile, "Puede darme un diagnóstico y recetarme algo para el dolor")

    assert r.effects == []
    assert "diagnóstico médico" in r.reply or "no puedo dar" in r.reply.lower()


# -- multilingual ---------------------------------------------------------------


def test_spanish_conversation_detected_and_responded_to_in_spanish(engine, profile):
    state = new_state(profile)
    r = say(engine, state, profile, "Hola, quiero reservar una cita para una limpieza")
    assert state.language == "es"
    assert any(ch in r.reply for ch in "áéíóúñ¿")


def test_language_switch_mid_conversation(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hello, I need some help with an appointment today")
    assert state.language == "en"

    # A real language switch means the caller actually starts speaking the
    # other language — not an English sentence that merely mentions it
    # (that correctly stays classified as English; see the "not derailed"
    # test above for the flip side of this behavior).
    say(engine, state, profile, "Hola, prefiero continuar esta llamada en español por favor")
    assert state.language == "es"


def test_short_slot_answers_do_not_derail_established_language(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hola, quiero reservar una cita")
    assert state.language == "es"

    # Short, digit-heavy answers are routinely misdetected by statistical
    # language ID at high confidence — they must not flip the conversation
    # into "unsupported language" mid-flow.
    say(engine, state, profile, "Me llamo Juan Perez")
    r = say(engine, state, profile, "Mi telefono es 415-555-0199")
    assert state.language == "es"
    assert state.status != ConversationStatus.AWAITING_LANGUAGE_CHOICE
    assert state.caller.phone == "+14155550199"


def test_unsupported_language_prompts_choice_and_lists_supported_ones(engine, profile):
    state = new_state(profile)
    r = say(engine, state, profile, "Bonjour, je voudrais prendre un rendez-vous pour une consultation")

    assert state.status == ConversationStatus.AWAITING_LANGUAGE_CHOICE
    assert "English" in r.reply
    assert "Español" in r.reply


def test_workspace_can_configure_a_narrower_language_set(engine):
    profile = WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="English Only Clinic",
        instructions="...",
        supported_languages=["en"],
        services=["Checkup"],
    )
    state = new_state(profile)
    r = say(engine, state, profile, "Hola, quiero reservar una cita para una consulta médica")
    assert state.status == ConversationStatus.AWAITING_LANGUAGE_CHOICE
    assert "English" in r.reply
    assert "Español" not in r.reply


# -- missing-information handling -----------------------------------------------


def test_reschedule_missing_info_asked_before_new_time(engine, profile):
    state = new_state(profile)
    say(engine, state, profile, "Hi")
    r = say(engine, state, profile, "reschedule my appointment")
    assert state.missing_fields == ["phone", "new_datetime"]
    assert "phone" in r.reply.lower()


# -- LLM abstraction / mock mode --------------------------------------------------


def test_mock_provider_is_always_available_without_credentials():
    provider = MockLLMProvider()
    assert provider.is_available()
    response = provider.complete([LLMMessage(role="user", content="hello")])
    assert response.content


def test_nlu_engine_rule_based_classification_works_without_any_llm_call():
    nlu = NLUEngine(MockLLMProvider())
    result = nlu.analyze("I'd like to book an appointment", "en", ["Cleaning"])
    assert result.intent == Intent.APPOINTMENT_BOOKING


def test_llm_provider_factory_defaults_to_mock_without_credentials():
    from app.core.config import Settings
    from app.ai.llm.factory import get_llm_provider

    cfg = Settings(_env_file=None, llm_provider="openai", openai_api_key="")
    provider = get_llm_provider(cfg)
    assert provider.name == "mock"

    cfg = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key="")
    provider = get_llm_provider(cfg)
    assert provider.name == "mock"
