import hashlib
import json
from datetime import date, time
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


# A voice assistant cannot omit an optional tool argument it never
# collected, so it sends a placeholder instead. Left as-is these fail
# schema validation, and for patient_email that rejects the entire HTTP
# request with a 422 before the booking handler runs -- Vapi receives no
# tool result at all and the caller is left hanging. Treat them as absent.
_BLANK_VALUES = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "null",
    "nil",
    "undefined",
    "unknown",
    "not provided",
}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip().lower() in _BLANK_VALUES:
        return None
    return value


def _direct_tool_call_id(tool_name: str, arguments: dict[str, Any]) -> str:
    """Stable per-invocation id for a flat-body tool call.

    A flat body carries no tool call id of its own. A constant would make
    every booking in one call look like an idempotent replay of the
    first, so the id is derived from the arguments: a Vapi retry sends
    the same body and stays idempotent, while a second, different
    booking in the same call gets its own id.
    """
    digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()
    return f"direct-{tool_name}-{digest[:32]}"


class VapiPhoneNumber(BaseModel):
    number: str = Field(min_length=1, max_length=32)

    model_config = ConfigDict(extra="ignore")


class VapiCall(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    # The number the caller dialed (`phoneNumber`) and the caller's own
    # number (`customer`). Used only to route the call to a workspace; the
    # caller can never name a workspace directly.
    customer: VapiPhoneNumber | None = None
    phone_number: VapiPhoneNumber | None = Field(default=None, alias="phoneNumber")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class VapiToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class VapiToolMessage(BaseModel):
    type: str
    tool_call_list: list[VapiToolCall] = Field(alias="toolCallList", min_length=1)
    # Vapi's current server message places call inside message. The explicit
    # contract for this project places it at the root, so both are accepted.
    call: VapiCall | None = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class VapiToolRequest(BaseModel):
    message: VapiToolMessage | None = None
    call: VapiCall | None = None

    # A Vapi custom tool can be configured to POST its arguments as a flat
    # body rather than the toolCallList envelope, and assistants in the
    # field do exactly that. Rejecting it produced an HTTP 422 with no
    # tool result, so the assistant apologised mid-call and the caller
    # never got an appointment. Both request shapes are accepted.
    service_id: uuid.UUID | None = None
    service_name: str | None = None
    provider_id: uuid.UUID | None = None
    provider_name: str | None = None
    preferred_date: date | None = None
    preferred_time: time | None = None
    max_slots: int | None = None
    availability_token: str | None = None
    patient_name: str | None = None
    patient_phone: str | None = None
    patient_email: EmailStr | None = None
    reason: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator(
        "service_id",
        "service_name",
        "provider_id",
        "provider_name",
        "preferred_date",
        "preferred_time",
        "max_slots",
        "availability_token",
        "patient_name",
        "patient_phone",
        "patient_email",
        "reason",
        mode="before",
    )
    @classmethod
    def blank_optional_is_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def require_tool_calls_message(self) -> "VapiToolRequest":
        if self.message is None:
            arguments = self.model_dump(
                mode="json", exclude_none=True, exclude={"message", "call"}
            )
            if not arguments:
                raise ValueError("message is required when no tool arguments are supplied")
            tool_name = (
                "book_appointment" if "availability_token" in arguments else "check_availability"
            )
            self.message = VapiToolMessage(
                type="tool-calls",
                toolCallList=[
                    VapiToolCall(
                        id=_direct_tool_call_id(tool_name, arguments),
                        name=tool_name,
                        arguments=arguments,
                    )
                ],
            )
        if self.message.type != "tool-calls":
            raise ValueError("message.type must be 'tool-calls'")
        return self

    @property
    def call_id(self) -> str | None:
        call = self.call or self.message.call
        return call.id if call else None

    @property
    def routing_phone_numbers(self) -> list[str]:
        """Numbers to try for phone -> workspace routing.

        Dialed number first (the clinic's own line), caller number second as
        a fallback. Order matters: the dialed number is what identifies the
        workspace; the caller number is only a last resort.
        """
        calls = [self.call, self.message.call]
        numbers: list[str] = []
        for call in calls:
            if call is None:
                continue
            for phone in (call.phone_number, call.customer):
                if phone and phone.number not in numbers:
                    numbers.append(phone.number)
        return numbers


class CheckAvailabilityArguments(BaseModel):
    service_id: uuid.UUID | None = None
    service_name: str | None = Field(default=None, min_length=1, max_length=255)
    provider_id: uuid.UUID | None = None
    provider_name: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_date: date
    preferred_time: time | None = None
    max_slots: int = Field(default=5, ge=1, le=10)

    @field_validator("max_slots", mode="before")
    @classmethod
    def blank_max_slots_is_default(cls, value: Any) -> Any:
        return 5 if _blank_to_none(value) is None else value

    @field_validator("service_name", "provider_name", mode="before")
    @classmethod
    def blank_optional_is_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def require_service_identity(self) -> "CheckAvailabilityArguments":
        if self.service_id is None and self.service_name is None:
            raise ValueError("service_id or service_name is required")
        return self


class BookAppointmentArguments(BaseModel):
    availability_token: str = Field(min_length=1, max_length=4096)
    patient_name: str = Field(min_length=2, max_length=120)
    patient_phone: str = Field(min_length=5, max_length=32)
    patient_email: EmailStr | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("patient_email", "reason", mode="before")
    @classmethod
    def blank_optional_is_none(cls, value: Any) -> Any:
        return _blank_to_none(value)


class VapiToolResult(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    result: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)


class VapiToolResponse(BaseModel):
    results: list[VapiToolResult]

