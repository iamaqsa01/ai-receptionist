from tests.conftest import auth_headers, create_workspace, register_and_login


def test_ai_session_flow_via_api(client):
    token = register_and_login(client, "ai-owner@example.com")
    ws_id = create_workspace(client, token, "Clinic AI", "clinic-ai")

    resp = client.post(f"/api/v1/workspaces/{ws_id}/ai/sessions", headers=auth_headers(token))
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/ai/sessions/{session_id}/messages",
        json={"message": "Hi there"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"]
    assert body["language"] == "en"

    resp = client.get(f"/api/v1/workspaces/{ws_id}/ai/sessions/{session_id}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()["history"]) == 2  # caller turn + assistant turn


def test_ai_session_is_tenant_isolated(client):
    owner_a = register_and_login(client, "ai-owner-a@example.com")
    ws_a = create_workspace(client, owner_a, "Clinic AI A", "clinic-ai-a")
    resp = client.post(f"/api/v1/workspaces/{ws_a}/ai/sessions", headers=auth_headers(owner_a))
    session_id = resp.json()["session_id"]

    owner_b = register_and_login(client, "ai-owner-b@example.com")
    ws_b = create_workspace(client, owner_b, "Clinic AI B", "clinic-ai-b")

    resp = client.post(
        f"/api/v1/workspaces/{ws_b}/ai/sessions/{session_id}/messages",
        json={"message": "Hi"},
        headers=auth_headers(owner_b),
    )
    assert resp.status_code == 404


def test_analyst_cannot_interact_with_ai_sessions(client):
    owner_token = register_and_login(client, "ai-rbac-owner@example.com")
    ws_id = create_workspace(client, owner_token, "Clinic AI RBAC", "clinic-ai-rbac")

    analyst_token = register_and_login(client, "ai-rbac-analyst@example.com")
    client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "ai-rbac-analyst@example.com", "role": "analyst"},
        headers=auth_headers(owner_token),
    )

    resp = client.post(f"/api/v1/workspaces/{ws_id}/ai/sessions", headers=auth_headers(analyst_token))
    assert resp.status_code == 403
