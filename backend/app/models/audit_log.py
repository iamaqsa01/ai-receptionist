import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPKMixin
from app.database.types import GUID, JSONType


class AuditLog(UUIDPKMixin, Base):
    """Immutable record of an action taken in the system. Append-only: no
    updated_at, since audit rows must never be edited after creation."""

    __tablename__ = "audit_logs"

    # Nullable: some audited actions are system-level and not scoped to a
    # single workspace (e.g. platform-level admin actions).
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
