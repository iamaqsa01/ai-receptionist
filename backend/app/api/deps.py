import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_context import bind_workspace_id
from app.core.rbac import role_allows
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized

    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti or not sub:
        raise unauthorized

    session = db.execute(select(AuthSession).where(AuthSession.id == uuid.UUID(jti))).scalar_one_or_none()
    if session is None or session.revoked_at is not None:
        raise unauthorized
    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise unauthorized

    user = db.execute(select(User).where(User.id == uuid.UUID(sub))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise unauthorized

    return user


@dataclass
class TenantContext:
    user: User
    workspace_id: uuid.UUID
    role: str  # "super_admin" or one of the WorkspaceRole values
    is_super_admin: bool


def get_tenant_context(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Iterator[TenantContext]:
    # Bound for the rest of this request so every log line emitted while
    # handling a workspace-scoped endpoint is correlated with its
    # workspace (see app.core.logging_context) — reset automatically once
    # the request finishes, same generator-dependency-teardown pattern as
    # get_db above.
    with bind_workspace_id(workspace_id):
        if current_user.is_super_admin:
            yield TenantContext(
                user=current_user, workspace_id=workspace_id, role="super_admin", is_super_admin=True
            )
            return

        membership = db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        ).scalar_one_or_none()

        if membership is None:
            # 404, not 403: don't reveal whether the workspace exists to a
            # caller who isn't a member of it.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        yield TenantContext(
            user=current_user, workspace_id=workspace_id, role=membership.role, is_super_admin=False
        )


def get_current_onboarded_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """A member of `{workspace_id}` whose workspace has completed onboarding.

    Server-side gate so a client can never reach a workspace's tenant data
    by skipping the mandatory clinic-setup flow (the frontend enforces the
    same thing, but that can be bypassed). Onboarding is a property of the
    WORKSPACE, not the user — being onboarded for workspace A does not grant
    access to a brand-new workspace B.

    Membership is resolved first (`get_tenant_context` → 404 for non-members,
    which does not reveal a workspace's onboarding state to outsiders); only
    then is the 403 raised for a workspace that has not finished setup.

    The onboarding endpoints themselves — POST /workspaces,
    GET/PATCH /workspaces/{id}, and GET/PUT /workspaces/{id}/clinic-settings
    — deliberately keep plain `require_permission` / `get_current_user` auth
    so the form can be submitted; completing it (PUT clinic-settings) flips
    `Workspace.is_onboarded`.
    """
    workspace = db.get(Workspace, ctx.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if not workspace.is_onboarded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This workspace has not completed onboarding. Finish clinic setup first.",
        )
    return ctx


# Continuity alias. Historically this gate was `get_current_onboarded_user`
# and checked a global `User.is_onboarded`. It now means: "the authenticated
# user, authorized for THIS workspace (`{workspace_id}` in the path), whose
# workspace has completed onboarding" — and it yields the TenantContext, not
# a bare User. Both names resolve to the same dependency.
get_current_onboarded_user = get_current_onboarded_tenant


def require_permission(permission: str):
    def dependency(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.is_super_admin:
            return ctx
        if not role_allows(ctx.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )
        return ctx

    return dependency
