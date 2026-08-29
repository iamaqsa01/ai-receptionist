import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.receptionist_service import ReceptionistService, UnknownConversationSessionError
from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.schemas.ai import (
    ConversationHistoryResponse,
    ConversationHistoryTurn,
    SendMessageRequest,
    SendMessageResponse,
    StartSessionResponse,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/ai/sessions", tags=["ai"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.post("", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
def start_session(
    ctx: TenantContext = Depends(require_permission("ai:interact")),
    db: Session = Depends(get_db),
) -> StartSessionResponse:
    service = ReceptionistService(db=db)
    state = service.start_session(ctx.workspace_id)
    return StartSessionResponse(session_id=state.session_id, status=state.status.value)


@router.post("/{session_id}/messages", response_model=SendMessageResponse)
def send_message(
    session_id: uuid.UUID,
    payload: SendMessageRequest,
    ctx: TenantContext = Depends(require_permission("ai:interact")),
    db: Session = Depends(get_db),
) -> SendMessageResponse:
    service = ReceptionistService(db=db)
    try:
        result = service.handle_message(ctx.workspace_id, session_id, payload.message)
    except UnknownConversationSessionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    state = result.state
    return SendMessageResponse(
        session_id=state.session_id,
        reply=result.reply,
        language=state.language,
        status=state.status.value,
        intent=state.intent.value if state.intent else None,
        missing_fields=state.missing_fields,
    )


@router.get("/{session_id}", response_model=ConversationHistoryResponse)
def get_session(
    session_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("ai:interact")),
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
    service = ReceptionistService(db=db)
    state = service.store.get(session_id)
    if state is None or state.workspace_id != ctx.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return ConversationHistoryResponse(
        session_id=state.session_id,
        status=state.status.value,
        language=state.language,
        intent=state.intent.value if state.intent else None,
        history=[
            ConversationHistoryTurn(role=t.role, text=t.text, language=t.language) for t in state.history
        ],
    )
