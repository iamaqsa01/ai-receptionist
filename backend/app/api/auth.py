import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import bearer_scheme, get_current_user
from app.core.rate_limit import login_rate_limiter, rate_limit, register_rate_limiter
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import (
    CurrentUserOut,
    LoginRequest,
    MembershipSummary,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit import record_audit_log

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, db: Session = Depends(get_db), _: None = Depends(rate_limit(register_rate_limiter))
) -> User:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit_log(db, action="user.registered", resource_type="user", actor_user_id=user.id, resource_id=user.id)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, db: Session = Depends(get_db), _: None = Depends(rate_limit(login_rate_limiter))
) -> TokenResponse:
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
    )

    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise invalid_credentials
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    token, jti, expires_at = create_access_token(user.id)

    db.add(
        AuthSession(
            id=uuid.UUID(jti),
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    record_audit_log(db, action="user.login", resource_type="user", actor_user_id=user.id, resource_id=user.id)

    return TokenResponse(access_token=token, expires_at=expires_at.isoformat())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    payload = decode_access_token(credentials.credentials)
    jti = payload["jti"]

    session = db.execute(select(AuthSession).where(AuthSession.id == uuid.UUID(jti))).scalar_one_or_none()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        record_audit_log(db, action="user.logout", resource_type="user", actor_user_id=current_user.id, resource_id=current_user.id)


@router.get("/me", response_model=CurrentUserOut)
def read_current_user(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CurrentUserOut:
    memberships = db.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == current_user.id)
    ).all()

    return CurrentUserOut(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_super_admin=current_user.is_super_admin,
        memberships=[
            MembershipSummary(
                workspace_id=ws.id,
                workspace_name=ws.name,
                role=member.role,
                is_onboarded=ws.is_onboarded,
            )
            for member, ws in memberships
        ],
    )
