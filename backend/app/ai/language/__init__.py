from app.ai.language.catalog import (
    LanguageProfile,
    get_language,
    list_registered_languages,
    register_language,
)
from app.ai.language.detector import (
    LanguageDetection,
    LANGUAGE_NAME_HINTS,
    detect_language,
    match_language_mention,
    normalize_language_code,
)
from app.ai.language.pakistan import register_pakistan_languages

# Register the Pakistan / South-Asian live-voice languages (ur, pa, skr, sd,
# ps) onto the same catalog the base module populated with en/es/fr/de. Done
# here rather than in catalog.py itself to keep that module's "one profile
# per register_language() call" shape unchanged.
register_pakistan_languages()

__all__ = [
    "LanguageProfile",
    "get_language",
    "list_registered_languages",
    "register_language",
    "register_pakistan_languages",
    "LanguageDetection",
    "LANGUAGE_NAME_HINTS",
    "detect_language",
    "match_language_mention",
    "normalize_language_code",
]
