from dataclasses import dataclass

from langdetect import DetectorFactory, LangDetectException, detect_langs

from app.ai.language.catalog import get_language, list_registered_languages

# Deterministic detection (langdetect is otherwise seeded from system time).
DetectorFactory.seed = 0

# langdetect (statistical text ID) cannot tell the supported Perso-Arabic
# languages apart — Urdu, Pakistani Punjabi (Shahmukhi), Saraiki, Sindhi and
# Pashto all come back as one of these coarse codes. `normalize_language_code`
# collapses them onto whichever of those the workspace actually supports.
_PERSO_ARABIC_DETECTOR_CODES = {"ur", "fa", "ar", "pa", "ps", "sd", "skr", "pnb", "ckb"}

# Explicit "let's speak X" mentions — the only reliable way to switch
# *between* two Perso-Arabic languages mid-call, since their scripts are not
# separable statistically. Checked by ConversationEngine when a caller
# message is long enough to be a deliberate request. Keys are matched as
# case-insensitive substrings.
LANGUAGE_NAME_HINTS: dict[str, str] = {
    "english": "en", "انگریزی": "en", "انگلش": "en",
    "urdu": "ur", "اردو": "ur",
    "punjabi": "pa", "panjabi": "pa", "پنجابی": "pa", "پنجاب": "pa",
    "saraiki": "skr", "seraiki": "skr", "سرائیکی": "skr",
    "sindhi": "sd", "سندھی": "sd", "سنڌي": "sd",
    "pashto": "ps", "pushto": "ps", "pakhto": "ps", "پشتو": "ps", "پښتو": "ps",
    "spanish": "es", "español": "es", "espanol": "es",
    "french": "fr", "français": "fr", "francais": "fr",
    "german": "de", "deutsch": "de",
}


@dataclass
class LanguageDetection:
    code: str  # ISO 639-1 code, e.g. "en", "es"; "" if undetectable
    confidence: float  # 0.0 - 1.0


def detect_language(text: str) -> LanguageDetection:
    """Detects the language of a short piece of caller speech/text.

    Confidence is naturally lower for very short utterances ("Hola", "Oui")
    — callers are expected to say a few words, and the conversation engine
    treats low-confidence detections as "ask the caller to repeat", not as
    an error.
    """
    cleaned = text.strip()
    if not cleaned:
        return LanguageDetection(code="", confidence=0.0)

    try:
        candidates = detect_langs(cleaned)
    except LangDetectException:
        return LanguageDetection(code="", confidence=0.0)

    if not candidates:
        return LanguageDetection(code="", confidence=0.0)

    top = candidates[0]
    return LanguageDetection(code=top.lang, confidence=top.prob)


def normalize_language_code(code: str, supported_languages: list[str]) -> str:
    """Maps a raw langdetect code onto a language the workspace supports.

    - An exact match is returned untouched.
    - The coarse Perso-Arabic codes langdetect emits (ur/fa/ar/...) are
      collapsed onto a supported Perso-Arabic language: the workspace's
      preferred Urdu if it has it, otherwise the first supported
      Perso-Arabic language in `supported_languages` order.
    - Anything else is returned unchanged (so a confidently-detected but
      genuinely unsupported language still triggers the "please choose a
      supported language" flow in ConversationEngine).
    """
    if not code:
        return code
    if code in supported_languages:
        return code
    if code in _PERSO_ARABIC_DETECTOR_CODES:
        if "ur" in supported_languages:
            return "ur"
        for candidate in supported_languages:
            profile = get_language(candidate)
            if profile is not None and profile.perso_arabic:
                return candidate
    return code


def match_language_mention(text: str, supported_languages: list[str]) -> str | None:
    """Returns a supported language code if the caller explicitly named a
    language to switch to ("can we continue in Pashto"), else None. This is
    what makes switching *between* the Perso-Arabic languages possible at
    all — their scripts are statistically inseparable."""
    lowered = text.lower()
    for phrase, lang in LANGUAGE_NAME_HINTS.items():
        if phrase in lowered and lang in supported_languages:
            return lang
    return None


def registered_language_codes() -> list[str]:
    return list_registered_languages()
