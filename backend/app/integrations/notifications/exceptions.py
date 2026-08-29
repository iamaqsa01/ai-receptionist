"""Every notification-provider failure mode gets its own exception type, so
NotificationService can record a distinct, useful `failure_reason` instead
of a single generic "send failed" string."""


class NotificationError(Exception):
    """Base class for every WhatsApp/email provider failure."""


class NotificationAuthError(NotificationError):
    """Credentials are missing, malformed, or otherwise rejected outright."""


class NotificationInvalidRecipientError(NotificationError):
    """The recipient address/number was rejected by the provider (bad
    format, unreachable, opted out, etc.)."""


class NotificationRateLimitError(NotificationError):
    """The provider is throttling this account."""


class NotificationTimeoutError(NotificationError):
    """The provider API did not respond in time."""


class NotificationAPIError(NotificationError):
    """The provider API responded with an error that isn't one of the more
    specific categories above (e.g. a 5xx, a malformed request)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
