import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID


class Call(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A single phone call handled by the receptionist (inbound or outbound)."""

    __tablename__ = "calls"

    ai_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("ai_agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The in-memory ConversationState's session id (app.ai.conversation.store)
    # that drove this call — not a foreign key (conversation sessions aren't
    # a DB table), but it's what lets analytics join a Call to the
    # HumanHandoff rows it produced (HumanHandoff.conversation_session_id).
    conversation_session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", nullable=False, index=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
