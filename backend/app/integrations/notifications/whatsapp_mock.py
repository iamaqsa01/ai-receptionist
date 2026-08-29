import uuid

from app.integrations.notifications.base import MessageSendResult, WhatsAppProvider


class MockWhatsAppProvider(WhatsAppProvider):
    """Deterministic, offline stand-in for a real WhatsApp API, used
    automatically when no WhatsApp credentials are configured. Always
    succeeds and records every send in memory so tests can assert on it."""

    name = "mock"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def is_available(self) -> bool:
        return True

    def send(self, to: str, body: str) -> MessageSendResult:
        message_id = f"mock-wa-{uuid.uuid4().hex}"
        self.sent.append({"to": to, "body": body, "message_id": message_id})
        return MessageSendResult(provider_message_id=message_id)


# Process-wide default, same rationale as
# app.integrations.calendar.mock_provider.default_mock_calendar_provider.
default_mock_whatsapp_provider = MockWhatsAppProvider()
