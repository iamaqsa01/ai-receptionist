from typing import List

from sqlalchemy import Boolean, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPKMixin


class Workspace(UUIDPKMixin, TimestampMixin, Base):
    """A tenant. All tenant-owned data hangs off a workspace_id."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    # False until this workspace completes the clinic-setup onboarding flow.
    # Flipped to True by the first successful
    # PUT /workspaces/{id}/clinic-settings for THIS workspace. Onboarding is
    # per-workspace, not per-user: a user who owns several workspaces (e.g.
    # branches) onboards each one independently. `get_current_onboarded_tenant`
    # (app/api/deps.py) gates every workspace-scoped data route on it, and the
    # frontend routes to the wizard until it flips.
    is_onboarded: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    members: Mapped[List["WorkspaceMember"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
