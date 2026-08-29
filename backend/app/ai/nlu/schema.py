from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"
    APPOINTMENT_BOOKING = "appointment_booking"
    APPOINTMENT_CANCELLATION = "appointment_cancellation"
    APPOINTMENT_RESCHEDULE = "appointment_reschedule"
    HUMAN_TRANSFER = "human_transfer"
    UNSUPPORTED_REQUEST = "unsupported_request"
    CLINICAL_REQUEST = "clinical_request"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


@dataclass
class ExtractedEntities:
    caller_name: str | None = None
    phone_number: str | None = None
    service: str | None = None
    provider: str | None = None  # a real provider name, or the sentinel "no_preference"
    appointment_datetime: datetime | None = None


@dataclass
class NLUResult:
    intent: Intent
    confidence: float
    entities: ExtractedEntities = field(default_factory=ExtractedEntities)
