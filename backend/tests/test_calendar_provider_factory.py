from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.integrations.calendar.exceptions import CalendarAuthError
from app.integrations.calendar.factory import get_calendar_provider
from app.integrations.calendar.mock_provider import MockCalendarProvider


def test_factory_defaults_to_mock():
    provider = get_calendar_provider(Settings(_env_file=None, calendar_provider="mock"))
    assert provider.name == "mock"


def test_factory_falls_back_to_mock_without_service_account_json():
    cfg = Settings(_env_file=None, calendar_provider="google", google_service_account_json="")
    provider = get_calendar_provider(cfg)
    assert provider.name == "mock"


def test_factory_falls_back_to_mock_on_invalid_json():
    cfg = Settings(_env_file=None, calendar_provider="google", google_service_account_json="not valid json{{{")
    provider = get_calendar_provider(cfg)
    assert provider.name == "mock"


def test_google_provider_unavailable_without_credentials():
    from app.integrations.calendar.google_provider import GoogleCalendarProvider

    provider = GoogleCalendarProvider(service_account_info=None)
    assert provider.is_available() is False
    with pytest.raises(CalendarAuthError):
        provider.check_availability("primary", datetime.now(timezone.utc), datetime.now(timezone.utc))


def test_google_provider_available_once_credentials_are_set():
    from app.integrations.calendar.google_provider import GoogleCalendarProvider

    provider = GoogleCalendarProvider(service_account_info={"type": "service_account", "project_id": "fake"})
    assert provider.is_available() is True


def test_google_provider_restores_utc_timezone_after_naive_database_round_trip():
    from app.integrations.calendar.google_provider import _google_datetime

    assert _google_datetime(datetime(2026, 9, 30, 3, 0)) == "2026-09-30T03:00:00+00:00"
