import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.ai.nlu.schema import Intent


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    AWAITING_LANGUAGE_CHOICE = "awaiting_language_choice"
    NEEDS_HUMAN = "needs_human"
    COMPLETED = "completed"


@dataclass
class Turn:
    role: str  # "caller" | "assistant"
    text: str
    language: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CallerInfo:
    name: str | None = None
    phone: str | None = None


@dataclass
class AppointmentDraft:
    service: str | None = None
    department: str | None = None  # resolved from `service` via the workspace's own mapping
    provider: str | None = None  # a real provider name, or "no_preference"
    when: datetime | None = None
    new_when: datetime | None = None  # target time for a reschedule


@dataclass
class ConversationState:
    """The AI Receptionist's working memory for one call/chat session:
    who's calling, what they want, what's been collected so far, and the
    running transcript. This is intentionally separate from any DB model —
    it's ephemeral session state, not a durable business record (durable
    outcomes — patients, appointments, notifications — are written to the
    database only once a flow actually completes; see receptionist_service.py).
    """

    session_id: uuid.UUID
    workspace_id: uuid.UUID
    language: str | None = None
    status: ConversationStatus = ConversationStatus.ACTIVE
    intent: Intent | None = None
    caller: CallerInfo = field(default_factory=CallerInfo)
    appointment: AppointmentDraft = field(default_factory=AppointmentDraft)
    history: list[Turn] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    low_confidence_strikes: int = 0
    # Consecutive turns classified as a low-confidence GENERAL_INQUIRY (the
    # NLU engine's fallback when nothing else matches) — distinct from
    # low_confidence_strikes above, which tracks language-detection
    # uncertainty specifically. Reset to 0 the moment any other intent is
    # recognized. See ConversationEngine._UNCLEAR_INTENT_TRANSFER_THRESHOLD.
    unclear_intent_strikes: int = 0
    # True once all booking requirements are collected and validated and
    # the caller has been asked "shall I go ahead and book it?" — while
    # True, the next caller turn is interpreted as a yes/no answer to that
    # question rather than re-run through normal intent classification.
    pending_booking_confirmation: bool = False

    def add_turn(self, role: str, text: str, language: str | None = None) -> None:
        self.history.append(Turn(role=role, text=text, language=language))
