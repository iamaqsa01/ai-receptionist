"""Phone number -> workspace routing: the management API and the model.

A phone number assigned to a workspace is what an inbound Vapi call is
routed by (see tests/test_vapi_tools.py for the routing side). Managing the
assignments is clinic configuration: any member may read them, only
Owner/Admin (settings:manage) may change them — no new role or permission.
"""

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.phone_number import PhoneNumber
from tests.conftest import auth_headers, create_workspace, register_and_login


def test_add_and_list_phone_number(client):
    token = register_and_login(client, "pn-owner@example.com")
    ws_id = create_workspace(client, token, "Phone Clinic", "phone-clinic")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+14155550100"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["number"] == "+14155550100"
    assert body["workspace_id"] == ws_id

    list_resp = client.get(
        f"/api/v1/workspaces/{ws_id}/phone-numbers", headers=auth_headers(token)
    )
    assert list_resp.status_code == 200
    assert [row["number"] for row in list_resp.json()] == ["+14155550100"]


def test_phone_number_is_normalized_to_e164(client):
    token = register_and_login(client, "pn-normalize@example.com")
    ws_id = create_workspace(client, token, "Norm Clinic", "norm-clinic")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+1 (415) 555-0100"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["number"] == "+14155550100"


def test_invalid_phone_numbers_are_rejected(client):
    token = register_and_login(client, "pn-invalid@example.com")
    ws_id = create_workspace(client, token, "Invalid Clinic", "invalid-clinic")

    # No country code / not parseable as an international number.
    for bad in ["not-a-number", "12345", "555-0100", "+", "abcdefghij"]:
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/phone-numbers",
            headers=auth_headers(token),
            json={"number": bad},
        )
        assert resp.status_code == 422, f"{bad!r} -> {resp.status_code}"


def test_duplicate_phone_number_in_same_workspace_conflicts(client):
    token = register_and_login(client, "pn-dup@example.com")
    ws_id = create_workspace(client, token, "Dup Clinic", "dup-clinic")

    first = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+14155550100"},
    )
    assert first.status_code == 201
    # Different formatting, same number.
    second = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+1 415-555-0100"},
    )
    assert second.status_code == 409


def test_phone_number_cannot_be_claimed_by_two_workspaces(client):
    owner_a = register_and_login(client, "pn-ws-a@example.com")
    ws_a = create_workspace(client, owner_a, "Clinic A", "pn-clinic-a")
    owner_b = register_and_login(client, "pn-ws-b@example.com")
    ws_b = create_workspace(client, owner_b, "Clinic B", "pn-clinic-b")

    a_resp = client.post(
        f"/api/v1/workspaces/{ws_a}/phone-numbers",
        headers=auth_headers(owner_a),
        json={"number": "+14155550100"},
    )
    assert a_resp.status_code == 201

    b_resp = client.post(
        f"/api/v1/workspaces/{ws_b}/phone-numbers",
        headers=auth_headers(owner_b),
        json={"number": "+14155550100"},
    )
    assert b_resp.status_code == 409
    # And it did not leak into workspace B.
    b_list = client.get(
        f"/api/v1/workspaces/{ws_b}/phone-numbers", headers=auth_headers(owner_b)
    )
    assert b_list.json() == []


def test_phone_numbers_are_tenant_isolated(client):
    owner_token = register_and_login(client, "pn-iso-owner@example.com")
    ws_id = create_workspace(client, owner_token, "Private PN Clinic", "private-pn-clinic")
    client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(owner_token),
        json={"number": "+14155550100"},
    )

    outsider_token = register_and_login(client, "pn-iso-outsider@example.com")
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/phone-numbers", headers=auth_headers(outsider_token)
    )
    assert resp.status_code == 404  # tenant isolation: 404, not 403 or empty list


