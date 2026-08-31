"""Clinic settings / AI knowledge base — dashboard save + prompt build.

The complete clinic configuration is stored in the workspace's active
``ai_agents.config["clinic_settings"]`` while normalized scheduling data is
kept in the existing providers, services, and business-hours tables. Settings
are folded into the AI Receptionist's system prompt by
``generate_system_prompt``."""

import uuid

import pytest

from app.ai.conversation.instructions import generate_system_prompt
from app.models.ai_agent import AIAgent
from app.models.business_hours import BusinessHours
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace
from tests.conftest import auth_headers, create_workspace, register_and_login

SAMPLE_SETTINGS = {
    "doctors": [
        {
            "name": "Dr. Ayesha Khan",
            "specialty": "Dermatology",
            "timings": "Mon-Fri 10:00-14:00",
            "consultation_fee": 3000,
        }
    ],
    "services": ["Skin Consultation", "Laser Treatment"],
    "business_hours": [
        {
            "day_of_week": day,
            "open_time": "09:00:00" if day < 5 else None,
            "close_time": "17:00:00" if day < 5 else None,
            "is_closed": day >= 5,
        }
        for day in range(7)
    ],
    "appointment_settings": {"default_slot_duration_minutes": 20, "max_daily_bookings": 40},
    "general_info": {
        "address": "12 Clinic Road, Lahore",
        "google_maps_link": "https://maps.example.com/clinic",
        "parking_available": True,
        "accepted_payment_methods": ["Cash", "Credit Card"],
    },
    "emergency_protocol": "Tell the caller to dial 1122 immediately and stay on the line for staff.",
    "agent_tone": "Empathetic",
    "preferred_language": "Roman Urdu",
}


def test_put_then_get_clinic_settings_round_trips(client):
    token = register_and_login(client, "clinic-owner@example.com")
    ws_id = create_workspace(client, token, "Skin Clinic", "skin-clinic")

    put_resp = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(token),
        json=SAMPLE_SETTINGS,
    )
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["workspace_id"] == ws_id
    assert body["agent_tone"] == "Empathetic"
    assert body["doctors"][0]["name"] == "Dr. Ayesha Khan"

    get_resp = client.get(
        f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(token)
    )
    assert get_resp.status_code == 200
    got = get_resp.json()
    assert got["services"] == ["Skin Consultation", "Laser Treatment"]
    assert got["appointment_settings"]["default_slot_duration_minutes"] == 20
    assert got["general_info"]["parking_available"] is True
    assert got["preferred_language"] == "Roman Urdu"


def test_saving_clinic_settings_marks_workspace_onboarded(client):
    token = register_and_login(client, "onboard-owner@example.com")
    ws_id = create_workspace(client, token, "Onboard Clinic", "onboard-clinic", onboarded=False)

    def membership(ws):
        me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()
        assert "is_onboarded" not in me, "onboarding is no longer a user-level flag"
        return next(m for m in me["memberships"] if m["workspace_id"] == ws)

    assert membership(ws_id)["is_onboarded"] is False
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(token)).json()["is_onboarded"] is False

    resp = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(token),
        json=SAMPLE_SETTINGS,
    )
    assert resp.status_code == 200, resp.text

    assert membership(ws_id)["is_onboarded"] is True
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(token)).json()["is_onboarded"] is True


def test_onboarding_creates_real_booking_records(client, db_session):
    token = register_and_login(client, "booking-records-owner@example.com")
    ws_id = create_workspace(client, token, "Booking Records Clinic", "booking-records", onboarded=False)

    response = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(token),
        json=SAMPLE_SETTINGS,
    )
    assert response.status_code == 200, response.text

    workspace_uuid = uuid.UUID(ws_id)
    providers = db_session.query(Provider).filter_by(workspace_id=workspace_uuid).all()
    services = db_session.query(Service).filter_by(workspace_id=workspace_uuid).all()
    hours = (
        db_session.query(BusinessHours)
        .filter_by(workspace_id=workspace_uuid)
        .order_by(BusinessHours.day_of_week)
        .all()
    )

    assert [(provider.name, provider.title, provider.is_active) for provider in providers] == [
        ("Dr. Ayesha Khan", "Dermatology", True)
    ]
    assert {(service.name, service.duration_minutes, service.is_active) for service in services} == {
        ("Skin Consultation", 20, True),
        ("Laser Treatment", 20, True),
    }
    assert len(hours) == 7
    assert hours[0].open_time.isoformat() == "09:00:00"
    assert hours[0].close_time.isoformat() == "17:00:00"
    assert hours[0].is_closed is False
    assert hours[6].open_time is None
    assert hours[6].close_time is None
    assert hours[6].is_closed is True


