import logging
import socket
from datetime import datetime
from typing import Any

from app.integrations.calendar.base import CalendarEvent, CalendarProvider
from app.integrations.calendar.exceptions import (
    CalendarAPIError,
    CalendarAuthError,
    CalendarCredentialsExpiredError,
    CalendarTimeoutError,
)

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarProvider(CalendarProvider):
    """Written against the documented Google Calendar API v3
    (googleapiclient + google-auth, service-account authentication — the
    standard approach for a server automating a single shared clinic
    calendar with no per-caller consent flow). Not exercised against a live
    Google account in this environment (no credentials available) —
    MockCalendarProvider is what the test suite actually runs against.

    Every method translates the SDK's exceptions into this package's own
    exception types (see exceptions.py) so callers never need to know
    googleapiclient/google-auth's exception hierarchy.
    """

    name = "google"

    def __init__(self, service_account_info: dict[str, Any] | None, timeout_seconds: float = 10.0) -> None:
        self._service_account_info = service_account_info
        self._timeout_seconds = timeout_seconds
        self._service = None

    def is_available(self) -> bool:
        return bool(self._service_account_info)

    def _get_service(self):
        if self._service is not None:
            return self._service
        if not self._service_account_info:
            raise CalendarAuthError("Google Calendar provider is not configured (missing service account credentials)")

        import httplib2
        from google.auth.exceptions import GoogleAuthError, RefreshError
        from google.oauth2 import service_account
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        try:
            credentials = service_account.Credentials.from_service_account_info(
                self._service_account_info, scopes=_SCOPES
            )
            # httplib2's timeout is what actually enforces a request
            # deadline here — googleapiclient's own `execute()` has no
            # universal timeout parameter, so it has to be set on the
            # underlying HTTP transport instead.
            http = httplib2.Http(timeout=self._timeout_seconds)
            authed_http = AuthorizedHttp(credentials, http=http)
            self._service = build("calendar", "v3", http=authed_http, cache_discovery=False)
        except RefreshError as exc:
            raise CalendarCredentialsExpiredError(str(exc)) from exc
        except GoogleAuthError as exc:
            raise CalendarAuthError(str(exc)) from exc
        except Exception as exc:  # malformed service account JSON, etc.
            raise CalendarAuthError(str(exc)) from exc
        return self._service

    def _translate_error(self, exc: Exception) -> Exception:
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError

        if isinstance(exc, socket.timeout | TimeoutError):
            return CalendarTimeoutError(str(exc))
        if isinstance(exc, RefreshError):
            return CalendarCredentialsExpiredError(str(exc))
        if isinstance(exc, HttpError):
            status = exc.resp.status if getattr(exc, "resp", None) is not None else None
            if status == 401:
                return CalendarAuthError(str(exc))
            if status == 403:
                # Google returns 403 for both a permissions problem and an
                # invalidated/expired grant; without a more specific reason
                # code, auth failure is the safer (more actionable) default.
                return CalendarAuthError(str(exc))
            return CalendarAPIError(str(exc), status_code=status)
        return CalendarAPIError(str(exc))

    def check_availability(self, calendar_id: str, start: datetime, end: datetime) -> bool:
        service = self._get_service()
        try:
            response = (
                service.freebusy()
                .query(body={"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": calendar_id}]})
                .execute(num_retries=0)
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc
        busy_periods = response.get("calendars", {}).get(calendar_id, {}).get("busy", [])
        return len(busy_periods) == 0

    def create_event(
        self, calendar_id: str, *, summary: str, description: str, start: datetime, end: datetime
    ) -> CalendarEvent:
        service = self._get_service()
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        try:
            created = service.events().insert(calendarId=calendar_id, body=body).execute(num_retries=0)
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return CalendarEvent(external_event_id=created["id"], summary=summary, start=start, end=end)

    def update_event(
        self,
        calendar_id: str,
        external_event_id: str,
        *,
        start: datetime,
        end: datetime,
        summary: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        service = self._get_service()
        body: dict[str, Any] = {
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        if summary is not None:
            body["summary"] = summary
        if description is not None:
            body["description"] = description
        try:
            updated = (
                service.events()
                .patch(calendarId=calendar_id, eventId=external_event_id, body=body)
                .execute(num_retries=0)
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return CalendarEvent(
            external_event_id=external_event_id, summary=updated.get("summary", summary or ""), start=start, end=end
        )

    def cancel_event(self, calendar_id: str, external_event_id: str) -> None:
        from googleapiclient.errors import HttpError

        service = self._get_service()
        try:
            service.events().delete(calendarId=calendar_id, eventId=external_event_id).execute(num_retries=0)
        except HttpError as exc:
            status = exc.resp.status if getattr(exc, "resp", None) is not None else None
            if status in (404, 410):
                # Already deleted/gone — same idempotent end state as a
                # successful cancel, not an error.
                return
            raise self._translate_error(exc) from exc
        except Exception as exc:
            raise self._translate_error(exc) from exc
