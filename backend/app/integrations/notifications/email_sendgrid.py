import httpx

from app.integrations.notifications.base import EmailProvider, MessageSendResult
from app.integrations.notifications.exceptions import (
    NotificationAPIError,
    NotificationAuthError,
    NotificationInvalidRecipientError,
    NotificationRateLimitError,
    NotificationTimeoutError,
)


class SendGridEmailProvider(EmailProvider):
    """Written against SendGrid's documented v3 `POST /mail/send` API.
    Not exercised against a live SendGrid account in this environment (no
    credentials available) — MockEmailProvider is what the test suite
    actually runs against."""

    name = "sendgrid"

    def __init__(self, api_key: str, from_address: str, timeout_seconds: float = 10.0) -> None:
        self._api_key = api_key
        self._from_address = from_address
        self._timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self._api_key and self._from_address)

    def send(self, to: str, subject: str, body: str) -> MessageSendResult:
        if not self.is_available():
            raise NotificationAuthError("SendGrid provider is not configured")

        url = "https://api.sendgrid.com/v3/mail/send"
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self._from_address},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout_seconds)
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

        # SendGrid's success response is 202 with an empty body; the
        # message id comes back in a response header, per their docs.
        message_id = response.headers.get("X-Message-Id") or f"sendgrid-{response.status_code}"
        return MessageSendResult(provider_message_id=message_id)
