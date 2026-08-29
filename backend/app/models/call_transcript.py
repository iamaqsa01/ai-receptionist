import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID


class CallTranscript(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """One utterance/segment of a call's transcript, in speaking order."""

    __tablename__ = "call_transcripts"

    call_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    spoken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
