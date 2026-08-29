from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.schemas.analytics import AnalyticsSummaryOut
from app.services.analytics import compute_analytics_summary

router = APIRouter(prefix="/workspaces/{workspace_id}/analytics", tags=["analytics"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.get("/summary", response_model=AnalyticsSummaryOut)
def get_analytics_summary(
    since: datetime | None = None,
    until: datetime | None = None,
    ctx: TenantContext = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryOut:
    summary = compute_analytics_summary(db, ctx.workspace_id, since=since, until=until)
    return AnalyticsSummaryOut(**summary.__dict__)
