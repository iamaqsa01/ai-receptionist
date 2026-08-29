import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.provider import Provider
from app.schemas.provider import ProviderCreate, ProviderOut
from app.services.audit import record_audit_log

router = APIRouter(prefix="/workspaces/{workspace_id}/providers", tags=["providers"], dependencies=[Depends(get_current_onboarded_tenant)])


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    ctx: TenantContext = Depends(require_permission("providers:write")),
    db: Session = Depends(get_db),
) -> Provider:
    provider = Provider(workspace_id=ctx.workspace_id, **payload.model_dump())
    db.add(provider)
    db.commit()
    db.refresh(provider)
    record_audit_log(
        db, action="provider.created", resource_type="provider",
        workspace_id=ctx.workspace_id, actor_user_id=ctx.user.id, resource_id=provider.id,
    )
    return provider


@router.get("", response_model=list[ProviderOut])
def list_providers(
    ctx: TenantContext = Depends(require_permission("providers:read")),
    db: Session = Depends(get_db),
) -> list[Provider]:
    return list(db.execute(select(Provider).where(Provider.workspace_id == ctx.workspace_id)).scalars())


@router.get("/{provider_id}", response_model=ProviderOut)
def get_provider(
    provider_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("providers:read")),
    db: Session = Depends(get_db),
) -> Provider:
    provider = db.execute(
        select(Provider).where(Provider.id == provider_id, Provider.workspace_id == ctx.workspace_id)
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider
