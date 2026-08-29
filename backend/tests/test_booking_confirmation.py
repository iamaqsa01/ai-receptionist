"""Phase 16 — immediate booking confirmation.

A successful booking fires the patient (and assigned-doctor) confirmation
right away, on the same shared AppointmentSchedulingService path the AI
Receptionist and the Vapi tool both use. A booking that fails (conflict /
duplicate) sends nothing.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.ai.scheduling.outcomes import BookingOutcome
from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.service import NotificationService
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.scheduling import AppointmentBookingRequest, AppointmentSchedulingService

START = datetime.now(timezone.utc) + timedelta(days=1)


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Booking Clinic", slug="booking-clinic", timezone="UTC")
    db_session.add(ws)
    db_session.flush()
    db_session.add(Service(workspace_id=ws.id, name="Cleaning", duration_minutes=30, is_active=True))
    db_session.add(Provider(workspace_id=ws.id, name="Dr Adeel", phone="+15557778888", is_active=True))
    db_session.commit()
    return ws


@pytest.fixture()
def deps(db_session):
    whatsapp, email = MockWhatsAppProvider(), MockEmailProvider()
    notifications = NotificationService(db=db_session, whatsapp=whatsapp, email=email)
    scheduling = AppointmentSchedulingService(db=db_session, notifications=notifications)
    return scheduling, whatsapp, email


def _request(db_session, workspace, *, phone="+15551234000", start=START):
    service = db_session.query(Service).filter_by(workspace_id=workspace.id).one()
    provider = db_session.query(Provider).filter_by(workspace_id=workspace.id).one()
    return AppointmentBookingRequest(
        workspace=workspace, service=service, provider=provider, start_time=start,
        patient_name="Hina Raza", patient_phone=phone, source="test",
    )


def test_successful_booking_sends_confirmation_immediately(db_session, workspace, deps):
    scheduling, whatsapp, email = deps

    result = scheduling.book_appointment(_request(db_session, workspace))

    assert result.outcome == BookingOutcome.CREATED
    assert result.appointment is not None
    # Patient confirmation went out on WhatsApp right after the DB write.
    assert any(m["to"] == "+15551234000" for m in whatsapp.sent)
    assert any("confirmed" in m["body"].lower() for m in whatsapp.sent)
    # Assigned doctor was notified too.
    assert any(m["to"] == "+15557778888" for m in whatsapp.sent)


def test_failed_booking_sends_no_confirmation(db_session, workspace, deps):
    scheduling, whatsapp, email = deps

    first = scheduling.book_appointment(_request(db_session, workspace, phone="+15550000001"))
    assert first.outcome == BookingOutcome.CREATED
    sent_after_success = len(whatsapp.sent)

    # Same provider + same slot, different patient -> provider conflict.
    second = scheduling.book_appointment(_request(db_session, workspace, phone="+15550000002"))

    assert second.outcome in (BookingOutcome.CONFLICT, BookingOutcome.DUPLICATE)
    assert len(whatsapp.sent) == sent_after_success  # nothing new sent


def test_confirmation_is_not_sent_twice_for_the_same_booking(db_session, workspace, deps):
    scheduling, whatsapp, email = deps
    req = _request(db_session, workspace)

    scheduling.book_appointment(req)
    before = len(whatsapp.sent)
    # Re-dispatch the same event for the created appointment.
    appt = db_session.query(Appointment).one()
    patient = db_session.query(Patient).one()
    scheduling.notifications.notify_appointment_event(
        "appointment_confirmation", appt, patient, service_summary="Cleaning"
    )
    assert len(whatsapp.sent) == before
