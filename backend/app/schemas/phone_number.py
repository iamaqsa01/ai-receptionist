import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PhoneNumberCreate(BaseModel):
    # Accepts any string the clinic types; the endpoint normalises it to
    # E.164 and rejects it with 422 if that fails. Must include a country
    # code (leading "+").
    number: str = Field(min_length=3, max_length=32)


class PhoneNumberOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    number: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
