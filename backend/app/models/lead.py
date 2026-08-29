from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin


class Lead(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A prospective, not-yet-converted contact captured by the receptionist."""

    __tablename__ = "leads"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
