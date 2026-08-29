import logging

from app.core.config import Settings, settings as default_settings
from app.integrations.notifications.base import EmailProvider
from app.integrations.notifications.email_mock import default_mock_email_provider

logger = logging.getLogger(__name__)


def get_email_provider(cfg: Settings | None = None) -> EmailProvider:
    cfg = cfg or default_settings
    provider_name = cfg.email_provider.lower().strip()

    if provider_name == "sendgrid":
        from app.integrations.notifications.email_sendgrid import SendGridEmailProvider

        provider = SendGridEmailProvider(
            cfg.sendgrid_api_key, cfg.email_from_address, timeout_seconds=cfg.notification_timeout_seconds
        )
        if provider.is_available():
            return provider
        logger.warning(
            "EMAIL_PROVIDER=sendgrid but SENDGRID_API_KEY is missing; falling back to mock email"
        )
        return default_mock_email_provider

    return default_mock_email_provider
