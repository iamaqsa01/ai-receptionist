import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.notifications import templates
from app.integrations.notifications.base import EmailProvider, WhatsAppProvider
from app.integrations.notifications.clinic_config import load_clinic_contact
from app.integrations.notifications.email_factory import get_email_provider
from app.integrations.notifications.exceptions import NotificationError
from app.integrations.notifications.whatsapp_factory import get_whatsapp_provider
from app.models.appointment import Appointment
from app.models.notification_message import NotificationMessage
from app.models.patient import Patient
from app.models.provider import Provider
from app.services.integration_log import record_integration_log

logger = logging.getLogger(__name__)

_BODY_BUILDERS = {
    "appointment_confirmation": templates.appointment_confirmation_body,
    "appointment_cancellation": templates.appointment_cancellation_body,
    "appointment_reschedule": templates.appointment_reschedule_body,
}


class NotificationService:
    """Sends WhatsApp/email notifications for the three appointment
    lifecycle events (confirmation, cancellation, reschedule) to both the
    patient and, if the workspace has configured one, the
    clinic/receptionist contact — and tracks every attempt as a
    NotificationMessage row (message id, recipient, status, timestamp,
    failure reason).

    Duplicate prevention: a (workspace, appointment, event_type, channel,
    recipient) combination that already has a `status="sent"` row is never
    sent again — the existing row is returned instead. A prior `"failed"`
    row does not block a retry, matching the same "only success is
    terminal" philosophy as CalendarSyncService's duplicate-event guard.
    """

    def __init__(self, db: Session, whatsapp: WhatsAppProvider | None = None, email: EmailProvider | None = None) -> None:
        self.db = db
        self.whatsapp = whatsapp or get_whatsapp_provider()
        self.email = email or get_email_provider()

    def _find_sent(
        self, workspace_id: uuid.UUID, appointment_id: uuid.UUID | None, event_type: str, channel: str, recipient: str
    ) -> NotificationMessage | None:
        return self.db.execute(
            select(NotificationMessage).where(
                NotificationMessage.workspace_id == workspace_id,
                NotificationMessage.appointment_id == appointment_id,
                NotificationMessage.event_type == event_type,
                NotificationMessage.channel == channel,
                NotificationMessage.recipient == recipient,
                NotificationMessage.status == "sent",
            )
        ).scalar_one_or_none()

    def _send_whatsapp(
        self,
        *,
        workspace_id: uuid.UUID,
        appointment_id: uuid.UUID | None,
        event_type: str,
        audience: str,
        to: str,
        body: str,
    ) -> NotificationMessage:
        existing = self._find_sent(workspace_id, appointment_id, event_type, "whatsapp", to)
        if existing is not None:
            return existing

        record = NotificationMessage(
            workspace_id=workspace_id,
            appointment_id=appointment_id,
            channel="whatsapp",
            event_type=event_type,
            audience=audience,
            recipient=to,
            provider=self.whatsapp.name,
            status="pending",
            body=body,
        )
        try:
            result = self.whatsapp.send(to, body)
        except NotificationError as exc:
            logger.error("WhatsApp send failed (event=%s, to=%s): %s", event_type, to, exc, exc_info=True)
            record.status = "failed"
            record.failure_reason = str(exc)
        else:
            record.status = "sent"
            record.provider_message_id = result.provider_message_id
            record.sent_at = datetime.now(timezone.utc)

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        record_integration_log(
            self.db, workspace_id=workspace_id, category="whatsapp", provider=self.whatsapp.name,
            action="send", status="success" if record.status == "sent" else "failure",
            detail=record.failure_reason,
        )
        return record

    def _send_email(
        self,
        *,
        workspace_id: uuid.UUID,
        appointment_id: uuid.UUID | None,
        event_type: str,
        audience: str,
        to: str,
        subject: str,
        body: str,
    ) -> NotificationMessage:
        existing = self._find_sent(workspace_id, appointment_id, event_type, "email", to)
        if existing is not None:
            return existing

        record = NotificationMessage(
            workspace_id=workspace_id,
            appointment_id=appointment_id,
            channel="email",
            event_type=event_type,
            audience=audience,
            recipient=to,
            provider=self.email.name,
            status="pending",
            subject=subject,
            body=body,
        )
        try:
            result = self.email.send(to, subject, body)
        except NotificationError as exc:
            logger.error("Email send failed (event=%s, to=%s): %s", event_type, to, exc, exc_info=True)
            record.status = "failed"
            record.failure_reason = str(exc)
        else:
            record.status = "sent"
            record.provider_message_id = result.provider_message_id
            record.sent_at = datetime.now(timezone.utc)

        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        record_integration_log(
            self.db, workspace_id=workspace_id, category="email", provider=self.email.name,
            action="send", status="success" if record.status == "sent" else "failure",
            detail=record.failure_reason,
        )
        return record

    def notify_appointment_event(
        self,
        event_type: str,
        appointment: Appointment,
        patient: Patient,
        *,
        service_summary: str,
        provider: Provider | None = None,
    ) -> list[NotificationMessage]:
        """event_type: one of "appointment_confirmation" / "appointment_cancellation" /
        "appointment_reschedule". Sends a patient-facing copy (WhatsApp to
        patient.phone, email to patient.email — whichever are on file) and,
        if the workspace has an active clinic_notifications integration, a
        clinic-facing copy on the same channels. Returns every
        NotificationMessage row touched (new sends and any deduped
        existing ones)."""
        body_builder = _BODY_BUILDERS[event_type]
        patient_name = f"{patient.first_name} {patient.last_name}".strip()
        subject = templates.EMAIL_SUBJECTS[event_type]

        results: list[NotificationMessage] = []

        patient_body = body_builder(patient_name, service_summary, appointment.start_time)
        if patient.phone:
            results.append(
                self._send_whatsapp(
                    workspace_id=appointment.workspace_id,
                    appointment_id=appointment.id,
                    event_type=event_type,
                    audience="patient",
                    to=patient.phone,
                    body=patient_body,
                )
            )
        if patient.email:
            results.append(
                self._send_email(
                    workspace_id=appointment.workspace_id,
                    appointment_id=appointment.id,
                    event_type=event_type,
                    audience="patient",
                    to=patient.email,
                    subject=subject,
                    body=patient_body,
                )
            )

        # Provider/doctor copy: only when the caller passed the resolved
        # provider (i.e. the booking business logic assigned a specific
        # doctor) and that provider has a contact method on file. Reuses
        # the staff-facing "clinic" wording, addressed to the provider.
        if provider is not None:
            provider_label = templates.CLINIC_EVENT_LABELS[event_type]
            provider_body = templates.clinic_notification_body(
                provider_label, patient_name, service_summary, appointment.start_time
            )
            if provider.phone:
                results.append(
                    self._send_whatsapp(
                        workspace_id=appointment.workspace_id,
                        appointment_id=appointment.id,
                        event_type=event_type,
                        audience="provider",
                        to=provider.phone,
                        body=provider_body,
                    )
                )
            if provider.email:
                results.append(
                    self._send_email(
                        workspace_id=appointment.workspace_id,
                        appointment_id=appointment.id,
                        event_type=event_type,
                        audience="provider",
                        to=provider.email,
                        subject=f"{provider_label}: {patient_name}",
                        body=provider_body,
                    )
                )

        clinic_contact = load_clinic_contact(self.db, appointment.workspace_id)
        if clinic_contact is not None:
            clinic_label = templates.CLINIC_EVENT_LABELS[event_type]
            clinic_body = templates.clinic_notification_body(
                clinic_label, patient_name, service_summary, appointment.start_time
            )
            if clinic_contact.whatsapp_number:
                results.append(
                    self._send_whatsapp(
                        workspace_id=appointment.workspace_id,
                        appointment_id=appointment.id,
                        event_type=event_type,
                        audience="clinic",
                        to=clinic_contact.whatsapp_number,
                        body=clinic_body,
                    )
                )
            if clinic_contact.email:
                results.append(
                    self._send_email(
                        workspace_id=appointment.workspace_id,
                        appointment_id=appointment.id,
                        event_type=event_type,
                        audience="clinic",
                        to=clinic_contact.email,
                        subject=f"{clinic_label}: {patient_name}",
                        body=clinic_body,
                    )
                )

        return results

    def notify_appointment_reminder(
        self,
        appointment: Appointment,
        patient: Patient,
        *,
        clinic_name: str,
        doctor_name: str,
        language: str,
        provider: Provider | None = None,
    ) -> list[NotificationMessage]:
        """Day-of reminder for one appointment. Sends the patient reminder
        (WhatsApp + email, whichever are on file) and — when a provider with
        a contact method is assigned — the doctor reminder.

        The message is only ever generated in English or Urdu (`language` is
        collapsed onto one of those), independent of the language the call
        was conducted in. Every attempt is tracked as a NotificationMessage
        row and de-duplicated the same way every other event is: a
        (workspace, appointment, "appointment_reminder", channel, recipient)
        combination that already succeeded is never re-sent.
        """
        event_type = "appointment_reminder"
        subject = templates.reminder_email_subject(language)
        results: list[NotificationMessage] = []

        patient_body = templates.patient_reminder_body(
            language, doctor_name, clinic_name, appointment.start_time
        )
        if patient.phone:
            results.append(
                self._send_whatsapp(
                    workspace_id=appointment.workspace_id,
                    appointment_id=appointment.id,
                    event_type=event_type,
                    audience="patient",
                    to=patient.phone,
                    body=patient_body,
                )
            )
        if patient.email:
            results.append(
                self._send_email(
                    workspace_id=appointment.workspace_id,
                    appointment_id=appointment.id,
                    event_type=event_type,
                    audience="patient",
                    to=patient.email,
                    subject=subject,
                    body=patient_body,
                )
            )

        if provider is not None and (provider.phone or provider.email):
            patient_name = f"{patient.first_name} {patient.last_name}".strip()
            doctor_body = templates.doctor_reminder_body(language, patient_name, appointment.start_time)
            if provider.phone:
                results.append(
                    self._send_whatsapp(
                        workspace_id=appointment.workspace_id,
                        appointment_id=appointment.id,
                        event_type=event_type,
                        audience="provider",
                        to=provider.phone,
                        body=doctor_body,
                    )
                )
            if provider.email:
                results.append(
                    self._send_email(
                        workspace_id=appointment.workspace_id,
                        appointment_id=appointment.id,
                        event_type=event_type,
                        audience="provider",
                        to=provider.email,
                        subject=subject,
                        body=doctor_body,
                    )
                )

        return results
