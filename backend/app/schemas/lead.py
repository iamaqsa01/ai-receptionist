import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

LeadStatus = Literal["new", "qualifying", "converted", "lost"]


class LeadCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=64)
    status: LeadStatus = "new"
    notes: str | None = Field(default=None, max_length=4000)


class LeadOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str | None
    email: str | None
    phone: str | None
    source: str | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
