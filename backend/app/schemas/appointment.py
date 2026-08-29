import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    start_time: datetime
    end_time: datetime
    notes: str | None = Field(default=None, max_length=4000)

    # `status` is deliberately not a caller-settable field here: a newly
    # created appointment always starts "scheduled" (set server-side in
    # app.api.appointments.create_appointment) — letting a client set it
    # directly on create served no legitimate purpose and let a caller
    # write any string into a column other code (analytics, the AI
    # Receptionist's own booking flow) assumes is one of a small known set.

    @model_validator(mode="after")
    def _end_after_start(self) -> "AppointmentCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AppointmentOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    patient_id: uuid.UUID
    provider_id: uuid.UUID | None
    service_id: uuid.UUID | None
    call_id: uuid.UUID | None
    start_time: datetime
    end_time: datetime
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
