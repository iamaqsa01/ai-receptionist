"""Phase 13 — integration logs: record_integration_log() persists a row per
attempted external-provider call, and it's wired into calendar sync and
WhatsApp/email notifications so a failure there shows up as an
`integration_failures` count in analytics."""

import uuid

from sqlalchemy import select

from app.integrations.calendar.mock_provider import MockCalendarProvider
from app.integrations.calendar.sync import CalendarSyncService
from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.exceptions import NotificationAPIError
from app.integrations.notifications.service import NotificationService
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.integration_log import IntegrationLog
from app.models.patient import Patient
from app.models.workspace import Workspace
from app.services.integration_log import record_integration_log


def test_record_integration_log_persists_a_row(db_session):
    ws = Workspace(name="Log Clinic", slug="log-clinic")
    db_session.add(ws)
    db_session.commit()

    entry = record_integration_log(
        db_session, workspace_id=ws.id, category="calendar", provider="mock", action="create_event", status="success",
    )
    stored = db_session.execute(select(IntegrationLog).where(IntegrationLog.id == entry.id)).scalar_one()
    assert stored.status == "success"
    assert stored.category == "calendar"


def test_calendar_sync_logs_success_and_failure(db_session, monkeypatch):
    ws = Workspace(name="Calendar Log Clinic", slug="calendar-log-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Integration(workspace_id=ws.id, provider="google_calendar", is_active=True, config={"calendar_id": "primary"}))
    patient = Patient(workspace_id=ws.id, first_name="Jane", last_name="Doe")
    db_session.add(patient)
    db_session.flush()

    from datetime import datetime, timedelta, timezone
    start = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = Appointment(workspace_id=ws.id, patient_id=patient.id, start_time=start, end_time=start + timedelta(minutes=30), status="scheduled")
    db_session.add(appointment)
    db_session.commit()

    calendar = MockCalendarProvider()
    service = CalendarSyncService(db=db_session, provider=calendar)
    service.create_event(ws.id, appointment, summary="Cleaning", description="")

    logs = db_session.execute(select(IntegrationLog).where(IntegrationLog.workspace_id == ws.id)).scalars().all()
    assert any(log.status == "success" and log.action == "create_event" for log in logs)

    # Now force a failure on cancel.
    def boom(*args, **kwargs):
        from app.integrations.calendar.exceptions import CalendarAPIError
        raise CalendarAPIError("simulated outage", status_code=503)

    monkeypatch.setattr(calendar, "cancel_event", boom)
    service.cancel_event(ws.id, appointment)

    logs = db_session.execute(select(IntegrationLog).where(IntegrationLog.workspace_id == ws.id)).scalars().all()
    assert any(log.status == "failure" and log.action == "cancel_event" for log in logs)


def test_notification_service_logs_success_and_failure(db_session):
    ws = Workspace(name="Notify Log Clinic", slug="notify-log-clinic")
    db_session.add(ws)
    db_session.flush()
    patient = Patient(workspace_id=ws.id, first_name="Jane", last_name="Doe", phone="+15551234567", email="jane@example.com")
    db_session.add(patient)
    db_session.flush()

    from datetime import datetime, timedelta, timezone
    start = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = Appointment(workspace_id=ws.id, patient_id=patient.id, start_time=start, end_time=start + timedelta(minutes=30), status="scheduled")
    db_session.add(appointment)
    db_session.commit()

    class BoomWhatsApp(MockWhatsAppProvider):
        def send(self, to, body):
            raise NotificationAPIError("simulated outage", status_code=503)

    service = NotificationService(db=db_session, whatsapp=BoomWhatsApp(), email=MockEmailProvider())
    service.notify_appointment_event("appointment_confirmation", appointment, patient, service_summary="Cleaning")

    logs = db_session.execute(select(IntegrationLog).where(IntegrationLog.workspace_id == ws.id)).scalars().all()
    categories_status = {(log.category, log.status) for log in logs}
    assert ("whatsapp", "failure") in categories_status
    assert ("email", "success") in categories_status
