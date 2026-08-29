import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # bcrypt (app.core.security.hash_password) only ever looks at the first
    # 72 bytes of a password and silently ignores the rest — capping the
    # accepted length here at bcrypt's own limit means what a user typed is
    # what actually gets checked, rather than two different long passwords
    # sharing a 72-byte prefix silently hashing identically.
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    # Bounded for the same reason as RegisterRequest.password, plus this
    # endpoint is unauthenticated — an unbounded field is an easy way to
    # make the server do more work (encode/compare a huge string) per
    # request than necessary before rate limiting even kicks in.
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str


class MembershipSummary(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    role: str
    # Per-workspace onboarding state (Workspace.is_onboarded). Onboarding is
    # NOT a user-level flag any more — the frontend guard reads this for the
    # active workspace.
    is_onboarded: bool = False

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    is_super_admin: bool

    model_config = {"from_attributes": True}


class CurrentUserOut(UserOut):
    memberships: list[MembershipSummary] = []
