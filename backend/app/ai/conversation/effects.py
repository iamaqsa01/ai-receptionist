from dataclasses import dataclass
from datetime import datetime


@dataclass
class BookAppointmentEffect:
    caller_name: str
    phone: str
    service: str
    when: datetime
    department: str | None = None
    provider: str | None = None  # a real provider name, or "no_preference"/None for any


@dataclass
class CancelAppointmentEffect:
    phone: str


@dataclass
class RescheduleAppointmentEffect:
    phone: str
    new_when: datetime


@dataclass
class TransferToHumanEffect:
    reason: str
    # "caller_request" | "repeated_misunderstanding" | "unsupported_request" |
    # "clinic_rule" | "technical_failure" — see app.models.human_handoff.HumanHandoff
    trigger: str = "caller_request"


@dataclass
class UpsertLeadEffect:
    """A caller who has shown interest but hasn't (yet) completed a
    booking — capturing them as a Lead as soon as we know how to reach
    them (a phone number), so front-desk staff can follow up even if the
    caller never finishes qualifying themselves into a Patient."""

    phone: str
    name: str | None
    status: str  # "new" | "qualifying" | "converted"
    source: str = "ai_receptionist"
    notes: str | None = None


Effect = (
    BookAppointmentEffect
    | CancelAppointmentEffect
    | RescheduleAppointmentEffect
    | TransferToHumanEffect
    | UpsertLeadEffect
)
