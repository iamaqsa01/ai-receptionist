import re
import uuid
from datetime import time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


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


class BusinessType(str, Enum):
    """The kind of business this workspace runs, chosen during onboarding.

    Drives which ``BusinessContext`` fields the onboarding form collects and
    (see ``app.api.workspaces``) whether the clinic-specific onboarding
    requirements (doctors / services / seven-day hours) apply.
    """

    SOFTWARE_AGENCY = "Software Agency"
    CLINIC = "Clinic"
    REAL_ESTATE = "Real Estate"
    OTHER = "Other"


_HTTP_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def _clean_optional_url(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if len(v) > 500:
        raise ValueError(f"{label} must be 500 characters or fewer")
    if not _HTTP_URL_RE.match(v):
        raise ValueError(f"{label} must be a valid URL starting with http:// or https://")
    return v


class BusinessContext(BaseModel):
    """Type-specific business information for the AI receptionist knowledge
    base. Every field is optional; the onboarding form only sends the keys
    relevant to the chosen ``business_type``, and this model serializes only
    the values that were actually provided (empty defaults are dropped) so
    the persisted JSON stays clean and deterministic.
    """

    model_config = ConfigDict(extra="forbid")

    # Software Agency
    core_services: list[str] = Field(default_factory=list)
    minimum_pricing: str | None = Field(default=None, max_length=120)
    discovery_call_booking_link: str | None = Field(default=None, max_length=500)
    # Clinic  (doctor_specializations is derived from ``doctors[].specialty``
    # by the onboarding form — never a separate manual input; clinic hours
    # stay in ``ClinicSettingsUpdate.business_hours``.)
    doctor_specializations: list[str] = Field(default_factory=list)
    appointment_booking_link: str | None = Field(default=None, max_length=500)
    # Real Estate
    property_services: list[str] = Field(default_factory=list)
    areas_served: list[str] = Field(default_factory=list)
    minimum_budget: str | None = Field(default=None, max_length=120)
    viewing_booking_link: str | None = Field(default=None, max_length=500)
    # Other
    custom_fields: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "BusinessContext":
        self.discovery_call_booking_link = _clean_optional_url(
            self.discovery_call_booking_link, "discovery_call_booking_link"
        )
        self.appointment_booking_link = _clean_optional_url(
            self.appointment_booking_link, "appointment_booking_link"
        )
        self.viewing_booking_link = _clean_optional_url(self.viewing_booking_link, "viewing_booking_link")

        for label, group in (
            ("core_services", self.core_services),
            ("doctor_specializations", self.doctor_specializations),
            ("property_services", self.property_services),
            ("areas_served", self.areas_served),
        ):
            cleaned_list = [item.strip() for item in group]
            if any(not item for item in cleaned_list):
                raise ValueError(f"{label} entries cannot be blank")
            if len(cleaned_list) != len({item.casefold() for item in cleaned_list}):
                raise ValueError(f"{label} entries must be unique")
            setattr(self, label, cleaned_list)

        cleaned_custom: dict[str, str] = {}
        for raw_key, raw_value in self.custom_fields.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("custom_fields keys cannot be blank")
            if len(key) > 100:
                raise ValueError("custom_fields keys must be 100 characters or fewer")
            if key.casefold() in {k.casefold() for k in cleaned_custom}:
                raise ValueError(f"duplicate custom field key: {key!r}")
            value = "" if raw_value is None else str(raw_value).strip()
            if not value:
                raise ValueError(f"custom field {key!r} must have a non-empty value")
            if len(value) > 1000:
                raise ValueError(f"custom field {key!r} value must be 1000 characters or fewer")
            cleaned_custom[key] = value
        self.custom_fields = cleaned_custom
        return self

    @model_serializer(mode="wrap")
    def _serialize(self, handler):  # noqa: ANN001 - pydantic serializer signature
        data = handler(self)
        return {key: value for key, value in data.items() if value not in (None, "", [], {})}


# Which BusinessContext keys each business type is allowed to carry. Anything
# outside its set is rejected so the persisted context never mixes shapes.
_BUSINESS_CONTEXT_KEYS: dict[BusinessType, set[str]] = {
    BusinessType.SOFTWARE_AGENCY: {"core_services", "minimum_pricing", "discovery_call_booking_link"},
    BusinessType.CLINIC: {"doctor_specializations", "appointment_booking_link"},
    BusinessType.REAL_ESTATE: {"property_services", "areas_served", "minimum_budget", "viewing_booking_link"},
    BusinessType.OTHER: {"custom_fields"},
}


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
    # Dynamic, context-aware onboarding (added Phase 20). ``business_type`` is
    # optional so every pre-existing payload keeps validating unchanged;
    # ``business_context`` only ever carries the keys for the chosen type.
    business_type: BusinessType | None = None
    business_context: BusinessContext = Field(default_factory=BusinessContext)

    @model_validator(mode="after")
    def validate_business_context(self) -> "ClinicSettingsUpdate":
        present = set(self.business_context.model_dump().keys())  # already pruned to non-empty
        if self.business_type is None:
            if present:
                raise ValueError("business_context can only be set together with a business_type")
            return self
        allowed = _BUSINESS_CONTEXT_KEYS[self.business_type]
        unexpected = present - allowed
        if unexpected:
            raise ValueError(
                f"business_context for '{self.business_type.value}' cannot include "
                f"{sorted(unexpected)}; allowed keys: {sorted(allowed)}"
            )
        return self

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
