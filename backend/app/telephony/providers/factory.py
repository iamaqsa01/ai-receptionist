import logging

from app.core.config import Settings, settings as default_settings
from app.telephony.providers.base import TelephonyAdapter
from app.telephony.providers.mock_adapter import MockTelephonyAdapter

logger = logging.getLogger(__name__)


def get_telephony_adapter(provider_name: str | None = None, cfg: Settings | None = None) -> TelephonyAdapter:
    cfg = cfg or default_settings
    provider_name = (provider_name or cfg.telephony_provider).lower().strip()

    if provider_name == "twilio":
        from app.telephony.providers.twilio_adapter import TwilioAdapter

        adapter = TwilioAdapter(cfg.twilio_account_sid, cfg.twilio_auth_token)
        if adapter.is_available():
            return adapter
        logger.warning(
            "TELEPHONY_PROVIDER=twilio but Twilio credentials are missing; falling back to mock adapter"
        )
        return MockTelephonyAdapter()

    if provider_name == "vapi":
        from app.telephony.providers.vapi_adapter import VapiAdapter

        adapter = VapiAdapter(cfg.vapi_api_key)
        if adapter.is_available():
            return adapter
        logger.warning(
            "TELEPHONY_PROVIDER=vapi but VAPI_API_KEY is missing; falling back to mock adapter"
        )
        return MockTelephonyAdapter()

    return MockTelephonyAdapter()
