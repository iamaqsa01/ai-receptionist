import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    timezone: str = Field(default="UTC", max_length=64)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    is_onboarded: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberInvite(BaseModel):
    email: EmailStr
    role: str
    # Optional. Maps onto the global ``User.phone`` column (String(32)). Only
    # applied when that user has no phone on file yet — an invite never
    # overwrites a number the user already set. Same "preserve what's
    # already configured" rule the workspace timezone field follows.
    phone_number: str | None = Field(default=None, max_length=32)


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str

    model_config = {"from_attributes": True}
