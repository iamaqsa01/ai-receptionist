import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr

from app.database.types import GUID


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UUIDPKMixin:
    """Adds a UUID primary key column named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds `created_at` / `updated_at` columns maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkspaceOwnedMixin:
    """Adds a `workspace_id` FK for rows that belong to a single tenant workspace."""

    @declared_attr
    def workspace_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            GUID(),
            ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
