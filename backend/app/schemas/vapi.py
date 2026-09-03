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


# Name given to the tool call synthesised from a flat body. The endpoint
# URL already says which tool was invoked, so the name is not inferred
# from the arguments -- inference broke when the assistant sent every
# argument empty, which is exactly when a clear error matters most.
FLAT_TOOL_CALL_NAME = "vapi_flat_body"


# A caller says "morning", never "09:00". The schema wanted HH:MM and
# rejected the whole request, which reaches Vapi as no tool result.
_TIME_WORDS = {
    "early morning": "08:00",
    "morning": "09:00",
    "late morning": "11:00",
    "noon": "12:00",
    "midday": "12:00",
    "lunchtime": "12:00",
    "early afternoon": "13:00",
    "afternoon": "13:00",
    "late afternoon": "16:00",
    "evening": "17:00",
    "night": "19:00",
    "subah": "09:00",
    "dopahar": "13:00",
    "sham": "17:00",
    "shaam": "17:00",
    "raat": "19:00",
}


def _coerce_time(value: Any) -> Any:
    """Map a spoken time-of-day onto a clock time, or drop it entirely.

    An unreadable time means "no preference", which returns the day's
    slots and lets the caller choose. Failing the request instead told
    the assistant nothing and ended the booking.
    """
    value = _blank_to_none(value)
    if not isinstance(value, str):
        return value
    key = value.strip().lower()
    if key in _TIME_WORDS:
        return _TIME_WORDS[key]
    try:
        time.fromisoformat(key)
    except ValueError:
        return None
    return key


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

    # Routing identity for a flat body, supplied by Vapi's Static Body
    # Fields ({{phoneNumber.number}}, {{customer.number}}, {{call.id}}).
    # These are server-trusted: Vapi fills them from call signalling, so
    # unlike a tool argument the model cannot choose which clinic a
    # request routes to. Without them a flat body carries no call object
    # and phone-number routing has nothing to resolve a workspace from.
    called_number: str | None = None
    caller_number: str | None = None
    vapi_call_id: str | None = Field(default=None, alias="call_id")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

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
        "called_number",
        "caller_number",
        "vapi_call_id",
        mode="before",
    )
    @classmethod
    def blank_optional_is_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("preferred_time", mode="before")
    @classmethod
    def spoken_time_is_a_clock_time(cls, value: Any) -> Any:
        return _coerce_time(value)

    _ROUTING_FIELDS = {"called_number", "caller_number", "vapi_call_id"}

    @model_validator(mode="after")
    def require_tool_calls_message(self) -> "VapiToolRequest":
        if self.call is None and (
            self.called_number or self.caller_number or self.vapi_call_id
        ):
            self.call = VapiCall(
                id=self.vapi_call_id or "vapi-static-body",
                phoneNumber=(
                    VapiPhoneNumber(number=self.called_number) if self.called_number else None
                ),
                customer=(
                    VapiPhoneNumber(number=self.caller_number) if self.caller_number else None
                ),
            )
        if self.message is None:
            arguments = self.model_dump(
                mode="json",
                exclude_none=True,
                exclude={"message", "call"} | self._ROUTING_FIELDS,
            )
            # An assistant that has collected nothing sends every argument
            # empty. Refusing the request outright returned a 422, which
            # reaches Vapi as no tool result, so the assistant only knew
            # "something broke". Let it through: argument validation then
            # names the missing fields and the call can recover.
            self.message = VapiToolMessage(
                type="tool-calls",
                toolCallList=[
                    VapiToolCall(
                        id=_direct_tool_call_id(FLAT_TOOL_CALL_NAME, arguments),
                        name=FLAT_TOOL_CALL_NAME,
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

    @field_validator("preferred_time", mode="before")
    @classmethod
    def spoken_time_is_a_clock_time(cls, value: Any) -> Any:
        return _coerce_time(value)

    @model_validator(mode="after")
    def require_service_identity(self) -> "CheckAvailabilityArguments":
        if self.service_id is None and self.service_name is None:
            raise ValueError("service_id or service_name is required")
        return self


class BookAppointmentArguments(BaseModel):
    # The token identifies the exact slot the caller chose and is still
    # preferred. It is a ~300 character JWT the assistant must copy back
    # verbatim, and in production it routinely arrives empty: the model
    # reads the slots aloud, then sends "" and the booking dies. So the
    # slot can also be named the way the caller named it, by date and
    # time. Nothing is trusted either way -- business hours, conflicts
    # and past times are all re-checked before anything is written.
    availability_token: str | None = Field(default=None, max_length=4096)
    service_id: uuid.UUID | None = None
    service_name: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=255)
    preferred_date: date | None = None
    preferred_time: time | None = None
    patient_name: str = Field(min_length=2, max_length=120)
    patient_phone: str = Field(min_length=5, max_length=32)
    patient_email: EmailStr | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "availability_token",
        "service_name",
        "provider_name",
        "patient_email",
        "reason",
        mode="before",
    )
    @classmethod
    def blank_optional_is_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("preferred_time", mode="before")
    @classmethod
    def spoken_time_is_a_clock_time(cls, value: Any) -> Any:
        return _coerce_time(value)

    @model_validator(mode="after")
    def require_a_slot(self) -> "BookAppointmentArguments":
        if self.availability_token:
            return self
        if self.preferred_date and self.preferred_time is not None and (
            self.service_id or self.service_name
        ):
            return self
        raise ValueError(
            "availability_token is required, or else service_name with "
            "preferred_date and preferred_time"
        )


class VapiToolResult(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    result: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)


class VapiToolResponse(BaseModel):
    results: list[VapiToolResult]

