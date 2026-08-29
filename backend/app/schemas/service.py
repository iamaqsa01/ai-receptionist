import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int = Field(default=30, ge=5, le=480)
    price_cents: int | None = Field(default=None, ge=0)
    is_active: bool = True


class ServiceOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    duration_minutes: int
    price_cents: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
