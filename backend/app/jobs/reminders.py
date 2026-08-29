"""Day-of appointment reminders.

`send_due_reminders` is a plain function (no scheduler, no framework) so it
is directly unit-testable and can also be invoked ad hoc. The scheduler
wrapper that calls it every morning lives in app/jobs/scheduler.py.

Duplicate-prevention strategy (requirement 7):

1.  `Appointment.reminder_sent` is a coarse "already handled" flag. It is
    set True only AFTER every reminder message for the appointment has been
    accepted by the messaging provider — a run that sends nothing, or that
    has any failed send, leaves it False so the next run retries.
2.  The authoritative idempotency guard is one layer down, in
    NotificationService: each individual reminder message is a
    (workspace, appointment, "appointment_reminder", channel, recipient)
    row, and a combination that already has a status="sent" row is never
    re-sent. So even if two runs race (or a crash re-runs a day), no
    patient/doctor is messaged twice.
3.  On PostgreSQL each appointment is re-checked under
    ``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent runners don't both
    process the same row.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.notifications.clinic_config import load_notification_language
from app.integrations.notifications.service import NotificationService
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# Appointment statuses that still warrant a reminder. "cancelled" (and any
# future "completed"/"no_show") are excluded.
_REMINDABLE_STATUSES = ("scheduled", "confirmed", "booked")


@dataclass
class RemindersRunResult:
    considered: int = 0
    reminded: int = 0
    skipped_already_sent: int = 0
    failed: int = 0
    workspace_ids: list[uuid.UUID] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - logging convenience
        return (
            f"considered={self.considered} reminded={self.reminded} "
            f"skipped_already_sent={self.skipped_already_sent} failed={self.failed}"
        )


def _workspace_tz(workspace: Workspace) -> ZoneInfo:
    try:
        return ZoneInfo(workspace.timezone or "UTC")
    except ZoneInfoNotFoundError:
        logger.warning("workspace=%s has invalid timezone %r; using UTC", workspace.id, workspace.timezone)
        return ZoneInfo("UTC")


def _local_day_bounds_utc(tz: ZoneInfo, now: datetime) -> tuple[datetime, datetime]:
    """[start, end) of *today* in `tz`, expressed in UTC."""
    local_now = now.astimezone(tz)
    local_start = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _doctor_display_name(provider: Provider | None) -> str:
    if provider is not None and (provider.name or "").strip():
        return provider.name.strip()
    return "your doctor"


def send_due_reminders(
    db: Session,
    *,
    now: datetime | None = None,
    workspace_id: uuid.UUID | None = None,
    notification_service: NotificationService | None = None,
) -> RemindersRunResult:
    """Send patient + doctor reminders for every appointment scheduled for
    *today* (clinic-local) that hasn't been reminded yet.

    `now` defaults to the current UTC time (injectable for tests).
    `workspace_id` limits the run to one workspace; otherwise every
    workspace is processed against its own timezone.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    notifications = notification_service or NotificationService(db=db)
    result = RemindersRunResult()

    ws_stmt = select(Workspace)
    if workspace_id is not None:
        ws_stmt = ws_stmt.where(Workspace.id == workspace_id)
    workspaces = list(db.execute(ws_stmt).scalars())

    is_postgres = db.get_bind().dialect.name == "postgresql"

    for workspace in workspaces:
        tz = _workspace_tz(workspace)
        day_start_utc, day_end_utc = _local_day_bounds_utc(tz, now)
        language = load_notification_language(db, workspace.id)

        due_ids = list(
            db.execute(
                select(Appointment.id).where(
                    Appointment.workspace_id == workspace.id,
                    Appointment.status.in_(_REMINDABLE_STATUSES),
                    Appointment.reminder_sent.is_(False),
                    Appointment.start_time >= day_start_utc,
                    Appointment.start_time < day_end_utc,
                )
            ).scalars()
        )
        if due_ids:
            result.workspace_ids.append(workspace.id)

        for appointment_id in due_ids:
            result.considered += 1
            processed = _process_one(
                db,
                notifications,
                appointment_id=appointment_id,
                clinic_name=workspace.name,
                language=language,
                is_postgres=is_postgres,
            )
            if processed == "reminded":
                result.reminded += 1
            elif processed == "skipped":
                result.skipped_already_sent += 1
            elif processed == "failed":
                result.failed += 1

    logger.info("day-of reminder run complete: %s", result)
    return result


def _process_one(
    db: Session,
    notifications: NotificationService,
    *,
    appointment_id: uuid.UUID,
    clinic_name: str,
    language: str,
    is_postgres: bool,
) -> str:
    """Process a single appointment in its own transaction. Returns one of
    "reminded" | "skipped" | "failed" | "gone"."""
    try:
        stmt = select(Appointment).where(Appointment.id == appointment_id)
        if is_postgres:
            stmt = stmt.with_for_update(skip_locked=True)
        appointment = db.execute(stmt).scalar_one_or_none()

        if appointment is None:
            db.rollback()
            return "gone"
        if appointment.reminder_sent:
            # Another runner handled it between the outer query and here.
            db.rollback()
            return "skipped"

        patient = db.get(Patient, appointment.patient_id)
        if patient is None:
            logger.warning("appointment=%s has no patient row; skipping reminder", appointment_id)
            db.rollback()
            return "failed"

        provider = db.get(Provider, appointment.provider_id) if appointment.provider_id else None

        messages = notifications.notify_appointment_reminder(
            appointment,
            patient,
            clinic_name=clinic_name,
            doctor_name=_doctor_display_name(provider),
            language=language,
            provider=provider,
        )

        # NotificationService commits each send on its own; re-load the row
        # in this session before mutating it.
        appointment = db.get(Appointment, appointment_id)
        if appointment is None:
            return "gone"

        if any(m.status == "failed" for m in messages):
            logger.warning(
                "appointment=%s reminder had failed sends (%s); leaving reminder_sent=False for retry",
                appointment_id,
                [m.channel for m in messages if m.status == "failed"],
            )
            return "failed"

        appointment.reminder_sent = True
        db.add(appointment)
        db.commit()
        return "reminded"
    except Exception:
        logger.exception("appointment=%s reminder processing raised; will retry next run", appointment_id)
        db.rollback()
        return "failed"
