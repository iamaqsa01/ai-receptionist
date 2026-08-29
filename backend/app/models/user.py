from typing import List

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    """A person who can sign in. Global identity — not tenant-owned; access to
    a given workspace is granted via WorkspaceMember."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # NOTE: onboarding state is NOT a property of the user. It lives on
    # Workspace.is_onboarded — a user may have onboarded workspace A but not
    # workspace B. (The former User.is_onboarded column was moved in the
    # "move onboarding state to workspace" migration.)

    # Platform-wide role, not scoped to a workspace. Bypasses workspace
    # membership checks entirely. Workspace-scoped roles (Owner/Admin/
    # Receptionist/Analyst) live on WorkspaceMember.role instead.
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships: Mapped[List["WorkspaceMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
