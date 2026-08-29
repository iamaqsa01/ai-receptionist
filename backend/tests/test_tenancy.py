import uuid

from tests.conftest import auth_headers, create_workspace, register_and_login


def test_workspace_creator_becomes_owner(client):
    token = register_and_login(client, "owner@example.com")
    ws_id = create_workspace(client, token, "Clinic A", "clinic-a")

    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    memberships = resp.json()["memberships"]
    assert len(memberships) == 1
    assert memberships[0]["workspace_id"] == ws_id
    assert memberships[0]["role"] == "owner"


def test_non_member_cannot_list_another_workspaces_patients(client):
    owner_token = register_and_login(client, "owner-a@example.com")
    ws_a = create_workspace(client, owner_token, "Clinic A", "clinic-a")
    client.post(
        f"/api/v1/workspaces/{ws_a}/patients",
        json={"first_name": "Pat", "last_name": "Ient"},
        headers=auth_headers(owner_token),
    )

    outsider_token = register_and_login(client, "outsider@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws_a}/patients", headers=auth_headers(outsider_token))
    assert resp.status_code == 404


def test_non_member_cannot_fetch_another_workspaces_patient_by_id(client):
    owner_token = register_and_login(client, "owner-b@example.com")
    ws_a = create_workspace(client, owner_token, "Clinic B", "clinic-b")
    patient_resp = client.post(
        f"/api/v1/workspaces/{ws_a}/patients",
        json={"first_name": "Pat", "last_name": "Ient"},
        headers=auth_headers(owner_token),
    )
    patient_id = patient_resp.json()["id"]

    outsider_token = register_and_login(client, "outsider-b@example.com")
    ws_b = create_workspace(client, outsider_token, "Clinic C", "clinic-c")

    # Outsider is a member of a *different* workspace, but tries to reach
    # workspace A's patient directly by ID via workspace A's URL.
    resp = client.get(
        f"/api/v1/workspaces/{ws_a}/patients/{patient_id}", headers=auth_headers(outsider_token)
    )
    assert resp.status_code == 404

    # Even scoping the *same* patient id under the outsider's own workspace
    # must not leak it (cross-tenant ID guessing).
    resp = client.get(
        f"/api/v1/workspaces/{ws_b}/patients/{patient_id}", headers=auth_headers(outsider_token)
    )
    assert resp.status_code == 404


def test_random_nonexistent_workspace_id_returns_404_not_500(client):
    token = register_and_login(client, "loner@example.com")
    fake_ws = uuid.uuid4()
    resp = client.get(f"/api/v1/workspaces/{fake_ws}/patients", headers=auth_headers(token))
    assert resp.status_code == 404


def test_leads_are_tenant_isolated(client):
    owner_a = register_and_login(client, "leadowner-a@example.com")
    ws_a = create_workspace(client, owner_a, "Clinic D", "clinic-d")
    client.post(
        f"/api/v1/workspaces/{ws_a}/leads", json={"name": "Lead A"}, headers=auth_headers(owner_a)
    )

    owner_b = register_and_login(client, "leadowner-b@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws_a}/leads", headers=auth_headers(owner_b))
    assert resp.status_code == 404


def test_appointment_cannot_reference_another_workspaces_patient(client):
    owner_a = register_and_login(client, "appt-owner-a@example.com")
    ws_a = create_workspace(client, owner_a, "Clinic E", "clinic-e")
    patient_resp = client.post(
        f"/api/v1/workspaces/{ws_a}/patients",
        json={"first_name": "Pat", "last_name": "Ient"},
        headers=auth_headers(owner_a),
    )
    patient_id = patient_resp.json()["id"]

    owner_b = register_and_login(client, "appt-owner-b@example.com")
    ws_b = create_workspace(client, owner_b, "Clinic F", "clinic-f")

    resp = client.post(
        f"/api/v1/workspaces/{ws_b}/appointments",
        json={
            "patient_id": patient_id,
            "start_time": "2026-01-01T10:00:00Z",
            "end_time": "2026-01-01T10:30:00Z",
        },
        headers=auth_headers(owner_b),
    )
    assert resp.status_code == 404


