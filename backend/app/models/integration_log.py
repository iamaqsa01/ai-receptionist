from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import JSONType


class IntegrationLog(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """One row per attempted call to an external provider — calendar sync
    (Phase 8), WhatsApp/email notifications (Phase 9), or a telephony live
    transfer (Phase 10). Distinct from NotificationMessage (which tracks
    only notification deliveries with duplicate-prevention semantics) and
    HumanHandoff (which tracks only escalations) — this is the general
    "did this integration call succeed" log every provider category
    reports into, which is what `integration_failures` in the analytics
    summary counts against."""

    __tablename__ = "integration_logs"

    # "calendar" | "whatsapp" | "email" | "telephony_transfer"
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # The specific adapter that handled (or attempted) the call, e.g.
    # "google", "mock", "twilio_whatsapp", "sendgrid", "twilio", "vapi".
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Short verb phrase: "create_event", "send", "transfer_call", ...
    action: Mapped[str] = mapped_column(String(64), nullable=False)

    # "success" | "failure"
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
