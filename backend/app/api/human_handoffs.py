from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.human_handoff import HumanHandoff
from app.schemas.human_handoff import HumanHandoffOut

router = APIRouter(prefix="/workspaces/{workspace_id}/human-handoffs", tags=["human-handoffs"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.get("", response_model=list[HumanHandoffOut])
def list_human_handoffs(
    ctx: TenantContext = Depends(require_permission("human_handoffs:read")),
    db: Session = Depends(get_db),
) -> list[HumanHandoff]:
    return list(
        db.execute(
            select(HumanHandoff)
            .where(HumanHandoff.workspace_id == ctx.workspace_id)
            .order_by(HumanHandoff.created_at.desc())
        ).scalars()
    )
