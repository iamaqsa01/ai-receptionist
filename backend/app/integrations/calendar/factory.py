import json
import logging

from app.core.config import Settings, settings as default_settings
from app.integrations.calendar.base import CalendarProvider
from app.integrations.calendar.mock_provider import default_mock_calendar_provider

logger = logging.getLogger(__name__)


def get_calendar_provider(cfg: Settings | None = None) -> CalendarProvider:
    cfg = cfg or default_settings
    provider_name = cfg.calendar_provider.lower().strip()

    if provider_name == "google":
        from app.integrations.calendar.google_provider import GoogleCalendarProvider

        service_account_info = None
        if cfg.google_service_account_json:
            try:
                service_account_info = json.loads(cfg.google_service_account_json)
            except (TypeError, ValueError):
                logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON; falling back to mock calendar")

        provider = GoogleCalendarProvider(service_account_info, timeout_seconds=cfg.google_calendar_timeout_seconds)
        if provider.is_available():
            return provider
        logger.warning(
            "CALENDAR_PROVIDER=google but GOOGLE_SERVICE_ACCOUNT_JSON is missing/invalid; "
            "falling back to mock calendar"
        )
        return default_mock_calendar_provider

    return default_mock_calendar_provider
