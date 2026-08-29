import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID


class NotificationMessage(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A single tracked attempt to deliver an outbound WhatsApp/email
    notification (appointment confirmation/cancellation/reschedule, or a
    clinic/receptionist copy of one of those events).

    One row per (workspace, appointment, event_type, channel, recipient)
    delivery attempt. `NotificationService` only ever sends again for a
    combination that doesn't already have a `status="sent"` row — that's
    the duplicate-prevention guard (see app/integrations/notifications/service.py).
    """

    __tablename__ = "notification_messages"

    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # "whatsapp" | "email"
    channel: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # "appointment_confirmation" | "appointment_cancellation" | "appointment_reschedule"
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # "patient" | "clinic" — who this particular copy of the message was addressed to
    audience: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Adapter that handled (or attempted) this send: "mock" | "twilio_whatsapp" |
    # "meta_whatsapp" | "sendgrid"
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # "pending" | "sent" | "failed"
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
