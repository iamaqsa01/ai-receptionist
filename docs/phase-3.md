# Phase 3 — Authentication, RBAC & Multi-Tenancy

## Scope

- Login, logout, secure password hashing (bcrypt), and a server-tracked JWT session system.
- Workspace creation and membership.
- RBAC across five roles: **Super Admin**, **Owner**, **Admin**, **Receptionist**, **Analyst**.
- Tenant access validation so a workspace can only ever see its own patients, leads, calls,
  appointments, transcripts, and settings.
- No AI or telephony logic.

## Roles

- **Super Admin** — platform-wide. Stored as `User.is_super_admin`, *not* a workspace role,
  since it isn't scoped to any single tenant. Bypasses membership/role checks entirely.
- **Owner**, **Admin**, **Receptionist**, **Analyst** — workspace-scoped, stored on
  `WorkspaceMember.role` (`app/core/roles.py: WorkspaceRole`). The clinic front-desk role is
  named exactly `Receptionist` per the spec, stored as `"receptionist"`.

Permission matrix (`app/core/rbac.py`):

| Permission | Owner | Admin | Receptionist | Analyst |
|---|---|---|---|---|
| members:manage | ✓ | ✓ | | |
| settings:manage | ✓ | ✓ | | |
| settings:read | ✓ | ✓ | ✓ | ✓ |
| patients/leads/appointments: write | ✓ | ✓ | ✓ | |
| patients/leads/appointments/calls/transcripts: read | ✓ | ✓ | ✓ | ✓ |

## Authentication

- Passwords hashed with `bcrypt` (`app/core/security.py`), never stored or returned in plaintext.
- Login issues a JWT (`HS256`, `SECRET_KEY` from env) whose `jti` is also the primary key of a
  new row in `auth_sessions`. `get_current_user` (`app/api/deps.py`) decodes the token *and*
  checks that session row isn't revoked/expired — so a stolen-but-logged-out token is rejected,
  which a purely stateless JWT scheme can't do.
- Logout sets `auth_sessions.revoked_at`, immediately invalidating that token.
- `SECRET_KEY` has a dev-only fallback in `Settings` so the app boots without configuration
  locally; `.env.example` documents that real deployments must override it.

## Multi-tenancy & tenant access validation

- Every workspace-scoped route is nested under `/api/v1/workspaces/{workspace_id}/...`.
- `get_tenant_context` (`app/api/deps.py`) resolves the caller's `WorkspaceMember` row for that
  specific `workspace_id`. No membership → `404` (not `403`, so an unauthorized caller can't use
  the status code to confirm a workspace exists). Super Admins skip this check.
- Every resource query additionally filters by `workspace_id` at the SQL level (e.g.
  `select(Patient).where(Patient.id == patient_id, Patient.workspace_id == ctx.workspace_id)`),
  so even a valid record ID from another tenant, reached through *your own* workspace's URL,
  returns `404` instead of the record.
- Cross-tenant object references are also blocked one level deeper: creating an appointment
  validates that the referenced `patient_id` belongs to the same workspace before allowing the
  link (`app/api/appointments.py`).

## Database compatibility change (carried from Phase 2)

Phase 2's models used PostgreSQL-only `UUID`/`JSONB` types directly, which meant they could only
ever be exercised against a real PostgreSQL server — and testing "cross-tenant access
prevention" properly requires actually running queries, not just inspecting schema. Since no
PostgreSQL/Docker was available in this environment (also true in Phase 2), a portable `GUID`
`TypeDecorator` and `JSON().with_variant(JSONB, "postgresql")` were added
(`app/database/types.py`) and swapped into every model. On PostgreSQL these render as native
`UUID`/`JSONB`, unchanged from Phase 2's behavior (verified below); on SQLite they fall back to
`CHAR(36)`/`JSON`, which is what makes the test suite able to run real INSERT/SELECT queries
against an in-memory database. The initial Alembic migration was regenerated to match (it had
never been applied to a real database, so this is a clean replacement, not an added migration).

## New tables

- `auth_sessions` — one row per issued token (`user_id`, `expires_at`, `revoked_at`), enabling
  real logout instead of a client-side no-op.
- `users` gained `hashed_password` and `is_super_admin`.
- `workspace_members.role` default changed from the placeholder `"member"` to `"receptionist"`.

## Testing

33 tests total, run against a real SQLite database created fresh per test
(`tests/conftest.py`, `StaticPool` in-memory engine + `Base.metadata.create_all`), with FastAPI's
`get_db` dependency overridden — so these exercise real HTTP requests through real password
hashing, JWT issuance/validation, and SQL queries, not mocks:

- `tests/test_auth.py` (10 tests): registration hashes passwords and never returns them,
  duplicate email rejected, login success/failure, protected routes reject missing/invalid
  tokens, `/me` returns memberships, logout revokes the token (subsequent use → 401), double
  logout is safe.
- `tests/test_tenancy.py` (12 tests) — the cross-tenant prevention suite:
  - Non-member gets `404` listing another workspace's patients.
  - Non-member gets `404` fetching another workspace's patient by ID directly, **and** gets `404`
    trying to reach that same ID through their *own* workspace's URL (ID-guessing across
    tenants).
  - A random, nonexistent `workspace_id` returns `404`, not a `500`.
  - Leads are tenant-isolated the same way.
  - Creating an appointment that references another workspace's patient is rejected (`404`).
  - RBAC: Analyst can read patients but not create one (`403`); Receptionist can create patients
    but not change workspace settings (`403`); only Owner/Admin can add members (`403` for
    Receptionist).
  - Super Admin bypasses membership checks and can read any workspace's data.
  - Calls and their transcripts (seeded directly via the ORM, since call creation is out of scope
    until the telephony phase) are tenant-isolated the same way as patients.
- `tests/test_database.py` updated for the new `auth_sessions` table (structural checks,
  unchanged approach from Phase 2).
- `alembic upgrade head --sql` against a `postgresql+psycopg2://` URL still exits 0 and renders
  correct `UUID`/`JSONB` DDL for every table including the new `auth_sessions`, confirming the
  GUID/JSON portability change didn't change PostgreSQL-side behavior.

**Not yet verified**: running against a live PostgreSQL server. Same caveat as Phase 2 — do this
before relying on it in a real environment:

```bash
alembic upgrade head
```

## Out of scope (unchanged)

AI engine, telephony integration. Appointment/notification *business logic* beyond
create/list/get is still future work — this phase only proves the auth/RBAC/tenancy pattern
across the required resource types.
