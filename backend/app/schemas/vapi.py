from datetime import date, time
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class VapiCall(BaseModel):
    id: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(extra="ignore")


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
    message: VapiToolMessage
    call: VapiCall | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def require_tool_calls_message(self) -> "VapiToolRequest":
        if self.message.type != "tool-calls":
            raise ValueError("message.type must be 'tool-calls'")
        return self

    @property
    def call_id(self) -> str | None:
        call = self.call or self.message.call
        return call.id if call else None


class CheckAvailabilityArguments(BaseModel):
    service_id: uuid.UUID | None = None
    service_name: str | None = Field(default=None, min_length=1, max_length=255)
    provider_id: uuid.UUID | None = None
    provider_name: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_date: date
    preferred_time: time | None = None
    max_slots: int = Field(default=5, ge=1, le=10)

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


class VapiToolResult(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    result: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)


class VapiToolResponse(BaseModel):
    results: list[VapiToolResult]

