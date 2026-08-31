import uuid
from datetime import time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    specialty: str | None = Field(default=None, max_length=120)
    # Individual timings, kept as free text so a clinic can express whatever
    # shape it needs, e.g. "Mon-Fri 9:00-13:00, Sat 10:00-12:00".
    timings: str | None = Field(default=None, max_length=255)
    consultation_fee: float | None = Field(default=None, ge=0)


class AppointmentSettings(BaseModel):
    default_slot_duration_minutes: int = Field(default=30, ge=5, le=480)
    max_daily_bookings: int | None = Field(default=None, ge=1, le=1000)


class BusinessHoursSetting(BaseModel):
    """One clinic-wide operating-hours row (0=Monday .. 6=Sunday).

    These values map directly onto the existing ``BusinessHours`` model;
    keeping them structured prevents the onboarding form's display text
    from becoming a second, unparseable scheduling source of truth.
    """

    day_of_week: int = Field(ge=0, le=6)
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False

    @model_validator(mode="after")
    def validate_times(self) -> "BusinessHoursSetting":
        if self.is_closed:
            self.open_time = None
            self.close_time = None
            return self
        if self.open_time is None or self.close_time is None:
            raise ValueError("open_time and close_time are required when the clinic is open")
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        return self


class GeneralInfo(BaseModel):
    address: str | None = Field(default=None, max_length=500)
    google_maps_link: str | None = Field(default=None, max_length=500)
    parking_available: bool | None = None
    accepted_payment_methods: list[str] = Field(default_factory=list)


class ClinicSettingsUpdate(BaseModel):
    """The complete AI knowledge base a dashboard sends for a workspace.

    Persisted into the workspace's active ``ai_agents.config`` under the
    ``clinic_settings`` key. Booking-related fields are also synchronized
    into the existing normalized scheduling models by the API service.
    """

    model_config = ConfigDict(extra="forbid")

    doctors: list[DoctorSetting] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    business_hours: list[BusinessHoursSetting] = Field(default_factory=list)
    appointment_settings: AppointmentSettings = Field(default_factory=AppointmentSettings)
    general_info: GeneralInfo = Field(default_factory=GeneralInfo)
    # Configurable emergency instruction/message the AI must follow when a
    # caller indicates a medical emergency.
    emergency_protocol: str | None = Field(default=None, max_length=2000)
    agent_tone: AgentTone = AgentTone.PROFESSIONAL
    preferred_language: PreferredLanguage = PreferredLanguage.ENGLISH

    @model_validator(mode="after")
    def validate_unique_booking_configuration(self) -> "ClinicSettingsUpdate":
        doctor_names = [doctor.name.strip().casefold() for doctor in self.doctors]
        if any(not name for name in doctor_names):
            raise ValueError("doctor names cannot be blank")
        if len(doctor_names) != len(set(doctor_names)):
            raise ValueError("doctor names must be unique within a clinic")

        service_names = [name.strip().casefold() for name in self.services]
        if any(not name for name in service_names):
            raise ValueError("service names cannot be blank")
        if any(len(name) > 255 for name in self.services):
            raise ValueError("service names cannot exceed 255 characters")
        if len(service_names) != len(set(service_names)):
            raise ValueError("service names must be unique within a clinic")

        weekdays = [hours.day_of_week for hours in self.business_hours]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("business_hours may contain each weekday only once")
        return self


class ClinicSettingsOut(ClinicSettingsUpdate):
    workspace_id: uuid.UUID
