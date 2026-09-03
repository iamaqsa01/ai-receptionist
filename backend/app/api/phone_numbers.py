import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, require_permission
from app.database.session import get_db
from app.models.phone_number import PhoneNumber
from app.schemas.phone_number import PhoneNumberCreate, PhoneNumberOut
from app.services.audit import record_audit_log
from app.services.phone_numbers import normalize_e164

# Managing which phone numbers route to a workspace is clinic configuration,
# same tier as services/providers/settings: any member may read it, only
# Owner/Admin (settings:manage) may change it. No new role or permission.
router = APIRouter(
    prefix="/workspaces/{workspace_id}/phone-numbers",
    tags=["phone-numbers"],
    dependencies=[Depends(get_current_onboarded_tenant)],
)


@router.get("", response_model=list[PhoneNumberOut])
def list_phone_numbers(
    ctx: TenantContext = Depends(require_permission("settings:read")),
    db: Session = Depends(get_db),
) -> list[PhoneNumber]:
    return list(
        db.execute(
            select(PhoneNumber)
            .where(PhoneNumber.workspace_id == ctx.workspace_id)
            .order_by(PhoneNumber.created_at)
        ).scalars()
    )


@router.post("", response_model=PhoneNumberOut, status_code=status.HTTP_201_CREATED)
def add_phone_number(
    payload: PhoneNumberCreate,
    ctx: TenantContext = Depends(require_permission("settings:manage")),
    db: Session = Depends(get_db),
) -> PhoneNumber:
    normalized = normalize_e164(payload.number)
    if normalized is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid phone number in international format, e.g. +14155550100.",
        )

    # `number` is globally unique — a number routes to exactly one
    # workspace. Don't disclose which workspace already holds it.
    existing = db.execute(
        select(PhoneNumber).where(PhoneNumber.number == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That phone number is already assigned.",
        )

    phone_number = PhoneNumber(workspace_id=ctx.workspace_id, number=normalized)
    db.add(phone_number)
    db.commit()
    db.refresh(phone_number)
    record_audit_log(
        db,
        action="phone_number.added",
        resource_type="phone_number",
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        resource_id=phone_number.id,
    )
    return phone_number


@router.delete("/{phone_number_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_phone_number(
    phone_number_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("settings:manage")),
    db: Session = Depends(get_db),
) -> None:
    phone_number = db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_number_id,
            PhoneNumber.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found"
        )

    db.delete(phone_number)
    db.commit()
    record_audit_log(
        db,
        action="phone_number.removed",
        resource_type="phone_number",
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        resource_id=phone_number_id,
    )
