"""Phase 17 — final audit finding: there was no way to create a Service or
Provider through the API at all, only via direct DB access in test
fixtures. Since a workspace with zero services can never have a caller
successfully book an appointment (extract_service/validate_service always
fail against an empty known_services list — see
app/ai/nlu/entities.py:extract_service), this made the AI Receptionist's
core booking flow unusable for any real, newly-signed-up clinic. Fixed
with a Service/Provider CRUD API mirroring the existing Lead/Patient
pattern exactly."""

from tests.conftest import auth_headers, create_workspace, register_and_login


def test_create_and_list_services(client):
    token = register_and_login(client, "svc-owner@example.com")
    ws_id = create_workspace(client, token, "Service Clinic", "service-clinic")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(token),
        json={"name": "Cleaning", "duration_minutes": 30},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Cleaning"
    assert body["is_active"] is True
    assert body["workspace_id"] == ws_id

    list_resp = client.get(f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = client.get(f"/api/v1/workspaces/{ws_id}/services/{body['id']}", headers=auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Cleaning"


def test_create_and_list_providers(client):
    token = register_and_login(client, "prov-owner@example.com")
    ws_id = create_workspace(client, token, "Provider Clinic", "provider-clinic")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/providers", headers=auth_headers(token),
        json={"name": "Dr. Okafor", "title": "General Dentist"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Dr. Okafor"

    list_resp = client.get(f"/api/v1/workspaces/{ws_id}/providers", headers=auth_headers(token))
    assert len(list_resp.json()) == 1


def test_services_and_providers_are_tenant_isolated(client):
    owner_token = register_and_login(client, "svc-tenant-owner@example.com")
    ws_id = create_workspace(client, owner_token, "Private Svc Clinic", "private-svc-clinic")
    client.post(
        f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(owner_token), json={"name": "Cleaning"}
    )

    outsider_token = register_and_login(client, "svc-tenant-outsider@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(outsider_token))
    assert resp.status_code == 404  # tenant isolation: 404, not 403 or an empty list


def test_receptionist_cannot_create_services_or_providers(client):
    """services:write / providers:write is Owner/Admin only, same tier as
    settings:manage — a Receptionist can read the clinic's configured
    services/providers but not change what the clinic offers."""
    owner_token = register_and_login(client, "svc-rbac-owner@example.com")
    ws_id = create_workspace(client, owner_token, "RBAC Svc Clinic", "rbac-svc-clinic")

    receptionist_email = "svc-rbac-receptionist@example.com"
    receptionist_token = register_and_login(client, receptionist_email)
    client.post(
        f"/api/v1/workspaces/{ws_id}/members", headers=auth_headers(owner_token),
        json={"email": receptionist_email, "role": "receptionist"},
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(receptionist_token), json={"name": "Cleaning"}
    )
    assert resp.status_code == 403

    read_resp = client.get(f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(receptionist_token))
    assert read_resp.status_code == 200


def test_service_creation_is_audited(client, db_session):
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    token = register_and_login(client, "svc-audit-owner@example.com")
    ws_id = create_workspace(client, token, "Audit Svc Clinic", "audit-svc-clinic")
    client.post(f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(token), json={"name": "Cleaning"})

    actions = [row.action for row in db_session.execute(select(AuditLog)).scalars()]
    assert "service.created" in actions


def test_a_newly_created_service_lets_the_ai_receptionist_actually_book(client, db_session):
    """The end-to-end regression test for the bug this phase fixed: a
    service created through the real HTTP API (not a direct DB fixture)
    must be immediately usable by the AI Receptionist's booking flow."""
    from app.ai.conversation.store import InMemoryConversationStore
    from app.ai.llm.mock_provider import MockLLMProvider
    from app.ai.receptionist_service import ReceptionistService
    from app.models.ai_agent import AIAgent
    import uuid as uuid_module

    token = register_and_login(client, "svc-e2e-owner@example.com")
    ws_id_str = create_workspace(client, token, "E2E Svc Clinic", "e2e-svc-clinic")
    ws_id = uuid_module.UUID(ws_id_str)

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/services", headers=auth_headers(token), json={"name": "Cleaning"}
    )
    assert resp.status_code == 201

    db_session.add(
        AIAgent(workspace_id=ws_id, name="AI", is_active=True, config={"supported_languages": ["en"]})
    )
    db_session.commit()

    receptionist = ReceptionistService(db=db_session, llm=MockLLMProvider(), store=InMemoryConversationStore())
    state = receptionist.start_session(ws_id)
    turns = ["Hi", "book an appointment", "My name is Jane Doe", "My phone is 415-555-0100", "Cleaning", "next Monday at 2pm", "Yes"]
    result = None
    for turn in turns:
        result = receptionist.handle_message(ws_id, state.session_id, turn)

    assert "Jane Doe" in result.reply  # booking actually completed, not stuck asking for a service forever
