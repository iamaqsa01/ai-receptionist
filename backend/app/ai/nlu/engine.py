import json
import logging

from app.ai.llm.base import LLMMessage, LLMProvider
from app.ai.nlu.entities import (
    extract_datetime,
    extract_name,
    extract_phone,
    extract_provider,
    extract_service,
    strip_phone_numbers,
)
from app.ai.nlu.keywords import INTENT_KEYWORDS, INTENT_PRIORITY
from app.ai.nlu.schema import ExtractedEntities, Intent, NLUResult

logger = logging.getLogger(__name__)

_RULE_BASED_CONFIDENCE_EXACT_LANGUAGE = 0.9
_RULE_BASED_CONFIDENCE_ENGLISH_FALLBACK = 0.6
_RULE_BASED_CONFIDENCE_DEFAULT = 0.3


class NLUEngine:
    """Intent detection + entity extraction. Deliberately kept independent
    of any single LLM provider: it always runs a fast, deterministic,
    multilingual rule-based pass first (so it works identically in mock
    mode and in tests), then — only for a real, available LLM provider —
    asks the model to refine the intent via a structured JSON completion.
    If that refinement fails or returns something unparseable, the
    rule-based result is kept, so a flaky/slow LLM call never breaks the
    conversation."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def analyze(
        self,
        text: str,
        language: str,
        known_services: list[str],
        known_providers: list[str] | None = None,
        timezone_name: str | None = None,
    ) -> NLUResult:
        intent, confidence = self._classify_intent(text, language)

        phone = extract_phone(text)
        # Date/name extraction run on the phone-stripped text: a run of
        # digits like a phone number is otherwise routinely misread as a
        # date by dateparser.
        cleaned_text = strip_phone_numbers(text) if phone else text

        entities = ExtractedEntities(
            caller_name=extract_name(cleaned_text, language),
            phone_number=phone,
            service=extract_service(text, known_services),
            provider=extract_provider(text, known_providers or [], language),
            appointment_datetime=extract_datetime(cleaned_text, language, timezone_name),
        )

        if self._llm.name != "mock" and self._llm.is_available():
            refined = self._refine_intent_with_llm(text, language, intent)
            if refined is not None:
                intent, confidence = refined

        return NLUResult(intent=intent, confidence=confidence, entities=entities)

    def _classify_intent(self, text: str, language: str) -> tuple[Intent, float]:
        lowered = text.lower()

        for intent in INTENT_PRIORITY:
            for keyword in INTENT_KEYWORDS.get(language, {}).get(intent, []):
                if keyword in lowered:
                    return intent, _RULE_BASED_CONFIDENCE_EXACT_LANGUAGE

        if language != "en":
            for intent in INTENT_PRIORITY:
                for keyword in INTENT_KEYWORDS.get("en", {}).get(intent, []):
                    if keyword in lowered:
                        return intent, _RULE_BASED_CONFIDENCE_ENGLISH_FALLBACK

        return Intent.GENERAL_INQUIRY, _RULE_BASED_CONFIDENCE_DEFAULT

    def _refine_intent_with_llm(
        self, text: str, language: str, fallback_intent: Intent
    ) -> tuple[Intent, float] | None:
        valid_intents = [i.value for i in Intent]
        system = (
            "Classify the caller's message into exactly one of these intents: "
            f"{', '.join(valid_intents)}. "
            'Respond with only a JSON object like {"intent": "...", "confidence": 0.0-1.0}. '
            "No other text."
        )
        try:
            response = self._llm.complete(
                [LLMMessage(role="system", content=system), LLMMessage(role="user", content=text)],
                temperature=0.0,
                max_tokens=60,
            )
            payload = json.loads(response.content.strip())
            intent_value = payload.get("intent")
            confidence = float(payload.get("confidence", 0.5))
            if intent_value in valid_intents:
                return Intent(intent_value), max(0.0, min(1.0, confidence))
        except Exception:
            logger.debug("LLM intent refinement failed; keeping rule-based intent", exc_info=True)
        return None
