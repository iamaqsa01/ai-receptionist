import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.integration_log import IntegrationLog

logger = logging.getLogger("app.integration")


def record_integration_log(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category: str,
    provider: str,
    action: str,
    status: str,
    detail: str | None = None,
    extra_data: dict[str, Any] | None = None,
) -> IntegrationLog:
    """Records one attempted call to an external integration (calendar,
    WhatsApp/email notification, telephony transfer) and commits
    independently — same "record the fact even if the caller's own
    transaction later rolls back" rationale as record_audit_log. `status`
    is "success" or "failure"; a "failure" row is what
    analytics.integration_failures counts."""
    entry = IntegrationLog(
        workspace_id=workspace_id,
        category=category,
        provider=provider,
        action=action,
        status=status,
        detail=detail,
        extra_data=extra_data,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    log_fn = logger.warning if status == "failure" else logger.info
    log_fn(
        "integration %s: %s.%s (%s) — %s",
        status, category, provider, action, detail or "ok",
        extra={
            "integration_category": category,
            "integration_provider": provider,
            "integration_action": action,
            "integration_status": status,
        },
    )
    return entry
