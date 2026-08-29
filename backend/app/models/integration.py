from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import JSONType


class Integration(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A connection to a third-party provider (e.g. calendar, telephony).

    `config` holds non-sensitive settings; secrets belong in a secrets
    manager, not this table."""

    __tablename__ = "integrations"

    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
