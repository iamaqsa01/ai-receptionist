"""Phase 13 — GET /workspaces/{workspace_id}/analytics/summary."""

from tests.conftest import auth_headers, create_workspace, register_and_login


def test_analytics_summary_is_reachable_and_scoped(client):
    token = register_and_login(client, "analytics-api@example.com")
    ws_id = create_workspace(client, token, "API Analytics Clinic", "api-analytics-clinic")

    resp = client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workspace_id"] == ws_id
    assert body["total_calls"] == 0
    assert body["conversion_rate"] is None


def test_analytics_summary_requires_auth(client):
    ws_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary")
    assert resp.status_code == 401


def test_analytics_summary_rejects_non_members(client):
    owner_token = register_and_login(client, "analytics-owner@example.com")
    ws_id = create_workspace(client, owner_token, "Private Analytics Clinic", "private-analytics-clinic")

    outsider_token = register_and_login(client, "analytics-outsider@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary", headers=auth_headers(outsider_token))
    assert resp.status_code == 404  # tenant isolation: 404, not 403
