"""Phase 16 — day-of reminder background job (app/jobs/reminders.py).

Covers: today's appointments are picked up and reminded; reminder_sent is
flipped; an already-reminded appointment is skipped; an appointment on
another day is ignored; and a messaging-provider failure leaves
reminder_sent False (safe retry) rather than falsely marking success.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.exceptions import NotificationAPIError
from app.integrations.notifications.service import NotificationService
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.jobs.reminders import send_due_reminders
from app.models.appointment import Appointment
from app.models.notification_message import NotificationMessage
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.workspace import Workspace

NOW = datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc)  # 06:00 UTC "today"


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Job Clinic", slug="job-clinic", timezone="UTC")
    db_session.add(ws)
    db_session.commit()
    return ws


@pytest.fixture()
def provider(db_session, workspace):
    p = Provider(workspace_id=workspace.id, name="Dr Sara", phone="+15550001111", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def patient(db_session, workspace):
    p = Patient(workspace_id=workspace.id, first_name="Omar", last_name="Farooq", phone="+15552223333")
    db_session.add(p)
    db_session.commit()
    return p


def _make_appt(db_session, workspace, patient, provider, *, start, status="scheduled", reminder_sent=False):
    appt = Appointment(
        workspace_id=workspace.id, patient_id=patient.id, provider_id=provider.id,
        start_time=start, end_time=start + timedelta(minutes=30), status=status,
        reminder_sent=reminder_sent,
    )
    db_session.add(appt)
    db_session.commit()
    return appt


def _service(db_session, whatsapp=None, email=None):
    return NotificationService(
        db=db_session, whatsapp=whatsapp or MockWhatsAppProvider(), email=email or MockEmailProvider()
    )


def test_todays_appointment_is_reminded_and_flag_is_set(db_session, workspace, patient, provider):
    appt = _make_appt(db_session, workspace, patient, provider, start=NOW + timedelta(hours=6))
    whatsapp = MockWhatsAppProvider()

    result = send_due_reminders(
        db_session, now=NOW, notification_service=_service(db_session, whatsapp=whatsapp)
    )

    assert result.considered == 1
    assert result.reminded == 1
    db_session.refresh(appt)
    assert appt.reminder_sent is True
    # patient + doctor both messaged.
    assert {m["to"] for m in whatsapp.sent} == {patient.phone, provider.phone}


def test_already_reminded_appointment_is_skipped(db_session, workspace, patient, provider):
    _make_appt(db_session, workspace, patient, provider, start=NOW + timedelta(hours=5), reminder_sent=True)
    whatsapp = MockWhatsAppProvider()

    result = send_due_reminders(
        db_session, now=NOW, notification_service=_service(db_session, whatsapp=whatsapp)
    )

    assert result.considered == 0
    assert result.reminded == 0
    assert whatsapp.sent == []


def test_appointment_on_another_day_is_not_selected(db_session, workspace, patient, provider):
    _make_appt(db_session, workspace, patient, provider, start=NOW + timedelta(days=2))

    result = send_due_reminders(db_session, now=NOW, notification_service=_service(db_session))

    assert result.considered == 0


def test_cancelled_appointment_is_not_reminded(db_session, workspace, patient, provider):
    _make_appt(
        db_session, workspace, patient, provider,
        start=NOW + timedelta(hours=4), status="cancelled",
    )
    result = send_due_reminders(db_session, now=NOW, notification_service=_service(db_session))
    assert result.considered == 0


def test_failed_send_does_not_mark_reminder_as_sent(db_session, workspace, patient, provider):
    appt = _make_appt(db_session, workspace, patient, provider, start=NOW + timedelta(hours=7))

    class BoomWhatsApp(MockWhatsAppProvider):
        def send(self, to, body):
            raise NotificationAPIError("provider outage", status_code=503)

    result = send_due_reminders(
        db_session, now=NOW, notification_service=_service(db_session, whatsapp=BoomWhatsApp()),
    )

    assert result.reminded == 0
    assert result.failed == 1
    db_session.refresh(appt)
    assert appt.reminder_sent is False  # <- safe retry, not a false success

    # The failure is recorded, and a later run can retry and succeed.
    failed_rows = db_session.execute(
        select(NotificationMessage).where(
            NotificationMessage.appointment_id == appt.id, NotificationMessage.status == "failed"
        )
    ).scalars().all()
    assert failed_rows

    retry = send_due_reminders(
        db_session, now=NOW, notification_service=_service(db_session, whatsapp=MockWhatsAppProvider()),
    )
    assert retry.reminded == 1
    db_session.refresh(appt)
    assert appt.reminder_sent is True


def test_second_run_is_idempotent(db_session, workspace, patient, provider):
    _make_appt(db_session, workspace, patient, provider, start=NOW + timedelta(hours=6))
    whatsapp = MockWhatsAppProvider()

    send_due_reminders(db_session, now=NOW, notification_service=_service(db_session, whatsapp=whatsapp))
    first = list(whatsapp.sent)
    send_due_reminders(db_session, now=NOW, notification_service=_service(db_session, whatsapp=whatsapp))

    assert whatsapp.sent == first  # nothing sent on the second pass