def test_booking_record_sync_is_idempotent_and_soft_deactivates_removed_rows(client, db_session):
    token = register_and_login(client, "booking-sync-owner@example.com")
    ws_id = create_workspace(client, token, "Booking Sync Clinic", "booking-sync", onboarded=False)
    headers = auth_headers(token)
    url = f"/api/v1/workspaces/{ws_id}/clinic-settings"

    assert client.put(url, headers=headers, json=SAMPLE_SETTINGS).status_code == 200
    updated = {
        **SAMPLE_SETTINGS,
        "doctors": [
            {
                **SAMPLE_SETTINGS["doctors"][0],
                "name": "dr. ayesha khan",
                "specialty": "Cosmetic Dermatology",
            }
        ],
        "services": ["skin consultation"],
        "appointment_settings": {
            "default_slot_duration_minutes": 45,
            "max_daily_bookings": 20,
        },
        "business_hours": [
            {
                "day_of_week": day,
                "open_time": "10:00:00" if day == 0 else None,
                "close_time": "14:00:00" if day == 0 else None,
                "is_closed": day != 0,
            }
            for day in range(7)
        ],
    }
    assert client.put(url, headers=headers, json=updated).status_code == 200

    workspace_uuid = uuid.UUID(ws_id)
    providers = db_session.query(Provider).filter_by(workspace_id=workspace_uuid).all()
    services = db_session.query(Service).filter_by(workspace_id=workspace_uuid).all()
    hours = db_session.query(BusinessHours).filter_by(workspace_id=workspace_uuid).all()

    assert len(providers) == 1
    assert providers[0].name == "dr. ayesha khan"
    assert providers[0].title == "Cosmetic Dermatology"
    assert providers[0].is_active is True
    assert len(services) == 2
    active = next(service for service in services if service.is_active)
    inactive = next(service for service in services if not service.is_active)
    assert active.name == "skin consultation"
    assert active.duration_minutes == 45
    assert inactive.name == "Laser Treatment"
    assert len(hours) == 7
    monday = next(row for row in hours if row.day_of_week == 0)
    tuesday = next(row for row in hours if row.day_of_week == 1)
    assert monday.open_time.isoformat() == "10:00:00"
    assert monday.close_time.isoformat() == "14:00:00"
    assert monday.is_closed is False
    assert tuesday.is_closed is True


def test_first_onboarding_requires_complete_business_configuration(client):
    token = register_and_login(client, "incomplete-booking-owner@example.com")
    ws_id = create_workspace(client, token, "Incomplete Clinic", "incomplete-booking", onboarded=False)
    headers = auth_headers(token)

    for patch, expected_detail in [
        ({"doctors": []}, "At least one doctor is required"),
        ({"services": []}, "At least one service is required"),
        ({"business_hours": []}, "Business hours must include all seven weekdays"),
    ]:
        response = client.put(
            f"/api/v1/workspaces/{ws_id}/clinic-settings",
            headers=headers,
            json={**SAMPLE_SETTINGS, **patch},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == expected_detail

    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=headers).json()["is_onboarded"] is False


def test_onboarding_state_is_independent_per_workspace(client):
    """A user with two workspaces onboards each one separately."""
    token = register_and_login(client, "two-clinic-owner@example.com")
    ws_a = create_workspace(client, token, "Branch A", "branch-a", onboarded=False)
    ws_b = create_workspace(client, token, "Branch B", "branch-b", onboarded=False)

    # Complete onboarding for A only.
    assert client.put(
        f"/api/v1/workspaces/{ws_a}/clinic-settings", headers=auth_headers(token), json=SAMPLE_SETTINGS
    ).status_code == 200

    me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()
    state = {m["workspace_id"]: m["is_onboarded"] for m in me["memberships"]}
    assert state[ws_a] is True
    assert state[ws_b] is False

    # A's data routes work; B's are still gated.
    assert client.get(f"/api/v1/workspaces/{ws_a}/patients", headers=auth_headers(token)).status_code == 200
    assert client.get(f"/api/v1/workspaces/{ws_b}/patients", headers=auth_headers(token)).status_code == 403


