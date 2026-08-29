from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import JSONType


class AIAgent(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """Configuration shell for a workspace's AI receptionist agent.

    No AI behaviour is implemented in this phase — this only stores config."""

    __tablename__ = "ai_agents"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
