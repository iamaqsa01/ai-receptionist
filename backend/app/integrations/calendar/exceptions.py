"""Every calendar-provider failure mode gets its own exception type, so
callers (CalendarSyncService) can decide exactly how to react to each
one — rather than a single generic "calendar failed" catch-all that loses
the distinction between "the caller can't have this slot" (must affect the
booking outcome) and "our Google credentials expired" (must not — the
booking still succeeds in our own system; someone just needs to reconnect
the integration)."""


class CalendarError(Exception):
    """Base class for every calendar-provider failure."""


class CalendarAuthError(CalendarError):
    """Credentials are missing, malformed, or otherwise rejected outright
    (never worked, as opposed to having worked and since expired)."""


class CalendarCredentialsExpiredError(CalendarError):
    """Credentials were valid but have since expired or been revoked
    (e.g. a refresh token no longer accepted) — distinct from
    CalendarAuthError so a "please reconnect" message can be specific."""


class CalendarSlotUnavailableError(CalendarError):
    """The requested time is busy on the external calendar."""


class CalendarTimeoutError(CalendarError):
    """The calendar API did not respond in time."""


class CalendarAPIError(CalendarError):
    """The calendar API responded with an error that isn't one of the more
    specific categories above (e.g. a 5xx, a malformed request)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
