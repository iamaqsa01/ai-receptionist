"""Phase 17 — Team invite carries an optional phone number.

The dashboard's "Invite member" form now sends `phone_number` alongside
`email`/`role`. It maps onto the global `User.phone` column and never
overwrites a number the invited user already has on file.
"""

from sqlalchemy import select

from app.models.user import User
from tests.conftest import auth_headers, create_workspace, register_and_login


def test_invite_sets_phone_on_user_without_one(client, db_session):
    owner = register_and_login(client, "phone-owner@example.com")
    ws_id = create_workspace(client, owner, "Phone Clinic", "phone-clinic")
    register_and_login(client, "phone-invitee@example.com")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "phone-invitee@example.com", "role": "receptionist", "phone_number": "+1 (415) 555-0100"},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201, resp.text

    invitee = db_session.execute(
        select(User).where(User.email == "phone-invitee@example.com")
    ).scalar_one()
    assert invitee.phone == "+1 (415) 555-0100"


def test_invite_without_phone_is_still_accepted(client, db_session):
    owner = register_and_login(client, "phone-owner-2@example.com")
    ws_id = create_workspace(client, owner, "Phone Clinic 2", "phone-clinic-2")
    register_and_login(client, "phone-invitee-2@example.com")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "phone-invitee-2@example.com", "role": "analyst"},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201, resp.text
    invitee = db_session.execute(
        select(User).where(User.email == "phone-invitee-2@example.com")
    ).scalar_one()
    assert invitee.phone is None


def test_invite_does_not_overwrite_existing_user_phone(client, db_session):
    owner = register_and_login(client, "phone-owner-3@example.com")
    ws_id = create_workspace(client, owner, "Phone Clinic 3", "phone-clinic-3")
    register_and_login(client, "phone-invitee-3@example.com")

    invitee = db_session.execute(
        select(User).where(User.email == "phone-invitee-3@example.com")
    ).scalar_one()
    invitee.phone = "+15550009999"
    db_session.add(invitee)
    db_session.commit()

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "phone-invitee-3@example.com", "role": "receptionist", "phone_number": "+15551110000"},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201, resp.text

    db_session.refresh(invitee)
    assert invitee.phone == "+15550009999"  # unchanged