def test_receptionist_can_read_but_not_manage_phone_numbers(client):
    owner_token = register_and_login(client, "pn-rbac-owner@example.com")
    ws_id = create_workspace(client, owner_token, "RBAC PN Clinic", "rbac-pn-clinic")

    receptionist_email = "pn-rbac-receptionist@example.com"
    receptionist_token = register_and_login(client, receptionist_email)
    client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers=auth_headers(owner_token),
        json={"email": receptionist_email, "role": "receptionist"},
    )

    create_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(receptionist_token),
        json={"number": "+14155550100"},
    )
    assert create_resp.status_code == 403

    read_resp = client.get(
        f"/api/v1/workspaces/{ws_id}/phone-numbers", headers=auth_headers(receptionist_token)
    )
    assert read_resp.status_code == 200


def test_delete_phone_number(client):
    token = register_and_login(client, "pn-del@example.com")
    ws_id = create_workspace(client, token, "Del Clinic", "del-clinic")
    created = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+14155550100"},
    ).json()

    del_resp = client.delete(
        f"/api/v1/workspaces/{ws_id}/phone-numbers/{created['id']}", headers=auth_headers(token)
    )
    assert del_resp.status_code == 204

    list_resp = client.get(
        f"/api/v1/workspaces/{ws_id}/phone-numbers", headers=auth_headers(token)
    )
    assert list_resp.json() == []


def test_delete_unknown_phone_number_is_404(client):
    token = register_and_login(client, "pn-del-404@example.com")
    ws_id = create_workspace(client, token, "Del404 Clinic", "del404-clinic")
    resp = client.delete(
        f"/api/v1/workspaces/{ws_id}/phone-numbers/{uuid.uuid4()}", headers=auth_headers(token)
    )
    assert resp.status_code == 404


def test_cannot_delete_another_workspaces_phone_number(client):
    owner_a = register_and_login(client, "pn-del-a@example.com")
    ws_a = create_workspace(client, owner_a, "Del Clinic A", "del-clinic-a")
    created = client.post(
        f"/api/v1/workspaces/{ws_a}/phone-numbers",
        headers=auth_headers(owner_a),
        json={"number": "+14155550100"},
    ).json()

    owner_b = register_and_login(client, "pn-del-b@example.com")
    ws_b = create_workspace(client, owner_b, "Del Clinic B", "del-clinic-b")
    resp = client.delete(
        f"/api/v1/workspaces/{ws_b}/phone-numbers/{created['id']}", headers=auth_headers(owner_b)
    )
    assert resp.status_code == 404
    # Still there for workspace A.
    a_list = client.get(
        f"/api/v1/workspaces/{ws_a}/phone-numbers", headers=auth_headers(owner_a)
    )
    assert len(a_list.json()) == 1


def test_phone_number_management_requires_onboarded_workspace(client):
    token = register_and_login(client, "pn-onboard@example.com")
    ws_id = create_workspace(client, token, "Unonboarded", "pn-unonboarded", onboarded=False)
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+14155550100"},
    )
    assert resp.status_code == 403


def test_adding_a_phone_number_is_audited(client, db_session):
    token = register_and_login(client, "pn-audit@example.com")
    ws_id = create_workspace(client, token, "Audit PN Clinic", "audit-pn-clinic")
    client.post(
        f"/api/v1/workspaces/{ws_id}/phone-numbers",
        headers=auth_headers(token),
        json={"number": "+14155550100"},
    )
    actions = [row.action for row in db_session.execute(select(AuditLog)).scalars()]
    assert "phone_number.added" in actions


def test_phone_number_model_has_uuid_pk_and_timestamps(db_session):
    workspace_id = uuid.uuid4()
    from app.models.workspace import Workspace

    db_session.add(Workspace(id=workspace_id, name="M", slug=f"m-{workspace_id.hex}", timezone="UTC"))
    db_session.flush()

    pn = PhoneNumber(number="+14155550100", workspace_id=workspace_id)
    db_session.add(pn)
    db_session.commit()
    db_session.refresh(pn)

    assert isinstance(pn.id, uuid.UUID)
    assert pn.created_at is not None
    assert pn.updated_at is not None
