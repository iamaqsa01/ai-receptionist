import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID, JSONType


class HumanHandoff(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A single AI-Receptionist-to-human escalation (Phase 10). Recorded the
    moment ReceptionistService applies a TransferToHumanEffect — i.e.
    *before* any live telephony transfer is attempted — so the handoff
    (reason, conversation context, call state, and timestamp via
    TimestampMixin.created_at) is durable even if the live transfer itself
    then fails."""

    __tablename__ = "human_handoffs"

    call_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The in-memory ConversationState's session id (app.ai.conversation.store)
    # — not a foreign key, since conversation sessions aren't a DB table.
    conversation_session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    # "caller_request" | "repeated_misunderstanding" | "unsupported_request" |
    # "clinic_rule" | "technical_failure"
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Snapshot of the conversation transcript up to the moment of transfer —
    # a list of {"role", "text", "language", "timestamp"} objects, one per
    # ConversationState.Turn.
    conversation_context: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    # Snapshot of ConversationState at the moment of transfer (language,
    # intent, caller info, appointment draft, missing fields, status).
    call_state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    # "pending" (recorded, no live transfer attempted or possible) |
    # "transferred" (live transfer succeeded) | "failed" (live transfer was
    # attempted but the provider rejected/couldn't complete it)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    transfer_target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transfer_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
