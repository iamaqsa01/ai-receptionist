import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadOut
from app.services.audit import record_audit_log

router = APIRouter(prefix="/workspaces/{workspace_id}/leads", tags=["leads"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    ctx: TenantContext = Depends(require_permission("leads:write")),
    db: Session = Depends(get_db),
) -> Lead:
    lead = Lead(workspace_id=ctx.workspace_id, **payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    record_audit_log(
        db, action="lead.created", resource_type="lead",
        workspace_id=ctx.workspace_id, actor_user_id=ctx.user.id, resource_id=lead.id,
    )
    return lead


@router.get("", response_model=list[LeadOut])
def list_leads(
    ctx: TenantContext = Depends(require_permission("leads:read")),
    db: Session = Depends(get_db),
) -> list[Lead]:
    return list(db.execute(select(Lead).where(Lead.workspace_id == ctx.workspace_id)).scalars())


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("leads:read")),
    db: Session = Depends(get_db),
) -> Lead:
    lead = db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead
