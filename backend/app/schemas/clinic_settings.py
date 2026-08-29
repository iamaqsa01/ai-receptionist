import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentTone(str, Enum):
    """Agent preference — how the AI Receptionist should sound."""

    PROFESSIONAL = "Professional"
    EMPATHETIC = "Empathetic"
    FRIENDLY = "Friendly"


class PreferredLanguage(str, Enum):
    """Language the AI Receptionist should primarily speak/write in.

    Covers the local Pakistani languages the live-voice pipeline already
    supports (see ``app.ai.language.pakistan`` — codes ur/pa/skr/sd/ps),
    plus English and a Latin-script "Roman Urdu" option for clinics that
    prefer transliterated written communication (SMS/WhatsApp templates)."""

    URDU = "Urdu"
    ENGLISH = "English"
    ROMAN_URDU = "Roman Urdu"
    PUNJABI = "Punjabi"
    SARAIKI = "Saraiki"
    SINDHI = "Sindhi"
    PASHTO = "Pashto"


class DoctorSetting(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    specialty: str | None = Field(default=None, max_length=255)
    # Individual timings, kept as free text so a clinic can express whatever
    # shape it needs, e.g. "Mon-Fri 9:00-13:00, Sat 10:00-12:00".
    timings: str | None = Field(default=None, max_length=255)
    consultation_fee: float | None = Field(default=None, ge=0)


class AppointmentSettings(BaseModel):
    default_slot_duration_minutes: int = Field(default=30, ge=5, le=480)
    max_daily_bookings: int | None = Field(default=None, ge=1, le=1000)


class GeneralInfo(BaseModel):
    address: str | None = Field(default=None, max_length=500)
    google_maps_link: str | None = Field(default=None, max_length=500)
    parking_available: bool | None = None
    accepted_payment_methods: list[str] = Field(default_factory=list)


class ClinicSettingsUpdate(BaseModel):
    """The complete AI knowledge base a dashboard sends for a workspace.

    Persisted verbatim into the workspace's active ``ai_agents.config``
    under the ``clinic_settings`` key — no new table, same JSON-config
    pattern already used for ``instructions`` / ``supported_languages`` /
    ``escalation_keywords``."""

    model_config = ConfigDict(extra="forbid")

    doctors: list[DoctorSetting] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    appointment_settings: AppointmentSettings = Field(default_factory=AppointmentSettings)
    general_info: GeneralInfo = Field(default_factory=GeneralInfo)
    # Configurable emergency instruction/message the AI must follow when a
    # caller indicates a medical emergency.
    emergency_protocol: str | None = Field(default=None, max_length=2000)
    agent_tone: AgentTone = AgentTone.PROFESSIONAL
    preferred_language: PreferredLanguage = PreferredLanguage.ENGLISH


class ClinicSettingsOut(ClinicSettingsUpdate):
    workspace_id: uuid.UUID