def test_analyst_can_read_but_not_write_patients(client):
    owner_token = register_and_login(client, "rbac-owner@example.com")
    ws_id = create_workspace(client, owner_token, "Clinic G", "clinic-g")

    analyst_token = register_and_login(client, "rbac-analyst@example.com")
    invite = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "rbac-analyst@example.com", "role": "analyst"},
        headers=auth_headers(owner_token),
    )
    assert invite.status_code == 201

    resp = client.get(f"/api/v1/workspaces/{ws_id}/patients", headers=auth_headers(analyst_token))
    assert resp.status_code == 200

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/patients",
        json={"first_name": "Pat", "last_name": "Ient"},
        headers=auth_headers(analyst_token),
    )
    assert resp.status_code == 403


def test_receptionist_can_write_patients_but_not_manage_settings(client):
    owner_token = register_and_login(client, "rbac-owner-2@example.com")
    ws_id = create_workspace(client, owner_token, "Clinic H", "clinic-h")

    reception_token = register_and_login(client, "rbac-reception@example.com")
    client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "rbac-reception@example.com", "role": "receptionist"},
        headers=auth_headers(owner_token),
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/patients",
        json={"first_name": "Pat", "last_name": "Ient"},
        headers=auth_headers(reception_token),
    )
    assert resp.status_code == 201

    resp = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "Hacked Name"},
        headers=auth_headers(reception_token),
    )
    assert resp.status_code == 403


def test_only_owner_or_admin_can_manage_members(client):
    owner_token = register_and_login(client, "rbac-owner-3@example.com")
    ws_id = create_workspace(client, owner_token, "Clinic I", "clinic-i")

    reception_token = register_and_login(client, "rbac-reception-3@example.com")
    client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "rbac-reception-3@example.com", "role": "receptionist"},
        headers=auth_headers(owner_token),
    )

    third_user_email = "rbac-third@example.com"
    register_and_login(client, third_user_email)

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": third_user_email, "role": "analyst"},
        headers=auth_headers(reception_token),
    )
    assert resp.status_code == 403


def test_super_admin_bypasses_membership_check(client, db_session):
    from app.models.user import User

    owner_token = register_and_login(client, "so-owned@example.com")
    ws_id = create_workspace(client, owner_token, "Clinic J", "clinic-j")
    client.post(
        f"/api/v1/workspaces/{ws_id}/patients",
        json={"first_name": "Pat", "last_name": "Ient"},
        headers=auth_headers(owner_token),
    )

    super_admin_token = register_and_login(client, "superadmin@example.com")
    user = db_session.query(User).filter_by(email="superadmin@example.com").one()
    user.is_super_admin = True
    db_session.add(user)
    db_session.commit()

    resp = client.get(f"/api/v1/workspaces/{ws_id}/patients", headers=auth_headers(super_admin_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_calls_and_transcripts_are_tenant_isolated(client, db_session):
    from app.models.call import Call
    from app.models.call_transcript import CallTranscript

    owner_a = register_and_login(client, "call-owner-a@example.com")
    ws_a = create_workspace(client, owner_a, "Clinic K", "clinic-k")

    call = Call(workspace_id=uuid.UUID(ws_a), direction="inbound", status="completed")
    db_session.add(call)
    db_session.flush()
    db_session.add(
        CallTranscript(
            workspace_id=uuid.UUID(ws_a), call_id=call.id, sequence=1, speaker="caller", content="Hello"
        )
    )
    db_session.commit()

    owner_b = register_and_login(client, "call-owner-b@example.com")
    ws_b = create_workspace(client, owner_b, "Clinic L", "clinic-l")

    resp = client.get(f"/api/v1/workspaces/{ws_b}/calls/{call.id}", headers=auth_headers(owner_b))
    assert resp.status_code == 404

    resp = client.get(
        f"/api/v1/workspaces/{ws_b}/calls/{call.id}/transcripts", headers=auth_headers(owner_b)
    )
    assert resp.status_code == 404

    resp = client.get(f"/api/v1/workspaces/{ws_a}/calls/{call.id}", headers=auth_headers(owner_a))
    assert resp.status_code == 200
