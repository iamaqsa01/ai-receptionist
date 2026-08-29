"""Caller-qualification business rules: validating collected information and
resolving which department a service belongs to.

Deliberately pure, deterministic Python — no LLM call anywhere in this
module, and no I/O. This is what "keep business rules outside the LLM"
means concretely: whether a phone number is valid, whether a proposed
appointment time is in the past, and which department a service belongs to
are all decided here, identically regardless of which LLM provider (or
none) is configured. The LLM is never asked to validate or decide these
things, and — since these functions only ever accept already-extracted
values or return None — the AI Receptionist can never use them to invent a
value that wasn't actually provided by the caller.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import phonenumbers


@dataclass
class ValidationResult:
    valid: bool
    reason: str | None = None  # machine-readable failure code, e.g. "in_the_past"

    def __bool__(self) -> bool:
        return self.valid


def validate_phone(phone_e164: str | None) -> ValidationResult:
    if not phone_e164:
        return ValidationResult(False, "missing")
    try:
        parsed = phonenumbers.parse(phone_e164, None)
    except phonenumbers.NumberParseException:
        return ValidationResult(False, "unparseable")
    if not phonenumbers.is_valid_number(parsed):
        return ValidationResult(False, "invalid")
    return ValidationResult(True)


def validate_name(name: str | None) -> ValidationResult:
    if not name or not name.strip():
        return ValidationResult(False, "missing")
    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 120:
        return ValidationResult(False, "implausible_length")
    if not any(ch.isalpha() for ch in cleaned):
        return ValidationResult(False, "no_letters")
    return ValidationResult(True)


def validate_service(service: str | None, known_services: list[str]) -> ValidationResult:
    if not service:
        return ValidationResult(False, "missing")
    if known_services and service not in known_services:
        return ValidationResult(False, "unknown_service")
    return ValidationResult(True)


def validate_future_datetime(when: datetime | None) -> ValidationResult:
    if when is None:
        return ValidationResult(False, "missing")
    now = datetime.now(when.tzinfo) if when.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
    if when < now:
        return ValidationResult(False, "in_the_past")
    return ValidationResult(True)


def resolve_department(service: str | None, department_map: dict[str, str]) -> str | None:
    """Looks up which department a service belongs to, from the workspace's
    own configured mapping. Returns None (never a guess) when the service
    is unknown or the workspace hasn't configured departments at all."""
    if not service:
        return None
    return department_map.get(service)


# A lead's journey only ever moves forward: new -> qualifying -> converted.
# This ordering is what stops a later, less-informative turn (e.g. the
# caller says "hi" again) from clobbering a more advanced status a previous
# turn already reached.
LEAD_STATUS_PRIORITY = {"new": 0, "qualifying": 1, "converted": 2}


def next_lead_status(current: str | None, proposed: str) -> str:
    if current is None:
        return proposed
    current_rank = LEAD_STATUS_PRIORITY.get(current, 0)
    proposed_rank = LEAD_STATUS_PRIORITY.get(proposed, 0)
    return proposed if proposed_rank > current_rank else current
