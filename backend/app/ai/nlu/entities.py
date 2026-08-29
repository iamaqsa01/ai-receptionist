import re
from datetime import datetime, timedelta

import dateparser
import phonenumbers

# Name-extraction patterns are intentionally simple, regex-based heuristics
# per language ("my name is X" / "je m'appelle X" / ...) — enough to collect
# structured caller info without needing an LLM round-trip for the common
# case. Real providers may supply a better name via LLM-based refinement in
# NLUEngine; this is the deterministic fallback used in mock mode and as a
# first pass otherwise. New languages extend this dict, same as keywords.py.
_NAME_PATTERNS: dict[str, list[str]] = {
    "en": [
        r"my name is ([A-Za-z' -]{2,60})",
        r"i am ([A-Za-z' -]{2,60})",
        r"i'm ([A-Za-z' -]{2,60})",
        r"this is ([A-Za-z' -]{2,60})",
    ],
    "es": [
        r"me llamo ([A-Za-zÀ-ÿ' -]{2,60})",
        r"mi nombre es ([A-Za-zÀ-ÿ' -]{2,60})",
        r"soy ([A-Za-zÀ-ÿ' -]{2,60})",
    ],
    "fr": [
        r"je m'appelle ([A-Za-zÀ-ÿ' -]{2,60})",
        r"mon nom est ([A-Za-zÀ-ÿ' -]{2,60})",
    ],
    "de": [
        r"mein name ist ([A-Za-zÀ-ÿäöüßÄÖÜ' -]{2,60})",
        r"ich bin ([A-Za-zÀ-ÿäöüßÄÖÜ' -]{2,60})",
    ],
}

# Trailing words that commonly get captured by the greedy name patterns above
# and should be trimmed back off (language-specific "and I'd like to..." etc).
_NAME_STOPWORDS = {
    "en": [" and", " i'd", " i would", " calling", " speaking"],
    "es": [" y ", " quisiera", " llamando"],
    "fr": [" et ", " je voudrais", " j'appelle"],
    "de": [" und ", " ich möchte", " ich rufe"],
}


def extract_phone(text: str, region_hint: str = "US") -> str | None:
    """Phone numbers are digits regardless of spoken language, so a single
    libphonenumber pass (Google's phone-number library) covers every
    language without per-language logic."""
    try:
        for match in phonenumbers.PhoneNumberMatcher(text, region_hint):
            return phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None
    return None


def strip_phone_numbers(text: str, region_hint: str = "US") -> str:
    """Removes validated phone-number substrings from text.

    dateparser will happily (mis)interpret a run of digits like a phone
    number as a date or time, so date/name extraction always run on this
    cleaned text rather than the raw caller utterance. Using
    PhoneNumberMatcher (which validates against real numbering plans)
    rather than a blunt "strip long digit runs" regex avoids accidentally
    eating a legitimate date like "2026-09-01".
    """
    try:
        matches = list(phonenumbers.PhoneNumberMatcher(text, region_hint))
    except Exception:
        return text
    if not matches:
        return text

    cleaned = text
    for match in reversed(matches):  # remove from the end so earlier spans stay valid
        cleaned = cleaned[: match.start] + " " + cleaned[match.end :]
    return cleaned


# "next <weekday>" style filler words. PREFER_DATES_FROM="future" already
# resolves a bare weekday name to its next occurrence, so stripping these
# is safe — and necessary, since dateparser's own parser is unreliable on
# the combination of these fillers with a time-of-day (see extract_datetime).
_RELATIVE_FILLER_WORDS: dict[str, list[str]] = {
    "en": ["next "],
    "es": ["el próximo ", "el proximo ", "próximo ", "proximo "],
    "fr": ["le prochain ", "la prochaine ", "prochain ", "prochaine "],
    "de": ["nächsten ", "nächste ", "kommenden "],
}


def _strip_relative_fillers(text: str, language: str | None) -> str:
    cleaned = text
    for filler in _RELATIVE_FILLER_WORDS.get(language or "en", []):
        cleaned = re.sub(re.escape(filler), " ", cleaned, flags=re.IGNORECASE)
    return cleaned


