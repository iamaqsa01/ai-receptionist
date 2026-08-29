import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger("app.audit")


def record_audit_log(
    db: Session,
    *,
    action: str,
    resource_type: str,
    workspace_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    extra_data: dict[str, Any] | None = None,
) -> AuditLog:
    """Appends one immutable AuditLog row and commits it independently of
    whatever transaction the caller is in the middle of — an audit record
    for an action that already happened must survive even if something
    later in the same request rolls back. `action` is a short verb phrase
    ("user.login", "lead.created", "workspace.member_added", ...);
    `resource_type`/`resource_id` identify what the action was performed
    on. Also emitted as a structured log line (request_id/workspace_id are
    picked up automatically from the bound logging context) so audit
    events show up in both places without duplicating call sites."""
    entry = AuditLog(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        extra_data=extra_data,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(
        "audit: %s on %s%s",
        action,
        resource_type,
        f" ({resource_id})" if resource_id else "",
        extra={
            "audit_action": action,
            "audit_resource_type": resource_type,
            "audit_resource_id": str(resource_id) if resource_id else None,
            "audit_actor_user_id": str(actor_user_id) if actor_user_id else None,
        },
    )
    return entry
