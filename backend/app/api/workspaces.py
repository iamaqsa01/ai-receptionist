import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, get_current_onboarded_tenant, get_current_user, require_permission
from app.core.roles import ALL_WORKSPACE_ROLES, WorkspaceRole
from app.database.session import get_db
from app.models.ai_agent import AIAgent
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.clinic_settings import BusinessType, ClinicSettingsOut, ClinicSettingsUpdate
from app.schemas.workspace import (
    MemberInvite,
    MemberOut,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services.audit import record_audit_log
from app.services.clinic_settings import sync_booking_configuration

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Workspace:
    existing = db.execute(select(Workspace).where(Workspace.slug == payload.slug)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")

    workspace = Workspace(name=payload.name, slug=payload.slug, timezone=payload.timezone)
    db.add(workspace)
    db.flush()

    # Creator becomes Owner of their new workspace.
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=current_user.id, role=WorkspaceRole.OWNER.value))
    db.commit()
    db.refresh(workspace)
    record_audit_log(
        db, action="workspace.created", resource_type="workspace",
        workspace_id=workspace.id, actor_user_id=current_user.id, resource_id=workspace.id,
    )
    return workspace


@router.get("", response_model=list[WorkspaceOut])
def list_my_workspaces(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Workspace]:
    return list(
        db.execute(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == current_user.id)
        ).scalars()
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("settings:read")),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    ctx: TenantContext = Depends(require_permission("settings:manage")),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if payload.name is not None:
        workspace.name = payload.name
    if payload.timezone is not None:
        workspace.timezone = payload.timezone

    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    record_audit_log(
        db, action="workspace.updated", resource_type="workspace",
        workspace_id=workspace.id, actor_user_id=ctx.user.id, resource_id=workspace.id,
        extra_data=payload.model_dump(exclude_unset=True),
    )
    return workspace


def _active_agent(db: Session, workspace_id: uuid.UUID) -> AIAgent | None:
    """The workspace's AI Receptionist config row. Prefers the active one
    (the same row load_workspace_profile / generate_system_prompt read),
    falling back to the earliest-created agent."""
    return (
        db.execute(
            select(AIAgent)
            .where(AIAgent.workspace_id == workspace_id)
            .order_by(AIAgent.is_active.desc(), AIAgent.created_at)
        )
        .scalars()
        .first()
    )


@router.get("/{workspace_id}/clinic-settings", response_model=ClinicSettingsOut)
def get_clinic_settings(
    workspace_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("settings:read")),
    db: Session = Depends(get_db),
) -> ClinicSettingsOut:
    if db.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    agent = _active_agent(db, workspace_id)
    stored = (agent.config or {}).get("clinic_settings", {}) if agent else {}
    # Round-trip through the schema so callers always get a fully-populated,
    # validated object even before anything has been saved.
    settings_model = ClinicSettingsUpdate.model_validate(stored)
    return ClinicSettingsOut(workspace_id=workspace_id, **settings_model.model_dump())


@router.put("/{workspace_id}/clinic-settings", response_model=ClinicSettingsOut)
def update_clinic_settings(
    workspace_id: uuid.UUID,
    payload: ClinicSettingsUpdate,
    ctx: TenantContext = Depends(require_permission("settings:manage")),
    db: Session = Depends(get_db),
) -> ClinicSettingsOut:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # A clinic workspace is only ready for real booking once every normalized
    # scheduling resource can be created. Existing/onboarded workspaces may
    # still save partial settings for backwards compatibility, but the first
    # onboarding completion must be operationally complete.
    #
    # This requirement is clinic-specific: it applies when the workspace is a
    # Clinic, and — for backwards compatibility — when no business_type was
    # supplied at all (every payload predating dynamic onboarding). Software
    # Agency / Real Estate / Other workspaces onboard without doctors,
    # services or seven-day clinic hours.
    clinic_like = payload.business_type in (None, BusinessType.CLINIC)
    if not workspace.is_onboarded and clinic_like:
        if not payload.doctors:
            raise HTTPException(status_code=422, detail="At least one doctor is required")
        if not payload.services:
            raise HTTPException(status_code=422, detail="At least one service is required")
        if {hours.day_of_week for hours in payload.business_hours} != set(range(7)):
            raise HTTPException(
                status_code=422,
                detail="Business hours must include all seven weekdays",
            )

    agent = _active_agent(db, workspace_id)
    if agent is None:
        # First time the dashboard saves settings for this workspace —
        # create the AI Receptionist config shell it hangs off of.
        agent = AIAgent(workspace_id=workspace_id, name="AI Receptionist", is_active=True, config={})
        db.add(agent)
        db.flush()

    # Reassign the whole dict (the JSON column isn't a MutableDict) and keep
    # every other config key (instructions, supported_languages, ...) intact.
    agent.config = {**(agent.config or {}), "clinic_settings": payload.model_dump(mode="json")}
    db.add(agent)

    # The JSON settings drive the clinic knowledge base, while these
    # existing normalized tables drive real availability and booking. Keep
    # both representations synchronized in this same transaction so a
    # workspace can never be marked onboarded with only half its scheduling
    # configuration saved.
    sync_booking_configuration(db, workspace_id, payload)

    # Completing clinic settings is what marks THIS WORKSPACE onboarded — the
    # frontend routes to /setup for this workspace until it flips, and
    # get_current_onboarded_tenant gates its data routes on it.
    if not workspace.is_onboarded:
        workspace.is_onboarded = True
        db.add(workspace)

    db.commit()
    db.refresh(agent)

    record_audit_log(
        db, action="workspace.clinic_settings_updated", resource_type="ai_agent",
        workspace_id=workspace_id, actor_user_id=ctx.user.id, resource_id=agent.id,
    )
    return ClinicSettingsOut(workspace_id=workspace_id, **payload.model_dump())


@router.get(
    "/{workspace_id}/members",
    response_model=list[MemberOut],
    dependencies=[Depends(get_current_onboarded_tenant)],
)
def list_members(
    workspace_id: uuid.UUID,
    ctx: TenantContext = Depends(require_permission("settings:read")),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    ).all()
    return [
        MemberOut(id=member.id, user_id=user.id, email=user.email, full_name=user.full_name, role=member.role)
        for member, user in rows
    ]


@router.post(
    "/{workspace_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_onboarded_tenant)],
)
def add_member(
    workspace_id: uuid.UUID,
    payload: MemberInvite,
    ctx: TenantContext = Depends(require_permission("members:manage")),
    db: Session = Depends(get_db),
) -> MemberOut:
    if payload.role not in ALL_WORKSPACE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {sorted(ALL_WORKSPACE_ROLES)}",
        )

    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No user with that email")

    existing = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    member = WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=payload.role)
    db.add(member)

    # Attach the invited phone number to the user's global profile, but
    # never overwrite one they already have on file.
    phone_applied = False
    if payload.phone_number and not user.phone:
        user.phone = payload.phone_number.strip()
        db.add(user)
        phone_applied = True

    db.commit()
    db.refresh(member)
    record_audit_log(
        db, action="workspace.member_added", resource_type="workspace_member",
        workspace_id=workspace_id, actor_user_id=ctx.user.id, resource_id=member.id,
        extra_data={
            "invited_email": payload.email,
            "role": payload.role,
            "phone_applied": phone_applied,
        },
    )
    return MemberOut(id=member.id, user_id=user.id, email=user.email, full_name=user.full_name, role=member.role)
