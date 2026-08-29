from app.core.roles import WorkspaceRole

OWNER = WorkspaceRole.OWNER.value
ADMIN = WorkspaceRole.ADMIN.value
RECEPTIONIST = WorkspaceRole.RECEPTIONIST.value
ANALYST = WorkspaceRole.ANALYST.value

# Permission -> set of workspace roles allowed to perform it.
# Super Admin (User.is_super_admin) always bypasses this map entirely.
PERMISSIONS: dict[str, set[str]] = {
    "members:manage": {OWNER, ADMIN},
    "settings:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "settings:manage": {OWNER, ADMIN},
    "patients:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "patients:write": {OWNER, ADMIN, RECEPTIONIST},
    "leads:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "leads:write": {OWNER, ADMIN, RECEPTIONIST},
    "appointments:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "appointments:write": {OWNER, ADMIN, RECEPTIONIST},
    # Clinic configuration (what services are offered, which providers
    # exist) — every caller booking depends on these being populated, so
    # read is broad (same as settings:read) but write is Owner/Admin-only,
    # same tier as settings:manage.
    "services:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "services:write": {OWNER, ADMIN},
    "providers:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "providers:write": {OWNER, ADMIN},
    "calls:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "transcripts:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "notifications:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "human_handoffs:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    "analytics:read": {OWNER, ADMIN, RECEPTIONIST, ANALYST},
    # Driving/testing the AI Receptionist from the staff dashboard (e.g. a
    # "try it" demo session) — not the caller-facing path, which will be
    # unauthenticated and reached via the telephony webhook in a later phase.
    "ai:interact": {OWNER, ADMIN, RECEPTIONIST},
}


def role_allows(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())
