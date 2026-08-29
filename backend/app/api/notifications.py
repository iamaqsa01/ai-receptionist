from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.notification_message import NotificationMessage
from app.schemas.notification import NotificationMessageOut

router = APIRouter(prefix="/workspaces/{workspace_id}/notification-messages", tags=["notifications"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.get("", response_model=list[NotificationMessageOut])
def list_notification_messages(
    ctx: TenantContext = Depends(require_permission("notifications:read")),
    db: Session = Depends(get_db),
) -> list[NotificationMessage]:
    return list(
        db.execute(
            select(NotificationMessage)
            .where(NotificationMessage.workspace_id == ctx.workspace_id)
            .order_by(NotificationMessage.created_at.desc())
        ).scalars()
    )
