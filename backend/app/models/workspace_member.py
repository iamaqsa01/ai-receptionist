import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import WorkspaceRole
from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID


class WorkspaceMember(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """Join table granting a user a role within a workspace."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), default=WorkspaceRole.RECEPTIONIST.value, nullable=False)

    workspace: Mapped["Workspace"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")
