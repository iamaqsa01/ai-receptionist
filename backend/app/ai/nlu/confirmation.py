"""Classifies a caller's reply to a yes/no confirmation prompt
("shall I go ahead and book it?"). Rule-based and multilingual, same
pattern as intent keyword matching — no LLM call."""

import re
from typing import Literal

ConfirmationAnswer = Literal["yes", "no", "unclear"]

_AFFIRMATIVE_WORDS: dict[str, list[str]] = {
    "en": ["yes", "yeah", "yep", "yup", "correct", "sure", "confirm", "go ahead", "that's right", "sounds good"],
    "es": ["sí", "si", "claro", "correcto", "confirmo", "adelante", "así es", "asi es"],
    "fr": ["oui", "d'accord", "confirmé", "confirme", "allez-y", "c'est ça", "c'est ca"],
    "de": ["ja", "genau", "bestätigt", "bestätige", "los", "passt"],
}

_NEGATIVE_WORDS: dict[str, list[str]] = {
    "en": ["no", "nope", "not correct", "cancel that", "wrong", "don't book"],
    "es": ["no", "incorrecto", "cancela eso", "no es correcto"],
    "fr": ["non", "incorrect", "annule", "ne réserve pas", "ne reserve pas"],
    "de": ["nein", "falsch", "storniere das", "nicht buchen"],
}


def _contains_word(lowered_text: str, phrase: str) -> bool:
    # Word-boundary match, not substring: a naive `phrase in text` check
    # would match "no" inside "know" or "si" inside dozens of ordinary
    # words, misclassifying an unrelated sentence as a yes/no answer.
    # Multi-word phrases ("that's right") still match as a literal
    # substring, since \b around a phrase with internal spaces/punctuation
    # behaves the same as a plain containment check for those.
    return re.search(rf"\b{re.escape(phrase)}\b", lowered_text) is not None


def classify_confirmation(text: str, language: str | None) -> ConfirmationAnswer:
    lowered = text.lower()
    language = language or "en"

    # Negative checked first: phrases like "no, that's not right" contain
    # no affirmative words, but a phrase like "not correct" could otherwise
    # collide with weaker matching — checking "no" first is the safer order.
    for word in _NEGATIVE_WORDS.get(language, []) + (_NEGATIVE_WORDS["en"] if language != "en" else []):
        if _contains_word(lowered, word):
            return "no"
    for word in _AFFIRMATIVE_WORDS.get(language, []) + (_AFFIRMATIVE_WORDS["en"] if language != "en" else []):
        if _contains_word(lowered, word):
            return "yes"
    return "unclear"
