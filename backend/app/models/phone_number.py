import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin
from app.database.types import GUID


class PhoneNumber(UUIDPKMixin, TimestampMixin, Base):
    """A phone number assigned to a workspace for inbound call routing.

    The dialed number on an incoming Vapi call is normalised to E.164 and
    looked up here to decide which workspace the call belongs to. `number`
    is globally unique — one phone number routes to exactly one workspace.
    """

    __tablename__ = "phone_numbers"
    __table_args__ = (UniqueConstraint("number", name="uq_phone_numbers_number"),)

    number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
