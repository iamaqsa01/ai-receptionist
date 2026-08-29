from enum import Enum


class WorkspaceRole(str, Enum):
    """Workspace-scoped roles, stored on WorkspaceMember.role.

    Super Admin is intentionally not here — it is a platform-wide flag on
    User (is_super_admin), not a per-workspace role.
    """

    OWNER = "owner"
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    ANALYST = "analyst"


ALL_WORKSPACE_ROLES = {role.value for role in WorkspaceRole}

SUPER_ADMIN = "super_admin"  # display-only pseudo-role for /auth/me, not stored on memberships
