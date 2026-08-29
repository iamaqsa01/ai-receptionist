import uuid

from pydantic import BaseModel, Field


class StartSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: str


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class SendMessageResponse(BaseModel):
    session_id: uuid.UUID
    reply: str
    language: str | None
    status: str
    intent: str | None
    missing_fields: list[str]


class ConversationHistoryTurn(BaseModel):
    role: str
    text: str
    language: str | None


class ConversationHistoryResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    language: str | None
    intent: str | None
    history: list[ConversationHistoryTurn]
