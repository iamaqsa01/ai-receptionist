import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.notifications.templates import normalize_notification_language
from app.models.integration import Integration

_INTEGRATION_PROVIDER = "clinic_notifications"


@dataclass
class ClinicContact:
    whatsapp_number: str | None
    email: str | None


def load_notification_language(db: Session, workspace_id: uuid.UUID) -> str:
    """The language appointment reminders/confirmations for this workspace
    are written in — always "en" or "ur", never anything else, and
    completely independent of the language any call was conducted in. A
    workspace overrides the deployment default via its clinic_notifications
    integration config ("notification_language")."""
    integration = db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.provider == _INTEGRATION_PROVIDER,
            Integration.is_active.is_(True),
        )
    ).scalar_one_or_none()
    configured = None
    if integration is not None:
        configured = integration.config.get("notification_language")
    return normalize_notification_language(configured or settings.notification_default_language)


def load_clinic_contact(db: Session, workspace_id: uuid.UUID) -> ClinicContact | None:
    """Returns this workspace's clinic/receptionist notification contact,
    or None if the workspace hasn't configured one — opt-in per workspace
    via an `integrations` row, exactly like calendar sync
    (app.integrations.calendar.config.load_calendar_integration)."""
    integration = db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.provider == _INTEGRATION_PROVIDER,
            Integration.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if integration is None:
        return None

    return ClinicContact(
        whatsapp_number=integration.config.get("whatsapp_number") or None,
        email=integration.config.get("email") or None,
    )
