"""Phase 16 — multilingual live voice.

Covers: the South-Asian language catalog is complete; the detector collapses
the statistically-inseparable Perso-Arabic codes onto a supported language;
the conversation engine keeps an English caller in English, moves an Urdu
caller to Urdu, honours an explicit mid-call switch, and the live-voice
session hands the established language to TTS (and flags an STT restart).
"""

import asyncio
import base64
import json
import uuid

import pytest

from app.ai.conversation.engine import ConversationEngine
from app.ai.conversation.instructions import WorkspaceAIProfile, render_system_prompt
from app.ai.conversation.state import ConversationState
from app.ai.language.catalog import TEMPLATE_KEYS, get_language, list_registered_languages
from app.ai.language.detector import match_language_mention, normalize_language_code
from app.ai.llm.mock_provider import MockLLMProvider
from app.ai.nlu.engine import NLUEngine
from app.ai.receptionist_service import ReceptionistService
from app.ai.speech.stt.mock_provider import MockSTTProvider
from app.ai.speech.tts.mock_provider import MockTTSProvider
from app.ai.conversation.store import InMemoryConversationStore
from app.models.service import Service
from app.models.workspace import Workspace
from app.telephony.providers.mock_adapter import MockTelephonyAdapter
from app.telephony.session import CallSession

PK_LANGS = ["ur", "pa", "skr", "sd", "ps"]


@pytest.fixture()
def profile():
    return WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="Shifa Clinic",
        instructions="You are a receptionist for a clinic.",
        supported_languages=["en", "ur", "pa", "skr", "sd", "ps"],
        services=["Checkup", "Cleaning"],
    )


@pytest.fixture()
def engine():
    llm = MockLLMProvider()
    return ConversationEngine(nlu=NLUEngine(llm), llm=llm)


def new_state(profile):
    return ConversationState(session_id=uuid.uuid4(), workspace_id=profile.workspace_id)


# -- catalog ------------------------------------------------------------------


def test_all_required_languages_registered():
    registered = set(list_registered_languages())
    assert {"en", *PK_LANGS}.issubset(registered)


@pytest.mark.parametrize("code", PK_LANGS)
def test_language_profile_defines_every_template(code):
    profile = get_language(code)
    assert profile is not None
    missing = [key for key in TEMPLATE_KEYS if key not in profile.templates]
    assert missing == []
    assert profile.perso_arabic is True
    assert profile.native_name


# -- detector normalization -------------------------------------------------


def test_perso_arabic_codes_collapse_onto_supported_urdu():
    # langdetect reports Urdu / Punjabi-Shahmukhi / Saraiki as "ur" and
    # Sindhi / Pashto as "fa"; all must map to a supported language.
    assert normalize_language_code("ur", ["en", "ur"]) == "ur"
    assert normalize_language_code("fa", ["en", "ur"]) == "ur"
    assert normalize_language_code("ar", ["en", "ur"]) == "ur"


def test_perso_arabic_falls_back_to_first_supported_perso_arabic_when_no_urdu():
    assert normalize_language_code("fa", ["en", "ps"]) == "ps"


def test_genuinely_unsupported_language_is_left_untouched():
    # A confidently-detected Latin-script language the workspace doesn't
    # support must NOT be silently rewritten — the engine needs it to
    # trigger the "please choose a supported language" flow.
    assert normalize_language_code("fr", ["en", "ur"]) == "fr"


def test_explicit_language_mention_matches_only_supported():
    assert match_language_mention("please continue in Pashto", ["en", "ur", "ps"]) == "ps"
    assert match_language_mention("بات پنجابی میں کریں", ["en", "pa"]) == "pa"
    assert match_language_mention("let's speak Urdu", ["en", "es"]) is None


# -- engine: per-turn language ------------------------------------------------


def test_english_caller_stays_in_english(engine, profile):
    state = new_state(profile)
    engine.handle_message(state, "Hello, I would like to book an appointment for a checkup", profile)
    assert state.language == "en"