# A genuine date/time mention contains a digit or one of these signal
# words; dateparser will otherwise occasionally hallucinate a date out of
# an ordinary word with no time reference at all (e.g. "hours" on its own,
# as in "just asking about your hours", parses as a nonsense date/time).
# This is a cheap pre-filter, not a replacement for the real parsing logic
# below — it only rules out attempting to parse text that couldn't
# possibly contain a real date/time mention.
_DATE_SIGNAL_WORDS: dict[str, set[str]] = {
    "en": {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "today", "tomorrow", "yesterday", "tonight", "noon", "midnight",
        "morning", "afternoon", "evening", "am", "pm",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    },
    "es": {
        "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo",
        "hoy", "mañana", "manana", "ayer", "noche", "mediodía", "mediodia", "medianoche",
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    },
    "fr": {
        "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
        "aujourd'hui", "demain", "hier", "soir", "midi", "minuit",
        "janvier", "février", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    },
    "de": {
        "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
        "heute", "morgen", "gestern", "abend", "mittag", "mitternacht",
        "januar", "februar", "märz", "marz", "april", "mai", "juni", "juli",
        "august", "september", "oktober", "november", "dezember",
    },
}


# Ordered Monday(0)..Sunday(6) to match datetime.weekday() — used solely to
# scope/drive the past-date correction below to phrases naming a weekday,
# as opposed to a specific calendar date (a different, unrelated problem).
_WEEKDAY_NAMES: dict[str, list[str]] = {
    "en": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "de": ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"],
}
# Spelling variants (accents caller/ASR text may or may not include) mapped
# to the canonical index in the list above.
_WEEKDAY_ALIASES: dict[str, dict[str, int]] = {
    "es": {"miercoles": 2, "sabado": 5},
}


def _weekday_index(text: str, language: str | None) -> int | None:
    lowered = text.lower()
    lang = language or "en"
    for index, name in enumerate(_WEEKDAY_NAMES.get(lang, [])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return index
    for alias, index in _WEEKDAY_ALIASES.get(lang, {}).items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return index
    return None


def _looks_like_a_date_phrase(text: str, language: str | None) -> bool:
    if any(ch.isdigit() for ch in text):
        return True
    lowered = text.lower()
    signal_words = _DATE_SIGNAL_WORDS.get(language or "en", set()) | _DATE_SIGNAL_WORDS["en"]
    # Word-boundary match, not substring: a naive `word in lowered` check
    # matches "am" inside "name" or "pm" inside "shipment", which sent
    # ordinary sentences like "My name is Patient One" into the date parser
    # and produced a hallucinated date from text that never mentioned one.
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in signal_words)


def extract_datetime(text: str, language: str | None, timezone_name: str | None = None) -> datetime | None:
    """dateparser natively understands dates/times phrased in many
    languages ('Tuesday at 3pm', 'el martes a las 3pm', ...), which is what
    lets us preserve structured date/time info regardless of the language
    being spoken.

    `timezone_name` (an IANA zone like "America/New_York") is the calling
    workspace's own timezone — a caller says "3pm" meaning 3pm at the
    clinic, not 3pm UTC or 3pm wherever the server happens to run. Passing
    it through dateparser's TIMEZONE/RETURN_AS_TIMEZONE_AWARE settings
    means every extracted datetime is timezone-aware and anchored to the
    right clock, so validation (is this in the past?) and storage are both
    unambiguous. Omitting it falls back to naive local-server time.

    A direct whole-string parse is tried first (most reliable); a "next
    <weekday>" style filler is stripped beforehand since dateparser's
    relative-date parsing is inconsistent with it present (and unnecessary,
    since PREFER_DATES_FROM="future" already yields the next occurrence of a
    bare weekday). If the whole string doesn't parse (typically because of
    leading conversational filler — "Move it to Wednesday at 10am" — dateparser's
    own `search_dates` was tried here first, but it has a reproducible bug
    that mis-resolves some "<weekday> at <N>am" phrasings to a nonsense date
    months out; a plain parse of successively shorter suffixes (dropping one
    leading word at a time) finds the same real date without that bug.
    """
    languages = [language] if language else None
    dateparser_settings: dict[str, object] = {"PREFER_DATES_FROM": "future"}
    if timezone_name:
        dateparser_settings["TIMEZONE"] = timezone_name
        dateparser_settings["RETURN_AS_TIMEZONE_AWARE"] = True
    cleaned = _strip_relative_fillers(text, language)

    if not _looks_like_a_date_phrase(cleaned, language):
        return None

    words = cleaned.split()
    for start in range(len(words)):
        candidate = " ".join(words[start:])
        try:
            result = dateparser.parse(candidate, languages=languages, settings=dateparser_settings)
        except Exception:
            result = None
        if result is not None:
            return _roll_forward_if_stale_weekday(result, candidate, language)

    return None


