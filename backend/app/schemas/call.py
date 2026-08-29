import uuid
from datetime import datetime

from pydantic import BaseModel


class CallOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    patient_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    direction: str
    from_number: str | None
    to_number: str | None
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CallTranscriptOut(BaseModel):
    id: uuid.UUID
    call_id: uuid.UUID
    sequence: int
    speaker: str
    content: str
    spoken_at: datetime | None

    model_config = {"from_attributes": True}