def test_get_returns_defaults_before_anything_saved(client):
    token = register_and_login(client, "clinic-owner2@example.com")
    ws_id = create_workspace(client, token, "Fresh Clinic", "fresh-clinic")

    resp = client.get(f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["doctors"] == []
    assert body["agent_tone"] == "Professional"
    assert body["preferred_language"] == "English"


def test_put_preserves_other_agent_config_keys(client, db_session):
    token = register_and_login(client, "clinic-owner3@example.com")
    ws_id = create_workspace(client, token, "Keep Clinic", "keep-clinic")

    db_session.add(
        AIAgent(
            workspace_id=uuid.UUID(ws_id),
            name="AI",
            is_active=True,
            config={"instructions": "Be concise.", "supported_languages": ["en"]},
        )
    )
    db_session.commit()

    resp = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(token),
        json=SAMPLE_SETTINGS,
    )
    assert resp.status_code == 200, resp.text

    agent = db_session.query(AIAgent).filter_by(workspace_id=uuid.UUID(ws_id)).one()
    db_session.refresh(agent)
    assert agent.config["instructions"] == "Be concise."
    assert agent.config["supported_languages"] == ["en"]
    assert agent.config["clinic_settings"]["agent_tone"] == "Empathetic"


def test_invalid_tone_is_rejected(client):
    token = register_and_login(client, "clinic-owner4@example.com")
    ws_id = create_workspace(client, token, "Bad Clinic", "bad-clinic")

    resp = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(token),
        json={**SAMPLE_SETTINGS, "agent_tone": "Sarcastic"},
    )
    assert resp.status_code == 422


def test_pakistani_languages_are_accepted(client):
    """PreferredLanguage was widened (Phase 19) to cover every language the
    live-voice pipeline already speaks (app/ai/language/pakistan.py:
    ur/pa/skr/sd/ps), not just Urdu/English/Roman Urdu."""
    token = register_and_login(client, "clinic-owner5@example.com")
    ws_id = create_workspace(client, token, "Multilingual Clinic", "multilingual-clinic")

    for language in ["Punjabi", "Saraiki", "Sindhi", "Pashto"]:
        resp = client.put(
            f"/api/v1/workspaces/{ws_id}/clinic-settings",
            headers=auth_headers(token),
            json={**SAMPLE_SETTINGS, "preferred_language": language},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["preferred_language"] == language

        got = client.get(
            f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(token)
        )
        assert got.json()["preferred_language"] == language


def test_invalid_language_is_rejected(client):
    token = register_and_login(client, "clinic-owner6@example.com")
    ws_id = create_workspace(client, token, "Bad Language Clinic", "bad-language-clinic")

    resp = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(token),
        json={**SAMPLE_SETTINGS, "preferred_language": "Klingon"},
    )
    assert resp.status_code == 422


def test_clinic_settings_are_tenant_isolated(client):
    owner_token = register_and_login(client, "clinic-tenant-owner@example.com")
    ws_id = create_workspace(client, owner_token, "Private Clinic", "private-clinic-settings")

    outsider_token = register_and_login(client, "clinic-tenant-outsider@example.com")
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(outsider_token)
    )
    assert resp.status_code == 404


# -- Phase 4 — workspace-specific completion + transaction safety -----------------


def test_put_clinic_settings_rejects_a_non_member(client):
    """A user must not be able to PUT another tenant's clinic settings by
    swapping the {id} in the URL."""
    owner = register_and_login(client, "p4-owner@example.com")
    ws_id = create_workspace(client, owner, "P4 Owned", "p4-owned", onboarded=False)

    outsider = register_and_login(client, "p4-outsider@example.com")
    resp = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        headers=auth_headers(outsider),
        json=SAMPLE_SETTINGS,
    )
    assert resp.status_code == 404  # membership not revealed; nothing changed

    # The workspace was not touched.
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(owner)).json()["is_onboarded"] is False
    assert client.get(
        f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(owner)
    ).json()["doctors"] == []