def _roll_forward_if_stale_weekday(result: datetime, candidate: str, language: str | None) -> datetime:
    """Safety net for a reproducible dateparser bug: `PREFER_DATES_FROM:
    "future"` is supposed to guarantee a weekday-name phrase ("Tuesday at
    3pm", "next Tuesday") resolves to an upcoming date, but when *today*
    happens to be that same weekday, dateparser can resolve it to the
    *wrong weekday entirely*, weeks in the past (reproduced directly:
    parsing "Tuesday at 3pm" on an actual Tuesday returned a Saturday over
    three weeks prior — not just a past Tuesday). Since only the date part
    is unreliable here, this recomputes the date from scratch with plain
    Python arithmetic (today + however many days to the named weekday,
    rolling to next week if that lands on today but today's time-of-day
    has already passed) and keeps dateparser's own (correctly parsed)
    time-of-day. Scoped to weekday-name phrases only — a specific calendar
    date ("August 1st") resolving to the past is a different (year-
    ambiguity) problem this fix must not touch."""
    weekday_index = _weekday_index(candidate, language)
    if weekday_index is None:
        return result

    now_reference = datetime.now(result.tzinfo) if result.tzinfo else datetime.now()
    days_ahead = (weekday_index - now_reference.weekday()) % 7
    corrected = now_reference.replace(
        hour=result.hour, minute=result.minute, second=result.second, microsecond=0
    ) + timedelta(days=days_ahead)
    if corrected <= now_reference:
        corrected += timedelta(days=7)
    return corrected


def extract_name(text: str, language: str) -> str | None:
    patterns = _NAME_PATTERNS.get(language, []) + (
        _NAME_PATTERNS.get("en", []) if language != "en" else []
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip()
        for stopword in _NAME_STOPWORDS.get(language, []):
            idx = candidate.lower().find(stopword.strip().lower())
            if idx > 0:
                candidate = candidate[:idx].strip()
        if candidate:
            return " ".join(part.capitalize() for part in candidate.split())
    return None


def extract_service(text: str, known_services: list[str]) -> str | None:
    """Language-agnostic substring match against the workspace's own
    service names/synonyms (already in whatever language the clinic
    configured them in)."""
    lowered = text.lower()
    for service in known_services:
        if service.lower() in lowered:
            return service
    return None


# "No preference" phrasing — a caller who doesn't care which provider they
# see. Recognized distinctly from "not yet answered" so the engine can move
# on rather than re-asking forever.
_NO_PREFERENCE_PHRASES: dict[str, list[str]] = {
    "en": ["no preference", "any provider", "anyone", "doesn't matter", "don't care", "whoever"],
    "es": ["sin preferencia", "cualquiera", "no importa", "quien sea"],
    "fr": ["peu importe", "n'importe qui", "aucune préférence", "aucune preference"],
    "de": ["keine präferenz", "egal", "irgendwer"],
}


def extract_provider(text: str, known_providers: list[str], language: str | None = None) -> str | None:
    """Language-agnostic substring match against the workspace's own
    provider names, same approach as extract_service. Returns the literal
    string "no_preference" (never a real provider name) when the caller
    explicitly says they don't have one — the engine treats that as a
    valid, distinct answer rather than a still-missing field."""
    lowered = text.lower()
    for phrase in _NO_PREFERENCE_PHRASES.get(language or "en", []) + _NO_PREFERENCE_PHRASES["en"]:
        if phrase in lowered:
            return "no_preference"
    for provider in known_providers:
        if provider.lower() in lowered:
            return provider
    return None
