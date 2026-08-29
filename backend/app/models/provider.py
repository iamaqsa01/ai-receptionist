from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin


class Provider(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A staff member / practitioner appointments can be booked with."""

    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
