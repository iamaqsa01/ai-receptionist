from datetime import time

from sqlalchemy import Boolean, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin


class BusinessHours(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """Operating hours per weekday for a workspace (0=Monday .. 6=Sunday)."""

    __tablename__ = "business_hours"
    __table_args__ = (
        UniqueConstraint("workspace_id", "day_of_week", name="uq_business_hours_workspace_day"),
    )

    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
