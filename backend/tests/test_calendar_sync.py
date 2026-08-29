"""Phase 8 — CalendarSyncService: every failure mode (authentication,
expired credentials, unavailable slots, generic API errors, timeouts) is
handled distinctly, and a calendar problem never blocks a booking except
for a genuine "that slot is busy" answer."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.integrations.calendar.base import CalendarEvent, CalendarProvider
from app.integrations.calendar.exceptions import (
    CalendarAPIError,
    CalendarAuthError,
    CalendarCredentialsExpiredError,
    CalendarSlotUnavailableError,
    CalendarTimeoutError,
)
from app.integrations.calendar.sync import CalendarSyncService
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.notification import Notification
from app.models.patient import Patient
from app.models.workspace import Workspace


def dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc)


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Calendar Clinic", slug="calendar-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(
        Integration(
            workspace_id=ws.id, provider="google_calendar", is_active=True, config={"calendar_id": "clinic@example.com"}
        )
    )
    db_session.commit()
    return ws


@pytest.fixture()
def patient(db_session, workspace):
    p = Patient(workspace_id=workspace.id, first_name="Jane", last_name="Doe", phone="+14155550100")
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def appointment(db_session, workspace, patient):
    a = Appointment(
        workspace_id=workspace.id, patient_id=patient.id, start_time=dt(9), end_time=dt(10), status="scheduled"
    )
    db_session.add(a)
    db_session.commit()
    return a


class _FailingProvider(CalendarProvider):
    """Raises a chosen exception from every method — used to prove each
    failure category is caught and reported the same way regardless of
    which operation triggered it."""

    name = "failing"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def is_available(self) -> bool:
        return True

    def check_availability(self, calendar_id, start, end):
        raise self._exc

    def create_event(self, calendar_id, *, summary, description, start, end):
        raise self._exc

    def update_event(self, calendar_id, external_event_id, *, start, end, summary=None, description=None):
        raise self._exc

    def cancel_event(self, calendar_id, external_event_id):
        raise self._exc


class _WorkingProvider(CalendarProvider):
    name = "working"

    def __init__(self) -> None:
        self.created: list[str] = []

    def is_available(self) -> bool:
        return True

    def check_availability(self, calendar_id, start, end):
        return True

    def create_event(self, calendar_id, *, summary, description, start, end):
        event_id = uuid.uuid4().hex
        self.created.append(event_id)
        return CalendarEvent(external_event_id=event_id, summary=summary, start=start, end=end)

    def update_event(self, calendar_id, external_event_id, *, start, end, summary=None, description=None):
        return CalendarEvent(external_event_id=external_event_id, summary=summary or "", start=start, end=end)

    def cancel_event(self, calendar_id, external_event_id):
        pass


# -- not configured -----------------------------------------------------------------


def test_no_op_when_workspace_has_no_calendar_integration(db_session, appointment):
    ws = Workspace(name="No Calendar Clinic", slug="no-calendar-clinic")
    db_session.add(ws)
    db_session.commit()

    provider = _WorkingProvider()
    sync = CalendarSyncService(db=db_session, provider=provider)
    sync.create_event(ws.id, appointment, summary="x", description="y")

    assert provider.created == []
    assert appointment.external_calendar_event_id is None


# -- each failure mode ----------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected_snippet",
    [
        (CalendarAuthError("bad creds"), "authentication failed"),
        (CalendarCredentialsExpiredError("expired"), "expired"),
        (CalendarTimeoutError("timed out"), "did not respond in time"),
        (CalendarAPIError("server error", status_code=500), "returned an error"),
    ],
)
def test_create_event_failure_does_not_block_booking_and_notifies_staff(
    db_session, workspace, appointment, exc, expected_snippet
):
    sync = CalendarSyncService(db=db_session, provider=_FailingProvider(exc))
    sync.create_event(workspace.id, appointment, summary="x", description="y")

    # The appointment itself is untouched — no external id was ever stored,
    # but nothing about the booking failed because of this.
    assert appointment.external_calendar_event_id is None

    notification = db_session.execute(
        select(Notification).where(Notification.workspace_id == workspace.id, Notification.type == "calendar_sync_error")
    ).scalar_one()
    assert expected_snippet in notification.message.lower()


def test_check_availability_slot_unavailable_returns_false(db_session, workspace, appointment):
    sync = CalendarSyncService(db=db_session, provider=_FailingProvider(CalendarSlotUnavailableError("busy")))
    assert sync.check_availability(workspace.id, appointment) is False
    # A real conflict is not a sync failure — no staff notification needed.
    assert db_session.execute(select(Notification).where(Notification.workspace_id == workspace.id)).scalars().all() == []


@pytest.mark.parametrize(
    "exc",
    [CalendarAuthError("x"), CalendarCredentialsExpiredError("x"), CalendarTimeoutError("x"), CalendarAPIError("x")],
)
def test_check_availability_other_failures_return_none_and_do_not_block(db_session, workspace, appointment, exc):
    sync = CalendarSyncService(db=db_session, provider=_FailingProvider(exc))
    result = sync.check_availability(workspace.id, appointment)
    assert result is None  # "unknown" — caller must not treat this as a conflict


def test_update_event_failure_is_reported_but_reschedule_already_committed(db_session, workspace, appointment):
    appointment.external_calendar_event_id = "evt-123"
    appointment.external_calendar_provider = "google"
    db_session.add(appointment)
    db_session.commit()

    sync = CalendarSyncService(db=db_session, provider=_FailingProvider(CalendarAPIError("boom")))
    sync.update_event(workspace.id, appointment)  # must not raise

    notification = db_session.execute(
        select(Notification).where(Notification.workspace_id == workspace.id)
    ).scalar_one()
    assert "calendar" in notification.title.lower()


def test_cancel_event_failure_is_reported_and_id_is_kept_for_retry(db_session, workspace, appointment):
    appointment.external_calendar_event_id = "evt-123"
    appointment.external_calendar_provider = "google"
    db_session.add(appointment)
    db_session.commit()

    sync = CalendarSyncService(db=db_session, provider=_FailingProvider(CalendarAuthError("x")))
    sync.cancel_event(workspace.id, appointment)

    # Left in place rather than silently cleared: a human (or a future
    # retry) still needs to actually remove it from the external calendar.
    assert appointment.external_calendar_event_id == "evt-123"
    notification = db_session.execute(
        select(Notification).where(Notification.workspace_id == workspace.id)
    ).scalar_one()
    assert notification.type == "calendar_sync_error"


# -- happy path + duplicate-event prevention -----------------------------------------


def test_create_event_success_stores_external_id(db_session, workspace, appointment):
    provider = _WorkingProvider()
    sync = CalendarSyncService(db=db_session, provider=provider)
    sync.create_event(workspace.id, appointment, summary="Cleaning — Jane Doe", description="...")

    assert appointment.external_calendar_event_id in provider.created
    assert appointment.external_calendar_provider == "working"


def test_create_event_is_never_called_twice_for_the_same_appointment(db_session, workspace, appointment):
    provider = _WorkingProvider()
    sync = CalendarSyncService(db=db_session, provider=provider)

    sync.create_event(workspace.id, appointment, summary="x", description="y")
    first_id = appointment.external_calendar_event_id

    sync.create_event(workspace.id, appointment, summary="x", description="y")  # called again
    assert appointment.external_calendar_event_id == first_id
    assert len(provider.created) == 1  # the provider was only ever asked once


def test_cancel_event_clears_external_id_on_success(db_session, workspace, appointment):
    provider = _WorkingProvider()
    sync = CalendarSyncService(db=db_session, provider=provider)
    sync.create_event(workspace.id, appointment, summary="x", description="y")
    assert appointment.external_calendar_event_id is not None

    sync.cancel_event(workspace.id, appointment)
    assert appointment.external_calendar_event_id is None
    assert appointment.external_calendar_provider is None
