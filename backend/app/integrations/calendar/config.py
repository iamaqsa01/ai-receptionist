import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration import Integration

_INTEGRATION_PROVIDER = "google_calendar"


@dataclass
class CalendarIntegrationConfig:
    calendar_id: str


def load_calendar_integration(db: Session, workspace_id: uuid.UUID) -> CalendarIntegrationConfig | None:
    """Returns this workspace's calendar configuration, or None if the
    workspace hasn't turned on calendar sync at all — calendar integration
    is opt-in per workspace (via an `integrations` row, is_active=True),
    exactly like every other workspace-specific behavior in this project."""
    integration = db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.provider == _INTEGRATION_PROVIDER,
            Integration.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if integration is None:
        return None

    calendar_id = integration.config.get("calendar_id") or "primary"
    return CalendarIntegrationConfig(calendar_id=calendar_id)
