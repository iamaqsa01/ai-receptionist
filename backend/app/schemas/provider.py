import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    is_active: bool = True


class ProviderOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    title: str | None
    email: str | None
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
