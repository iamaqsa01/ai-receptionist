"""Approved-template sending for patient WhatsApp confirmations.

WhatsApp only allows free-form text inside the 24-hour window that opens
when a customer messages the business. A patient who telephoned the clinic
never opened one, so a booking confirmation reaches them as an approved
template or not at all.
"""

import pytest

from app.core.config import settings
from app.integrations.notifications import templates
from app.integrations.notifications.base import MessageSendResult, WhatsAppProvider
from app.integrations.notifications.whatsapp_meta import MetaWhatsAppProvider


class RecordingProvider(WhatsAppProvider):
    name = "recording"

    def __init__(self, supports: bool):
        self._supports = supports
        self.freeform: list[tuple[str, str]] = []
        self.templates: list[dict] = []

    def is_available(self) -> bool:
        return True

    def supports_templates(self) -> bool:
        return self._supports

    def send(self, to, body):
        self.freeform.append((to, body))
        return MessageSendResult(provider_message_id="freeform-1")

    def send_template(self, to, *, template_name, language, parameters, fallback_body):
        if not self._supports:
            return super().send_template(
                to,
                template_name=template_name,
                language=language,
                parameters=parameters,
                fallback_body=fallback_body,
            )
        self.templates.append(
            {"to": to, "name": template_name, "language": language, "parameters": parameters}
        )
        return MessageSendResult(provider_message_id="template-1")


def test_a_backend_without_template_support_still_sends_free_form():
    provider = RecordingProvider(supports=False)
    result = provider.send_template(
        "+923001234567",
        template_name="appointment_confirmation",
        language="en",
        parameters=["Ayesha", "dental cleaning", "Friday"],
        fallback_body="Hi Ayesha, your appointment is confirmed.",
    )
    assert result.provider_message_id == "freeform-1"
    assert provider.freeform == [("+923001234567", "Hi Ayesha, your appointment is confirmed.")]
    assert provider.templates == []


def test_meta_builds_the_payload_meta_expects(monkeypatch):
    provider = MetaWhatsAppProvider(access_token="t", phone_number_id="123")
    assert provider.supports_templates() is True

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"messages": [{"id": "wamid.1"}]}

        return Response()

    monkeypatch.setattr("app.integrations.notifications.whatsapp_meta.httpx.post", fake_post)

    result = provider.send_template(
        "+923001234567",
        template_name="appointment_confirmation",
        language="en",
        parameters=["Ayesha Malik", "dental cleaning", "Friday, September 04 at 9:30 AM"],
        fallback_body="unused",
    )
    assert result.provider_message_id == "wamid.1"
    payload = captured["json"]
    assert payload["type"] == "template"
    assert payload["to"] == "+923001234567"
    assert payload["template"]["name"] == "appointment_confirmation"
    assert payload["template"]["language"] == {"code": "en"}
    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "Ayesha Malik"},
        {"type": "text", "text": "dental cleaning"},
        {"type": "text", "text": "Friday, September 04 at 9:30 AM"},
    ]


def test_meta_free_form_payload_is_unchanged(monkeypatch):
    provider = MetaWhatsAppProvider(access_token="t", phone_number_id="123")
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"messages": [{"id": "wamid.2"}]}

        return Response()

    monkeypatch.setattr("app.integrations.notifications.whatsapp_meta.httpx.post", fake_post)
    provider.send("+923001234567", "hello")
    assert captured["json"]["type"] == "text"
    assert captured["json"]["text"] == {"body": "hello"}


def test_the_template_parameter_matches_the_wording_in_the_body():
    """{{3}} has to read the same as the free-form message it replaces."""
    from datetime import datetime, timezone

    start = datetime(2026, 9, 4, 9, 30, tzinfo=timezone.utc)
    body = templates.appointment_confirmation_body("Ayesha", "dental cleaning", start)
    assert templates.format_when(start) in body


def test_no_template_configured_means_free_form(monkeypatch):
    monkeypatch.setattr(settings, "meta_whatsapp_template_confirmation", "")
    from app.integrations.notifications.service import _patient_template_name

    assert _patient_template_name("appointment_confirmation") == ""


def test_configured_template_is_picked_per_event(monkeypatch):
    monkeypatch.setattr(settings, "meta_whatsapp_template_confirmation", "clinic_confirm")
    monkeypatch.setattr(settings, "meta_whatsapp_template_cancellation", "clinic_cancel")
    from app.integrations.notifications.service import _patient_template_name

    assert _patient_template_name("appointment_confirmation") == "clinic_confirm"
    assert _patient_template_name("appointment_cancellation") == "clinic_cancel"
    assert _patient_template_name("appointment_reminder") == ""
