"""Opt-in live verification for the existing Google Calendar provider.

This test is skipped during the normal suite. It creates a real event through
the canonical appointment scheduling service, verifies that the event blocks
the Google Calendar slot and that its external ID is persisted, then removes
the event in a ``finally`` block.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.ai.scheduling.outcomes import BookingOutcome
from app.integrations.calendar.factory import get_calendar_provider
from app.integrations.calendar.sync import CalendarSyncService
from app.models.integration import Integration
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.scheduling import AppointmentBookingRequest, AppointmentSchedulingService


_LIVE_TEST_ENABLED = os.getenv("RUN_GOOGLE_CALENDAR_LIVE_TEST") == "1"
_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_TEST_CALENDAR_ID", "").strip()


@pytest.mark.skipif(
    not _LIVE_TEST_ENABLED or not _CALENDAR_ID,
    reason="Set RUN_GOOGLE_CALENDAR_LIVE_TEST=1 and GOOGLE_CALENDAR_TEST_CALENDAR_ID to run",
)
def test_google_calendar_through_canonical_appointment_flow(db_session):
    provider = get_calendar_provider()
    assert provider.name == "google"
    assert provider.is_available()

    # Pick a free, deterministic-length window without assuming the clinic's
    # real calendar is empty on one particular date.
    start = (datetime.now(timezone.utc) + timedelta(days=30)).replace(
        hour=3, minute=0, second=0, microsecond=0
    )
    for offset in range(14):
        candidate = start + timedelta(days=offset)
        if provider.check_availability(_CALENDAR_ID, candidate, candidate + timedelta(minutes=15)):
            start = candidate
            break
    else:
        pytest.fail("No free 15-minute live-test slot found in the next 14 candidate days")
    end = start + timedelta(minutes=15)

    workspace = Workspace(name="Google Calendar Live Test", slug="google-calendar-live-test", timezone="UTC")
    db_session.add(workspace)
    db_session.flush()
    service = Service(
        workspace_id=workspace.id,
        name="Calendar Integration Test",
        duration_minutes=15,
        is_active=True,
    )
    db_session.add_all(
        [
            service,
            Integration(
                workspace_id=workspace.id,
                provider="google_calendar",
                is_active=True,
                config={"calendar_id": _CALENDAR_ID},
            ),
        ]
    )
    db_session.commit()

    scheduling = AppointmentSchedulingService(
        db_session,
        calendar=CalendarSyncService(db_session, provider=provider),
    )
    appointment = None
    event_id = None
    try:
        result = scheduling.book_appointment(
            AppointmentBookingRequest(
                workspace=workspace,
                service=service,
                start_time=start,
                patient_name="Calendar Live Test",
                patient_phone="+15555550100",
                source="google_calendar_live_test",
            )
        )

        assert result.outcome == BookingOutcome.CREATED
        appointment = result.appointment
        assert appointment is not None
        assert appointment.external_calendar_provider == "google"
        assert appointment.external_calendar_event_id
        event_id = appointment.external_calendar_event_id

        # A fresh API request confirms the created event is visible and now
        # blocks the same slot on the shared calendar.
        assert provider.check_availability(_CALENDAR_ID, start, end) is False
    finally:
        if event_id:
            provider.cancel_event(_CALENDAR_ID, event_id)

