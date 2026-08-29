import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPKMixin, WorkspaceOwnedMixin
from app.database.types import GUID


class Appointment(UUIDPKMixin, TimestampMixin, WorkspaceOwnedMixin, Base):
    """A scheduled appointment between a patient and a provider."""

    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "vapi_call_id",
            "vapi_tool_call_id",
            name="uq_appointments_vapi_tool_call",
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("providers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Day-of reminder state (app/jobs/reminders.py). False = the patient/
    # doctor reminder for this appointment has not yet been sent
    # successfully. Set True only once every required reminder message for
    # the appointment has been accepted by the messaging provider, so a
    # partial/failed run is safely retried on the next pass. `server_default`
    # keeps every pre-existing row valid (treated as "not yet reminded").
    reminder_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True
    )

    # External calendar sync (Phase 8). Both nullable: an appointment is
    # valid and fully bookable in our own system whether or not calendar
    # sync is configured/succeeded for its workspace. `unique=True` (with
    # NULLs excluded from the uniqueness check, standard SQL behavior)
    # gives duplicate-event prevention a DB-level backstop in addition to
    # the application-level guard in CalendarSyncService.
    external_calendar_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_calendar_event_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    # Persisted idempotency identity for Vapi retries. Both values are
    # nullable so appointments created by staff or the internal AI flow are
    # unaffected; when present, the composite constraint guarantees one
    # appointment per Vapi tool invocation.
    vapi_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    vapi_tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
