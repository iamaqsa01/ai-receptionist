import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationMessageOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    appointment_id: uuid.UUID | None
    channel: str
    event_type: str
    audience: str
    recipient: str
    provider: str
    provider_message_id: str | None
    status: str
    failure_reason: str | None
    subject: str | None
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
