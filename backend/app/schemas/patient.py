import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    date_of_birth: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PatientOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    date_of_birth: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
