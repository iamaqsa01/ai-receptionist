import httpx

from app.integrations.notifications.base import MessageSendResult, WhatsAppProvider
from app.integrations.notifications.exceptions import (
    NotificationAPIError,
    NotificationAuthError,
    NotificationInvalidRecipientError,
    NotificationRateLimitError,
    NotificationTimeoutError,
)


class MetaWhatsAppProvider(WhatsAppProvider):
    """Meta's WhatsApp Cloud API — written against the documented
    `POST /{phone-number-id}/messages` endpoint with a free-form text
    message. Not exercised against a live Meta account in this environment
    (no credentials available) — MockWhatsAppProvider is what the test
    suite actually runs against."""

    name = "meta_whatsapp"

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        timeout_seconds: float = 10.0,
        api_version: str = "v20.0",
    ) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._timeout_seconds = timeout_seconds
        self._api_version = api_version

    def is_available(self) -> bool:
        return bool(self._access_token and self._phone_number_id)

    def send(self, to: str, body: str) -> MessageSendResult:
        if not self.is_available():
            raise NotificationAuthError("Meta WhatsApp provider is not configured")

        url = f"https://graph.facebook.com/{self._api_version}/{self._phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {"Authorization": f"Bearer {self._access_token}"}
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

        try:
            data = response.json()
            message_id = data["messages"][0]["id"]
        except (ValueError, KeyError, IndexError) as exc:
            raise NotificationAPIError(f"Unexpected Meta WhatsApp response: {response.text}") from exc
        return MessageSendResult(provider_message_id=message_id)
