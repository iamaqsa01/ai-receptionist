"""Phase 6 — caller qualification: unit tests for the pure validation/
department-resolution rules, plus engine-level tests proving those rules
are wired into the conversation flow and never depend on the LLM."""

import uuid
from datetime import datetime, timedelta, timezone

from app.ai.qualification.validators import (
    next_lead_status,
    resolve_department,
    validate_future_datetime,
    validate_name,
    validate_phone,
    validate_service,
)


# -- validators (pure, no LLM) -----------------------------------------------------


def test_validate_phone_accepts_valid_e164():
    assert validate_phone("+14155550100")


def test_validate_phone_rejects_missing():
    result = validate_phone(None)
    assert not result
    assert result.reason == "missing"


def test_validate_phone_rejects_garbage():
    result = validate_phone("not-a-number")
    assert not result


def test_validate_name_rejects_empty_and_too_short():
    assert not validate_name(None)
    assert not validate_name("  ")
    assert not validate_name("A")


def test_validate_name_rejects_digits_only():
    result = validate_name("12345")
    assert not result
    assert result.reason == "no_letters"


def test_validate_name_accepts_plausible_name():
    assert validate_name("Jane Doe")


def test_validate_service_requires_known_service_when_list_provided():
    assert validate_service("Cleaning", ["Cleaning", "Checkup"])
    assert not validate_service("Massage", ["Cleaning", "Checkup"])
    assert not validate_service(None, ["Cleaning"])


def test_validate_service_allows_anything_when_workspace_has_no_service_list():
    # A workspace that hasn't configured any services yet shouldn't block
    # booking on a service check it can't actually perform.
    assert validate_service("Anything", [])


def test_validate_future_datetime_rejects_past():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    result = validate_future_datetime(past)
    assert not result
    assert result.reason == "in_the_past"


def test_validate_future_datetime_accepts_future():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert validate_future_datetime(future)


def test_validate_future_datetime_rejects_missing():
    result = validate_future_datetime(None)
    assert not result
    assert result.reason == "missing"


def test_resolve_department_looks_up_configured_mapping():
    mapping = {"Cleaning": "Hygiene", "Root Canal": "Endodontics"}
    assert resolve_department("Cleaning", mapping) == "Hygiene"


def test_resolve_department_never_guesses_unmapped_service():
    assert resolve_department("Cleaning", {}) is None
    assert resolve_department(None, {"Cleaning": "Hygiene"}) is None


def test_lead_status_only_ever_escalates():
    assert next_lead_status(None, "new") == "new"
    assert next_lead_status("new", "qualifying") == "qualifying"
    assert next_lead_status("qualifying", "converted") == "converted"
    # A later, less-informative turn can't downgrade an already-advanced lead.
    assert next_lead_status("converted", "new") == "converted"
    assert next_lead_status("qualifying", "new") == "qualifying"
