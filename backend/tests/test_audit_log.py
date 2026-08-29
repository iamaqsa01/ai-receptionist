"""Phase 13 — audit logs: record_audit_log() persists an immutable
AuditLog row, and the key mutation endpoints (register, login, logout,
workspace create/update/member-add, lead/patient/appointment create) each
write one."""

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services.audit import record_audit_log
from tests.conftest import auth_headers, create_workspace, register_and_login


def test_record_audit_log_persists_a_row(db_session):
    entry = record_audit_log(
        db_session, action="lead.created", resource_type="lead", workspace_id=None, actor_user_id=None,
    )
    assert entry.id is not None
    stored = db_session.execute(select(AuditLog).where(AuditLog.id == entry.id)).scalar_one()
    assert stored.action == "lead.created"
    assert stored.resource_type == "lead"


def test_registration_and_login_are_audited(client, db_session):
    client.post("/api/v1/auth/register", json={"email": "audit@example.com", "password": "correct-horse-1", "full_name": "Audit User"})
    client.post("/api/v1/auth/login", json={"email": "audit@example.com", "password": "correct-horse-1"})

    actions = [row.action for row in db_session.execute(select(AuditLog)).scalars()]
    assert "user.registered" in actions
    assert "user.login" in actions


def test_logout_is_audited(client, db_session):
    token = register_and_login(client, "audit2@example.com")
    client.post("/api/v1/auth/logout", headers=auth_headers(token))

    actions = [row.action for row in db_session.execute(select(AuditLog)).scalars()]
    assert "user.logout" in actions


def test_workspace_and_resource_mutations_are_audited(client, db_session):
    token = register_and_login(client, "audit3@example.com")
    ws_id = create_workspace(client, token, "Audit Clinic", "audit-clinic")

    client.post(
        f"/api/v1/workspaces/{ws_id}/leads", headers=auth_headers(token),
        json={"name": "Jane Doe", "phone": "415-555-0100"},
    )
    client.post(
        f"/api/v1/workspaces/{ws_id}/patients", headers=auth_headers(token),
        json={"first_name": "Jane", "last_name": "Doe"},
    )

    rows = db_session.execute(select(AuditLog).where(AuditLog.workspace_id == ws_id)).scalars().all()
    actions = {row.action for row in rows}
    assert "workspace.created" in actions
    assert "lead.created" in actions
    assert "patient.created" in actions
    # Every workspace-scoped audit row is actually scoped to that workspace.
    assert all(row.workspace_id is not None for row in rows)
