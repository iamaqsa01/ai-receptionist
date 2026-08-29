"""Phase 9 — NotificationService: sends appointment confirmation/
cancellation/reschedule notifications (WhatsApp + email) to the patient and,
when configured, to the clinic/receptionist contact; tracks every attempt;
and never sends the same notification twice."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.exceptions import NotificationAPIError
from app.integrations.notifications.service import NotificationService
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.notification_message import NotificationMessage
from app.models.patient import Patient
from app.models.workspace import Workspace


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Notify Clinic", slug="notify-clinic", timezone="UTC")
    db_session.add(ws)
    db_session.commit()
    return ws


@pytest.fixture()
def workspace_with_clinic_contact(db_session):
    ws = Workspace(name="Notify Clinic 2", slug="notify-clinic-2", timezone="UTC")
    db_session.add(ws)
    db_session.flush()
    db_session.add(
        Integration(
            workspace_id=ws.id,
            provider="clinic_notifications",
            is_active=True,
            config={"whatsapp_number": "+15559990000", "email": "frontdesk@example.com"},
        )
    )
    db_session.commit()
    return ws


@pytest.fixture()
def patient(db_session, workspace):
    p = Patient(workspace_id=workspace.id, first_name="Jane", last_name="Doe", phone="+15551234567", email="jane@example.com")
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def appointment(db_session, workspace, patient):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    appt = Appointment(
        workspace_id=workspace.id,
        patient_id=patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status="scheduled",
    )
    db_session.add(appt)
    db_session.commit()
    return appt


@pytest.fixture()
def whatsapp():
    return MockWhatsAppProvider()


@pytest.fixture()
def email():
    return MockEmailProvider()


@pytest.fixture()
def service(db_session, whatsapp, email):
    return NotificationService(db=db_session, whatsapp=whatsapp, email=email)


# -- the four supported notification kinds --------------------------------------------


def test_appointment_confirmation_sends_whatsapp_and_email_to_patient(db_session, service, appointment, patient, whatsapp, email):
    results = service.notify_appointment_event(
        "appointment_confirmation", appointment, patient, service_summary="Cleaning"
    )
    assert len(results) == 2
    assert all(r.status == "sent" for r in results)
    assert len(whatsapp.sent) == 1
    assert len(email.sent) == 1
    assert "confirmed" in whatsapp.sent[0]["body"].lower()


def test_appointment_cancellation_message_says_cancelled(service, appointment, patient, whatsapp):
    service.notify_appointment_event("appointment_cancellation", appointment, patient, service_summary="Cleaning")
    assert "cancelled" in whatsapp.sent[0]["body"].lower()


def test_appointment_reschedule_message_says_rescheduled(service, appointment, patient, whatsapp):
    service.notify_appointment_event("appointment_reschedule", appointment, patient, service_summary="Cleaning")
    assert "rescheduled" in whatsapp.sent[0]["body"].lower()


def test_clinic_contact_also_notified_when_configured(
    db_session, whatsapp, email, workspace_with_clinic_contact, patient, appointment
):
    # Re-point the fixtures' patient/appointment at the clinic-enabled workspace.
    patient.workspace_id = workspace_with_clinic_contact.id
    appointment.workspace_id = workspace_with_clinic_contact.id
    db_session.commit()

    service = NotificationService(db=db_session, whatsapp=whatsapp, email=email)
    results = service.notify_appointment_event(
        "appointment_confirmation", appointment, patient, service_summary="Cleaning"
    )

    # 2 patient messages + 2 clinic messages.
    assert len(results) == 4
    audiences = {r.audience for r in results}
    assert audiences == {"patient", "clinic"}
    clinic_whatsapp_recipients = [m["to"] for m in whatsapp.sent]
    assert "+15559990000" in clinic_whatsapp_recipients


def test_no_clinic_notification_when_workspace_has_not_configured_one(service, appointment, patient, whatsapp, email):
    results = service.notify_appointment_event(
        "appointment_confirmation", appointment, patient, service_summary="Cleaning"
    )
    assert all(r.audience == "patient" for r in results)


def test_patient_with_no_phone_or_email_gets_no_messages(db_session, service, workspace, appointment):
    silent_patient = Patient(workspace_id=workspace.id, first_name="No", last_name="Contact")
    db_session.add(silent_patient)
    db_session.commit()

    results = service.notify_appointment_event(
        "appointment_confirmation", appointment, silent_patient, service_summary="Cleaning"
    )
    assert results == []


# -- tracking: message id, recipient, status, timestamp, failure reason ---------------


def test_successful_send_is_tracked_with_provider_message_id_and_timestamp(db_session, service, appointment, patient):
    results = service.notify_appointment_event(
        "appointment_confirmation", appointment, patient, service_summary="Cleaning"
    )
    whatsapp_record = next(r for r in results if r.channel == "whatsapp")
    assert whatsapp_record.recipient == patient.phone
    assert whatsapp_record.status == "sent"
    assert whatsapp_record.provider_message_id
    assert whatsapp_record.sent_at is not None
    assert whatsapp_record.failure_reason is None

    stored = db_session.execute(
        select(NotificationMessage).where(NotificationMessage.id == whatsapp_record.id)
    ).scalar_one()
    assert stored.status == "sent"


def test_failed_send_is_tracked_with_failure_reason_and_no_message_id(db_session, appointment, patient, email):
    class BoomWhatsApp(MockWhatsAppProvider):
        def send(self, to, body):
            raise NotificationAPIError("simulated outage", status_code=503)

    service = NotificationService(db=db_session, whatsapp=BoomWhatsApp(), email=email)
    results = service.notify_appointment_event(
        "appointment_confirmation", appointment, patient, service_summary="Cleaning"
    )
    whatsapp_record = next(r for r in results if r.channel == "whatsapp")
    assert whatsapp_record.status == "failed"
    assert whatsapp_record.provider_message_id is None
    assert whatsapp_record.sent_at is None
    assert "simulated outage" in whatsapp_record.failure_reason


# -- duplicate prevention --------------------------------------------------------------


def test_sending_the_same_event_twice_does_not_send_twice(service, appointment, patient, whatsapp, email):
    service.notify_appointment_event("appointment_confirmation", appointment, patient, service_summary="Cleaning")
    service.notify_appointment_event("appointment_confirmation", appointment, patient, service_summary="Cleaning")

    assert len(whatsapp.sent) == 1
    assert len(email.sent) == 1


def test_a_different_event_type_for_the_same_appointment_still_sends(service, appointment, patient, whatsapp):
    service.notify_appointment_event("appointment_confirmation", appointment, patient, service_summary="Cleaning")
    service.notify_appointment_event("appointment_reschedule", appointment, patient, service_summary="Cleaning")

    assert len(whatsapp.sent) == 2


def test_a_failed_send_can_be_retried(db_session, appointment, patient, email):
    class FlakyWhatsApp(MockWhatsAppProvider):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def send(self, to, body):
            self.attempts += 1
            if self.attempts == 1:
                raise NotificationAPIError("simulated outage", status_code=503)
            return super().send(to, body)

    flaky = FlakyWhatsApp()
    service = NotificationService(db=db_session, whatsapp=flaky, email=email)

    first = service.notify_appointment_event("appointment_confirmation", appointment, patient, service_summary="Cleaning")
    assert next(r for r in first if r.channel == "whatsapp").status == "failed"

    second = service.notify_appointment_event("appointment_confirmation", appointment, patient, service_summary="Cleaning")
    assert next(r for r in second if r.channel == "whatsapp").status == "sent"
    assert flaky.attempts == 2

    # Both attempts are tracked as separate rows.
    all_rows = db_session.execute(
        select(NotificationMessage).where(
            NotificationMessage.appointment_id == appointment.id, NotificationMessage.channel == "whatsapp"
        )
    ).scalars().all()
    assert len(all_rows) == 2
