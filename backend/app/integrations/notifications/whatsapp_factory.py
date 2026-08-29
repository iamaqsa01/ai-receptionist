import logging

from app.core.config import Settings, settings as default_settings
from app.integrations.notifications.base import WhatsAppProvider
from app.integrations.notifications.whatsapp_mock import default_mock_whatsapp_provider

logger = logging.getLogger(__name__)


def get_whatsapp_provider(cfg: Settings | None = None) -> WhatsAppProvider:
    cfg = cfg or default_settings
    provider_name = cfg.whatsapp_provider.lower().strip()

    if provider_name == "twilio":
        from app.integrations.notifications.whatsapp_twilio import TwilioWhatsAppProvider

        provider = TwilioWhatsAppProvider(
            cfg.twilio_account_sid,
            cfg.twilio_auth_token,
            cfg.whatsapp_from_number,
            timeout_seconds=cfg.notification_timeout_seconds,
        )
        if provider.is_available():
            return provider
        logger.warning(
            "WHATSAPP_PROVIDER=twilio but Twilio credentials/WHATSAPP_FROM_NUMBER are missing; "
            "falling back to mock WhatsApp"
        )
        return default_mock_whatsapp_provider

    if provider_name == "meta":
        from app.integrations.notifications.whatsapp_meta import MetaWhatsAppProvider

        provider = MetaWhatsAppProvider(
            cfg.meta_whatsapp_access_token,
            cfg.meta_whatsapp_phone_number_id,
            timeout_seconds=cfg.notification_timeout_seconds,
        )
        if provider.is_available():
            return provider
        logger.warning(
            "WHATSAPP_PROVIDER=meta but Meta WhatsApp credentials are missing; falling back to mock WhatsApp"
        )
        return default_mock_whatsapp_provider

    return default_mock_whatsapp_provider
