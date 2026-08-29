"""Phase 9 — WhatsApp/email adapters: mock behavior, and factory fallback
to mock when the selected real provider's credentials are missing."""

import pytest

from app.core.config import Settings
from app.integrations.notifications.email_factory import get_email_provider
from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.email_sendgrid import SendGridEmailProvider
from app.integrations.notifications.exceptions import NotificationAuthError
from app.integrations.notifications.whatsapp_factory import get_whatsapp_provider
from app.integrations.notifications.whatsapp_meta import MetaWhatsAppProvider
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.integrations.notifications.whatsapp_twilio import TwilioWhatsAppProvider


# -- mock adapters -------------------------------------------------------------------


def test_mock_whatsapp_provider_always_succeeds_and_records_sends():
    provider = MockWhatsAppProvider()
    assert provider.is_available() is True

    result = provider.send("+15551234567", "Your appointment is confirmed.")
    assert result.provider_message_id
    assert provider.sent == [{"to": "+15551234567", "body": "Your appointment is confirmed.", "message_id": result.provider_message_id}]


def test_mock_whatsapp_provider_ids_are_unique_per_send():
    provider = MockWhatsAppProvider()
    first = provider.send("+15551234567", "one")
    second = provider.send("+15551234567", "two")
    assert first.provider_message_id != second.provider_message_id


def test_mock_email_provider_always_succeeds_and_records_sends():
    provider = MockEmailProvider()
    assert provider.is_available() is True

    result = provider.send("patient@example.com", "Confirmed", "See you then.")
    assert result.provider_message_id
    assert provider.sent[0]["to"] == "patient@example.com"
    assert provider.sent[0]["subject"] == "Confirmed"


# -- real adapters: unavailable without credentials -----------------------------------


def test_twilio_whatsapp_provider_unavailable_without_credentials():
    provider = TwilioWhatsAppProvider(account_sid="", auth_token="", from_number="")
    assert provider.is_available() is False
    with pytest.raises(NotificationAuthError):
        provider.send("+15551234567", "hi")


def test_twilio_whatsapp_provider_available_once_configured():
    provider = TwilioWhatsAppProvider(account_sid="AC123", auth_token="secret", from_number="+14155238886")
    assert provider.is_available() is True


def test_meta_whatsapp_provider_unavailable_without_credentials():
    provider = MetaWhatsAppProvider(access_token="", phone_number_id="")
    assert provider.is_available() is False
    with pytest.raises(NotificationAuthError):
        provider.send("+15551234567", "hi")


def test_meta_whatsapp_provider_available_once_configured():
    provider = MetaWhatsAppProvider(access_token="token", phone_number_id="123456")
    assert provider.is_available() is True


def test_sendgrid_provider_unavailable_without_credentials():
    provider = SendGridEmailProvider(api_key="", from_address="")
    assert provider.is_available() is False
    with pytest.raises(NotificationAuthError):
        provider.send("patient@example.com", "subj", "body")


def test_sendgrid_provider_available_once_configured():
    provider = SendGridEmailProvider(api_key="SG.abc", from_address="clinic@example.com")
    assert provider.is_available() is True


# -- factories: default to mock, fall back to mock on missing credentials -------------


def test_whatsapp_factory_defaults_to_mock():
    provider = get_whatsapp_provider(Settings(_env_file=None, whatsapp_provider="mock"))
    assert provider.name == "mock"


def test_whatsapp_factory_falls_back_to_mock_without_twilio_credentials():
    cfg = Settings(_env_file=None, whatsapp_provider="twilio", twilio_account_sid="", twilio_auth_token="")
    assert get_whatsapp_provider(cfg).name == "mock"


def test_whatsapp_factory_uses_twilio_once_configured():
    cfg = Settings(
        _env_file=None,
        whatsapp_provider="twilio",
        twilio_account_sid="AC123",
        twilio_auth_token="secret",
        whatsapp_from_number="+14155238886",
    )
    assert get_whatsapp_provider(cfg).name == "twilio_whatsapp"


def test_whatsapp_factory_falls_back_to_mock_without_meta_credentials():
    cfg = Settings(_env_file=None, whatsapp_provider="meta", meta_whatsapp_access_token="", meta_whatsapp_phone_number_id="")
    assert get_whatsapp_provider(cfg).name == "mock"


def test_whatsapp_factory_uses_meta_once_configured():
    cfg = Settings(
        _env_file=None,
        whatsapp_provider="meta",
        meta_whatsapp_access_token="token",
        meta_whatsapp_phone_number_id="123456",
    )
    assert get_whatsapp_provider(cfg).name == "meta_whatsapp"


def test_email_factory_defaults_to_mock():
    provider = get_email_provider(Settings(_env_file=None, email_provider="mock"))
    assert provider.name == "mock"


def test_email_factory_falls_back_to_mock_without_sendgrid_key():
    cfg = Settings(_env_file=None, email_provider="sendgrid", sendgrid_api_key="")
    assert get_email_provider(cfg).name == "mock"


def test_email_factory_uses_sendgrid_once_configured():
    cfg = Settings(_env_file=None, email_provider="sendgrid", sendgrid_api_key="SG.abc", email_from_address="clinic@example.com")
    assert get_email_provider(cfg).name == "sendgrid"
