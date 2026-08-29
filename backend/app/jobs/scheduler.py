"""Minimal in-process scheduler for the day-of reminder job.

Deliberately NOT Celery/Redis/etc. — this is a single APScheduler
``BackgroundScheduler`` living inside the FastAPI process, started from the
app lifespan (app/main.py). APScheduler is an optional dependency: if it is
not installed the app still starts, it just logs that reminders are
disabled.

The job wakes once an hour and, for each workspace, runs the reminders only
when that workspace's local clock has reached ``settings.reminder_local_hour``
(~08:00). Running hourly + filtering by local hour is what makes a single
trigger correct across workspaces in different timezones, without a
per-workspace cron entry. ``Appointment.reminder_sent`` + the
NotificationService dedup guard make a second pass within the same hour a
no-op, so this is safe even if the trigger fires twice.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.core.config import settings
from app.database.session import SessionLocal
from app.jobs.reminders import send_due_reminders
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

_scheduler = None  # module-level singleton; set by start_reminder_scheduler()


def run_due_reminders_for_all_workspaces(now: datetime | None = None) -> None:
    """Entry point the scheduler calls hourly. Also safe to call manually
    (e.g. from a management shell)."""
    now = now or datetime.now(timezone.utc)
    target_hour = settings.reminder_local_hour
    db = SessionLocal()
    try:
        workspaces = list(db.execute(select(Workspace)).scalars())
        for workspace in workspaces:
            try:
                tz = ZoneInfo(workspace.timezone or "UTC")
            except ZoneInfoNotFoundError:
                tz = ZoneInfo("UTC")
            if now.astimezone(tz).hour != target_hour:
                continue
            logger.info("running day-of reminders for workspace=%s (local hour %s)", workspace.id, target_hour)
            send_due_reminders(db, now=now, workspace_id=workspace.id)
    except Exception:
        logger.exception("day-of reminder scheduler tick failed")
    finally:
        db.close()


def start_reminder_scheduler():
    """Start the hourly reminder scheduler. Returns the scheduler instance,
    or None if APScheduler isn't installed / it's already running."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning(
            "APScheduler is not installed — day-of appointment reminders are disabled. "
            "Install it (pip install APScheduler) to enable them."
        )
        return None

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_due_reminders_for_all_workspaces,
        trigger=CronTrigger(minute=0),  # top of every hour
        id="day_of_appointment_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "reminder scheduler started (hourly; sends at ~%02d:00 workspace-local)",
        settings.reminder_local_hour,
    )
    return scheduler


def shutdown_reminder_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("reminder scheduler stopped")
