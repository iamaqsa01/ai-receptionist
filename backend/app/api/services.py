import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceOut
from app.services.audit import record_audit_log

router = APIRouter(prefix="/workspaces/{workspace_id}/services", tags=["services"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    ctx: TenantContext = Depends(require_permission("services:write")),
    db: Session = Depends(get_db),
) -> Service:
    service = Service(workspace_id=ctx.workspace_id, **payload.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    record_audit_log(
        db, action="service.created", resource_type="service",
        workspace_id=ctx.workspace_id, actor_user_id=ctx.user.id, resource_id=service.id,
    )
    return service


@router.get("", response_model=list[ServiceOut])
def list_services(
    ctx: TenantContext = Depends(require_permission("services:read")),
    db: Session = Depends(get_db),
) -> list[Service]:
    return list(db.execute(select(Service).where(Service.workspace_id == ctx.workspace_id)).scalars())


@router.get("/{service_id}", response_model=ServiceOut)
def get_service(
    service_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("services:read")),
    db: Session = Depends(get_db),
) -> Service:
    service = db.execute(
        select(Service).where(Service.id == service_id, Service.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service
