import httpx

from app.integrations.notifications.base import MessageSendResult, WhatsAppProvider
from app.integrations.notifications.exceptions import (
    NotificationAPIError,
    NotificationAuthError,
    NotificationInvalidRecipientError,
    NotificationRateLimitError,
    NotificationTimeoutError,
)


class TwilioWhatsAppProvider(WhatsAppProvider):
    """Twilio's WhatsApp messaging API — the same Messages resource used
    for SMS, with a `whatsapp:` prefix on the from/to numbers, per Twilio's
    documented WhatsApp API. Not exercised against a live Twilio account in
    this environment (no credentials available) — MockWhatsAppProvider is
    what the test suite actually runs against."""

    name = "twilio_whatsapp"

    def __init__(self, account_sid: str, auth_token: str, from_number: str, timeout_seconds: float = 10.0) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self._account_sid and self._auth_token and self._from_number)

    def send(self, to: str, body: str) -> MessageSendResult:
        if not self.is_available():
            raise NotificationAuthError("Twilio WhatsApp provider is not configured")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        data = {
            "From": f"whatsapp:{self._from_number}",
            "To": f"whatsapp:{to}",
            "Body": body,
        }
        try:
            response = httpx.post(
                url, data=data, auth=(self._account_sid, self._auth_token), timeout=self._timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise NotificationTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise NotificationAPIError(str(exc)) from exc

        if response.status_code == 401:
            raise NotificationAuthError(response.text)
        if response.status_code == 429:
            raise NotificationRateLimitError(response.text)
        if response.status_code == 400:
            raise NotificationInvalidRecipientError(response.text)
        if response.status_code >= 400:
            raise NotificationAPIError(response.text, status_code=response.status_code)

        try:
            payload = response.json()
            message_sid = payload["sid"]
        except (ValueError, KeyError) as exc:
            raise NotificationAPIError(f"Unexpected Twilio response: {response.text}") from exc
        return MessageSendResult(provider_message_id=message_sid)
