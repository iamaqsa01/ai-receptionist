from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MessageSendResult:
    provider_message_id: str


class WhatsAppProvider(ABC):
    """Every WhatsApp backend (Twilio, Meta Cloud API, mock) implements this
    same interface. NotificationService only ever depends on this
    abstraction — never a provider SDK directly. Every method may raise one
    of the app.integrations.notifications.exceptions types."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def send(self, to: str, body: str) -> MessageSendResult: ...

    def supports_templates(self) -> bool:
        """Whether this backend can send a pre-approved template.

        WhatsApp only permits free-form text inside the 24-hour window
        that opens when the customer messages the business. A patient
        who telephoned the clinic never did that, so a booking
        confirmation has to go out as an approved template or not at
        all. Backends that cannot do templates keep sending free-form.
        """
        return False

    def send_template(
        self,
        to: str,
        *,
        template_name: str,
        language: str,
        parameters: list[str],
        fallback_body: str,
    ) -> MessageSendResult:
        """Send a template, or fall back to free-form text.

        The fallback keeps the mock and Twilio backends working
        unchanged, and keeps local development free of any template
        approval step.
        """
        return self.send(to, fallback_body)


class EmailProvider(ABC):
    """Every email backend (SendGrid, mock) implements this same
    interface. Same abstraction split as WhatsAppProvider above."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> MessageSendResult: ...
