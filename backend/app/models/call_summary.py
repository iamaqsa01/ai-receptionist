import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID, JSONType


class CallSummary(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """One summary per call, generated after the call ends."""

    __tablename__ = "call_summaries"

    call_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action_items: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
