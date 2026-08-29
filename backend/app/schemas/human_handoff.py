import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HumanHandoffOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    call_id: uuid.UUID | None
    conversation_session_id: uuid.UUID | None
    trigger: str
    reason: str
    conversation_context: list[Any]
    call_state: dict[str, Any]
    status: str
    transfer_target: str | None
    transfer_detail: str | None
    transferred_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
