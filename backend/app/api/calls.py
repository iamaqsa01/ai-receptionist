import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.call import Call
from app.models.call_transcript import CallTranscript
from app.schemas.call import CallOut, CallTranscriptOut

router = APIRouter(prefix="/workspaces/{workspace_id}/calls", tags=["calls"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.get("", response_model=list[CallOut])
def list_calls(
    ctx: TenantContext = Depends(require_permission("calls:read")),
    db: Session = Depends(get_db),
) -> list[Call]:
    return list(db.execute(select(Call).where(Call.workspace_id == ctx.workspace_id)).scalars())


@router.get("/{call_id}", response_model=CallOut)
def get_call(
    call_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("calls:read")),
    db: Session = Depends(get_db),
) -> Call:
    call = db.execute(
        select(Call).where(Call.id == call_id, Call.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    return call


@router.get("/{call_id}/transcripts", response_model=list[CallTranscriptOut])
def list_call_transcripts(
    call_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("transcripts:read")),
    db: Session = Depends(get_db),
) -> list[CallTranscript]:
    call = db.execute(
        select(Call).where(Call.id == call_id, Call.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    return list(
        db.execute(
            select(CallTranscript)
            .where(CallTranscript.call_id == call_id, CallTranscript.workspace_id == ctx.workspace_id)
            .order_by(CallTranscript.sequence)
        ).scalars()
    )