def _has_arabic_script(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ" for ch in text)


def test_urdu_caller_is_answered_in_urdu(engine, profile):
    state = new_state(profile)
    r = engine.handle_message(state, "السلام علیکم، مجھے چیک اپ کے لیے اپائنٹمنٹ چاہیے", profile)
    assert state.language == "ur"
    # Reply is rendered from the Urdu template set (Perso-Arabic script).
    assert _has_arabic_script(r.reply)


def test_local_language_caller_maps_to_supported_language(engine, profile):
    # Sindhi text (langdetect -> "fa") must resolve to a supported language,
    # never leave the caller stuck at "unsupported language".
    state = new_state(profile)
    engine.handle_message(state, "مان سڀاڻي ڊاڪٽر سان ملاقات ڪرڻ چاهيان ٿو مهرباني ڪري", profile)
    assert state.language in profile.supported_languages
    assert state.status.value != "awaiting_language_choice"


def test_caller_can_switch_language_mid_call_by_asking(engine, profile):
    state = new_state(profile)
    engine.handle_message(state, "Hello, I need help with an appointment today please", profile)
    assert state.language == "en"
    engine.handle_message(state, "Sorry, can we please continue this call in Pashto instead", profile)
    assert state.language == "ps"


def test_unsupported_language_still_prompts_a_choice(engine):
    profile = WorkspaceAIProfile(
        workspace_id=uuid.uuid4(),
        clinic_name="EN/UR Clinic",
        instructions="...",
        supported_languages=["en", "ur"],
        services=["Checkup"],
    )
    state = new_state(profile)
    r = engine.handle_message(state, "Bonjour, je voudrais prendre un rendez-vous medical pour demain", profile)
    assert state.status.value == "awaiting_language_choice"
    assert "English" in r.reply


# -- system prompt ---------------------------------------------------------


def test_system_prompt_states_multilingual_policy(profile):
    prompt = render_system_prompt(profile)
    assert "Language policy" in prompt
    assert "Detect the language the caller is CURRENTLY speaking" in prompt
    assert "Do not switch to English" in prompt
    assert "Never claim to support a language that is not in the list" in prompt
    # Lists the supported languages by name.
    assert "Urdu" in prompt and "Pashto" in prompt


# -- live voice: TTS gets the established language --------------------------


def _drive_call(session, sender, texts):
    async def run():
        await session.handle_raw_message(
            json.dumps({"event": "start", "call_id": "c1", "from": "+15550000001", "to": "+15550000002"})
        )
        for i, text in enumerate(texts):
            await session.handle_raw_message(
                json.dumps(
                    {"event": "media", "call_id": "c1", "payload": base64.b64encode(text.encode()).decode()}
                )
            )
            for _ in range(300):
                if len(sender.sent) >= i + 1:
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError(f"no reply for turn {i}")
        await session.close()

    asyncio.run(run())


class RecordingTTS(MockTTSProvider):
    def __init__(self):
        self.calls = []

    async def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        self.calls.append(language)
        return text.encode("utf-8")


class RecordingSender:
    def __init__(self):
        self.sent = []

    async def __call__(self, message):
        self.sent.append(message)


def test_tts_is_called_with_the_detected_call_language(db_session):
    ws = Workspace(name="Voice PK Clinic", slug="voice-pk-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Checkup", is_active=True))
    db_session.commit()

    tts = RecordingTTS()
    sender = RecordingSender()
    session = CallSession(
        workspace_id=ws.id,
        adapter=MockTelephonyAdapter(),
        stt=MockSTTProvider(),
        tts=tts,
        receptionist=ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore()),
        send=sender,
    )
    _drive_call(session, sender, ["السلام علیکم، مجھے اپائنٹمنٹ کے بارے میں مدد چاہیے آج"])

    assert tts.calls, "TTS was never invoked"
    assert tts.calls[-1] == "ur"
    # And the session flagged the STT stream to be reconfigured for Urdu.
    assert session._stt_language == "ur" or session._pending_stt_language == "ur"
