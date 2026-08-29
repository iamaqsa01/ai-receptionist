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


class EmailProvider(ABC):
    """Every email backend (SendGrid, mock) implements this same
    interface. Same abstraction split as WhatsAppProvider above."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> MessageSendResult: ...
