import logging
import uuid

from sqlalchemy.orm import Session

from app.integrations.calendar.base import CalendarProvider
from app.integrations.calendar.config import load_calendar_integration
from app.integrations.calendar.exceptions import (
    CalendarAPIError,
    CalendarAuthError,
    CalendarCredentialsExpiredError,
    CalendarError,
    CalendarSlotUnavailableError,
    CalendarTimeoutError,
)
from app.integrations.calendar.factory import get_calendar_provider
from app.models.appointment import Appointment
from app.models.notification import Notification
from app.services.integration_log import record_integration_log

logger = logging.getLogger(__name__)

_NON_FATAL_MESSAGES: dict[type[CalendarError], str] = {
    CalendarAuthError: "Google Calendar authentication failed. Please check the workspace's Google Calendar connection.",
    CalendarCredentialsExpiredError: "Google Calendar credentials have expired. Please reconnect Google Calendar.",
    CalendarTimeoutError: "Google Calendar did not respond in time. The appointment was saved, but may not appear on the calendar yet.",
    CalendarAPIError: "Google Calendar returned an error. The appointment was saved, but may not appear on the calendar.",
}


class CalendarSyncService:
    """Keeps a workspace's Google Calendar (or whichever CalendarProvider
    is configured) in sync with appointments — without ever letting a
    calendar problem block a phone booking. Every failure mode
    (authentication, expired credentials, API errors, timeouts) is caught
    here, logged, and surfaced to staff as a Notification; the booking
    itself always still succeeds in our own database. Only "the requested
    slot is busy on the calendar" is allowed to affect the booking outcome
    — that's a real scheduling conflict, not an integration failure."""

    def __init__(self, db: Session, provider: CalendarProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_calendar_provider()

    def check_availability(self, workspace_id: uuid.UUID, appointment: Appointment) -> bool | None:
        """True/False if the calendar answered; None if calendar sync isn't
        configured for this workspace, or the check itself failed for a
        non-fatal reason (in which case the caller should NOT block the
        booking on an unknown answer)."""
        config = load_calendar_integration(self.db, workspace_id)
        if config is None:
            return None
        try:
            return self.provider.check_availability(config.calendar_id, appointment.start_time, appointment.end_time)
        except CalendarSlotUnavailableError:
            return False
        except CalendarError as exc:
            self._report_failure(workspace_id, exc, "check calendar availability for", action="check_availability")
            return None

    def create_event(self, workspace_id: uuid.UUID, appointment: Appointment, *, summary: str, description: str) -> None:
        # Duplicate-event prevention: an appointment that's already synced
        # is never synced again.
        if appointment.external_calendar_event_id:
            return
        config = load_calendar_integration(self.db, workspace_id)
        if config is None:
            return
        try:
            event = self.provider.create_event(
                config.calendar_id,
                summary=summary,
                description=description,
                start=appointment.start_time,
                end=appointment.end_time,
            )
        except CalendarError as exc:
            self._report_failure(workspace_id, exc, "create a calendar event for", action="create_event")
            return
        appointment.external_calendar_provider = self.provider.name
        appointment.external_calendar_event_id = event.external_event_id
        self.db.add(appointment)
        self.db.commit()
        self._report_success(workspace_id, "create_event")

    def update_event(self, workspace_id: uuid.UUID, appointment: Appointment) -> None:
        if not appointment.external_calendar_event_id:
            return  # never synced in the first place — nothing external to update
        config = load_calendar_integration(self.db, workspace_id)
        if config is None:
            return
        try:
            self.provider.update_event(
                config.calendar_id,
                appointment.external_calendar_event_id,
                start=appointment.start_time,
                end=appointment.end_time,
            )
        except CalendarError as exc:
            self._report_failure(workspace_id, exc, "update the calendar event for", action="update_event")
            return
        self._report_success(workspace_id, "update_event")

    def cancel_event(self, workspace_id: uuid.UUID, appointment: Appointment) -> None:
        if not appointment.external_calendar_event_id:
            return
        config = load_calendar_integration(self.db, workspace_id)
        if config is None:
            return
        try:
            self.provider.cancel_event(config.calendar_id, appointment.external_calendar_event_id)
        except CalendarError as exc:
            self._report_failure(workspace_id, exc, "cancel the calendar event for", action="cancel_event")
            return
        appointment.external_calendar_event_id = None
        appointment.external_calendar_provider = None
        self.db.add(appointment)
        self.db.commit()
        self._report_success(workspace_id, "cancel_event")

    def _report_failure(self, workspace_id: uuid.UUID, exc: CalendarError, action_label: str, action: str) -> None:
        logger.error("workspace_id=%s failed to %s appointment: %s", workspace_id, action_label, exc, exc_info=True)
        message = _NON_FATAL_MESSAGES.get(type(exc), str(exc))
        notification = Notification(
            workspace_id=workspace_id,
            type="calendar_sync_error",
            title="Google Calendar sync failed",
            message=message,
        )
        self.db.add(notification)
        self.db.commit()
        record_integration_log(
            self.db, workspace_id=workspace_id, category="calendar", provider=self.provider.name,
            action=action, status="failure", detail=message,
        )

    def _report_success(self, workspace_id: uuid.UUID, action: str) -> None:
        record_integration_log(
            self.db, workspace_id=workspace_id, category="calendar", provider=self.provider.name,
            action=action, status="success",
        )
