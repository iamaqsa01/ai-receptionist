from datetime import datetime, timezone

import pytest

from app.integrations.calendar.exceptions import CalendarAPIError
from app.integrations.calendar.mock_provider import MockCalendarProvider


def dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc)


@pytest.fixture()
def provider():
    return MockCalendarProvider()


def test_is_available_always_true():
    assert MockCalendarProvider().is_available() is True


def test_check_availability_true_when_calendar_empty(provider):
    assert provider.check_availability("cal-1", dt(9), dt(10)) is True


def test_create_event_returns_an_id_and_blocks_that_slot(provider):
    event = provider.create_event("cal-1", summary="Cleaning", description="...", start=dt(9), end=dt(10))
    assert event.external_event_id
    assert provider.check_availability("cal-1", dt(9), dt(10)) is False


def test_create_event_does_not_itself_reject_overlaps(provider):
    """Mirrors real Google Calendar API semantics: creating an event never
    checks for conflicts on its own — callers must call check_availability
    first (which CalendarSyncService always does)."""
    provider.create_event("cal-1", summary="A", description="", start=dt(9), end=dt(10))
    second = provider.create_event("cal-1", summary="B", description="", start=dt(9), end=dt(10))
    assert second.external_event_id


def test_different_calendars_are_independent(provider):
    provider.create_event("cal-1", summary="A", description="", start=dt(9), end=dt(10))
    assert provider.check_availability("cal-2", dt(9), dt(10)) is True


def test_update_event_moves_the_blocked_slot(provider):
    event = provider.create_event("cal-1", summary="A", description="", start=dt(9), end=dt(10))
    provider.update_event("cal-1", event.external_event_id, start=dt(14), end=dt(15))

    assert provider.check_availability("cal-1", dt(9), dt(10)) is True
    assert provider.check_availability("cal-1", dt(14), dt(15)) is False


def test_update_unknown_event_raises_api_error(provider):
    with pytest.raises(CalendarAPIError):
        provider.update_event("cal-1", "does-not-exist", start=dt(9), end=dt(10))


def test_cancel_event_frees_the_slot(provider):
    event = provider.create_event("cal-1", summary="A", description="", start=dt(9), end=dt(10))
    provider.cancel_event("cal-1", event.external_event_id)
    assert provider.check_availability("cal-1", dt(9), dt(10)) is True


def test_cancel_is_idempotent_for_already_gone_events(provider):
    provider.cancel_event("cal-1", "never-existed")  # must not raise