def test_completing_onboarding_for_one_workspace_never_touches_the_other(client):
    """A -> false, B -> false.  Complete A  =>  A true, B still false.
    Then complete B  =>  B true, A still true (unchanged)."""
    token = register_and_login(client, "p4-two-owner@example.com")
    ws_a = create_workspace(client, token, "P4 A", "p4-a", onboarded=False)
    ws_b = create_workspace(client, token, "P4 B", "p4-b", onboarded=False)
    hdrs = auth_headers(token)

    def state():
        return {
            m["workspace_id"]: m["is_onboarded"]
            for m in client.get("/api/v1/auth/me", headers=hdrs).json()["memberships"]
        }

    assert state() == {ws_a: False, ws_b: False}

    assert client.put(
        f"/api/v1/workspaces/{ws_a}/clinic-settings", headers=hdrs, json=SAMPLE_SETTINGS
    ).status_code == 200
    assert state() == {ws_a: True, ws_b: False}

    assert client.put(
        f"/api/v1/workspaces/{ws_b}/clinic-settings", headers=hdrs, json=SAMPLE_SETTINGS
    ).status_code == 200
    assert state() == {ws_a: True, ws_b: True}


def test_failed_clinic_settings_save_leaves_workspace_not_onboarded(client, db_session, monkeypatch):
    """Transaction safety: if the save fails, the workspace must NOT be
    marked onboarded and the settings must NOT be persisted — the flip and
    the settings write share one commit."""
    token = register_and_login(client, "p4-txn-owner@example.com")
    ws_id = create_workspace(client, token, "P4 Txn", "p4-txn", onboarded=False)
    hdrs = auth_headers(token)

    # Break the very next commit (the atomic settings + is_onboarded write in
    # update_clinic_settings). Setup above has already committed.
    def boom():
        raise RuntimeError("simulated DB failure while saving clinic settings")

    monkeypatch.setattr(db_session, "commit", boom)
    # The commit failure propagates as a 500 to a real client; TestClient
    # (raise_server_exceptions default) re-raises it. Either way, nothing is
    # persisted — that is what this test proves via the post-conditions.
    with pytest.raises(RuntimeError):
        client.put(f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=hdrs, json=SAMPLE_SETTINGS)
    monkeypatch.undo()
    db_session.rollback()  # prod: a fresh per-request session; here: reset the shared one

    # Nothing was persisted.
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=hdrs).json()["is_onboarded"] is False
    assert client.get(f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=hdrs).json()["doctors"] == []
    # And the gate is still closed for this workspace.
    assert client.get(f"/api/v1/workspaces/{ws_id}/patients", headers=hdrs).status_code == 403

    # A subsequent successful save still works and flips the flag.
    assert client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=hdrs, json=SAMPLE_SETTINGS
    ).status_code == 200
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=hdrs).json()["is_onboarded"] is True


def test_generate_system_prompt_includes_saved_settings(db_session):
    ws = Workspace(name="Prompt Clinic", slug="prompt-clinic", timezone="Asia/Karachi")
    db_session.add(ws)
    db_session.flush()
    db_session.add(
        AIAgent(
            workspace_id=ws.id,
            name="AI",
            is_active=True,
            config={"supported_languages": ["en"], "clinic_settings": SAMPLE_SETTINGS},
        )
    )
    db_session.commit()

    prompt = generate_system_prompt(ws.id, db=db_session)

    assert "Dr. Ayesha Khan" in prompt
    assert "Dermatology" in prompt
    assert "Skin Consultation" in prompt
    assert "20 minutes" in prompt
    assert "12 Clinic Road, Lahore" in prompt
    assert "Empathetic" in prompt
    assert "Roman Urdu" in prompt
    # Emergency protocol is verbatim and reinforced with the no-diagnosis rule.
    assert "dial 1122 immediately" in prompt
    assert "do NOT provide any independent" in prompt.replace("\n", " ")


def test_generate_system_prompt_has_safe_emergency_default(db_session):
    ws = Workspace(name="Default Clinic", slug="default-emergency-clinic")
    db_session.add(ws)
    db_session.flush()
    db_session.add(AIAgent(workspace_id=ws.id, name="AI", is_active=True, config={}))
    db_session.commit()

    prompt = generate_system_prompt(ws.id, db=db_session)
    assert "EMERGENCY PROTOCOL" in prompt
    assert "not attempt to diagnose" in prompt.lower()
    assert "emergency number" in prompt
