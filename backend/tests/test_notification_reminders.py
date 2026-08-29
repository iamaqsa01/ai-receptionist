"""Phase 16 — bilingual (English / Urdu only) appointment reminders.

The voice conversation language and the notification language are entirely
separate: a Punjabi/Saraiki/Sindhi/Pashto caller still receives an
English-or-Urdu reminder, never one in their spoken language.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.integrations.notifications.clinic_config import load_notification_language
from app.integrations.notifications.email_mock import MockEmailProvider
from app.integrations.notifications.service import NotificationService
from app.integrations.notifications.templates import (
    doctor_reminder_body,
    normalize_notification_language,
    patient_reminder_body,
)
from app.integrations.notifications.whatsapp_mock import MockWhatsAppProvider
from app.models.appointment import Appointment
from app.models.integration import Integration
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.workspace import Workspace

WHEN = datetime(2026, 8, 28, 15, 30, tzinfo=timezone.utc)


# -- template layer ---------------------------------------------------------


def test_english_patient_reminder_uses_the_required_wording():
    body = patient_reminder_body("en", "Ayesha Khan", "Sunrise Clinic", WHEN)
    assert body == (
        "Reminder: Your appointment with Dr. Ayesha Khan at Sunrise Clinic "
        "is scheduled for today at 3:30 PM."
    )


def test_english_doctor_reminder_uses_the_required_wording():
    body = doctor_reminder_body("en", "Bilal Ahmed", WHEN)
    assert body == "Reminder: You have an appointment with Bilal Ahmed today at 3:30 PM."


def test_urdu_reminder_is_urdu_and_carries_the_dynamic_values():
    body = patient_reminder_body("ur", "Ayesha Khan", "Sunrise Clinic", WHEN)
    assert any("؀" <= ch <= "ۿ" for ch in body)  # Perso-Arabic script
    assert "Ayesha Khan" in body and "Sunrise Clinic" in body and "3:30" in body
    assert body != patient_reminder_body("en", "Ayesha Khan", "Sunrise Clinic", WHEN)


@pytest.mark.parametrize("spoken", ["pa", "skr", "sd", "ps", "en", "ur", "fr", None, ""])
def test_only_english_or_urdu_is_ever_produced(spoken):
    assert normalize_notification_language(spoken) in ("en", "ur")


def test_local_language_call_never_yields_a_local_language_notification():
    # Whatever the caller spoke, the notification language collapses to en/ur.
    for spoken in ("pa", "skr", "sd", "ps"):
        assert normalize_notification_language(spoken) == "en"


# -- service layer --------------------------------------------------------


@pytest.fixture()
def workspace(db_session):
    ws = Workspace(name="Reminder Clinic", slug="reminder-clinic", timezone="UTC")
    db_session.add(ws)
    db_session.commit()
    return ws


@pytest.fixture()
def provider(db_session, workspace):
    p = Provider(workspace_id=workspace.id, name="Bilal Ahmed", phone="+15559998888", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def patient(db_session, workspace):
    p = Patient(
        workspace_id=workspace.id, first_name="Ayesha", last_name="Khan",
        phone="+15551112222", email="ayesha@example.com",
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture()
def appointment(db_session, workspace, patient, provider):
    appt = Appointment(
        workspace_id=workspace.id, patient_id=patient.id, provider_id=provider.id,
        start_time=WHEN, end_time=WHEN + timedelta(minutes=30), status="scheduled",
    )
    db_session.add(appt)
    db_session.commit()
    return appt


def test_reminder_notifies_patient_and_doctor_and_tracks_every_send(db_session, appointment, patient, provider):
    whatsapp, email = MockWhatsAppProvider(), MockEmailProvider()
    service = NotificationService(db=db_session, whatsapp=whatsapp, email=email)

    results = service.notify_appointment_reminder(
        appointment, patient, clinic_name="Reminder Clinic",
        doctor_name=provider.name, language="en", provider=provider,
    )

    assert all(r.status == "sent" for r in results)
    audiences = {r.audience for r in results}
    assert audiences == {"patient", "provider"}
    assert {r.event_type for r in results} == {"appointment_reminder"}
    # patient reached on whatsapp + email, doctor on whatsapp.
    recipients = {m["to"] for m in whatsapp.sent}
    assert patient.phone in recipients and provider.phone in recipients
    assert "Dr. Bilal Ahmed" in next(m["body"] for m in whatsapp.sent if m["to"] == patient.phone)


def test_reminder_is_not_sent_twice(db_session, appointment, patient, provider):
    whatsapp, email = MockWhatsAppProvider(), MockEmailProvider()
    service = NotificationService(db=db_session, whatsapp=whatsapp, email=email)
    kwargs = dict(clinic_name="Reminder Clinic", doctor_name=provider.name, language="en", provider=provider)

    service.notify_appointment_reminder(appointment, patient, **kwargs)
    service.notify_appointment_reminder(appointment, patient, **kwargs)

    # patient whatsapp + doctor whatsapp = 2, not 4.
    assert len(whatsapp.sent) == 2
    assert len(email.sent) == 1


def test_workspace_notification_language_override(db_session, workspace):
    assert load_notification_language(db_session, workspace.id) == "en"
    db_session.add(
        Integration(
            workspace_id=workspace.id, provider="clinic_notifications", is_active=True,
            config={"notification_language": "ur"},
        )
    )
    db_session.commit()
    assert load_notification_language(db_session, workspace.id) == "ur"
