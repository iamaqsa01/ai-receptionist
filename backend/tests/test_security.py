"""Phase 14 — security audit fixes: Twilio webhook signature verification,
rate limiting, tenant-isolation/IDOR closes on appointment creation, input
validation tightening, request body size limits, and secure-by-default
config enforcement."""

import base64
import hashlib
import hmac

import pytest
from pydantic import ValidationError

from app.core.config import DEV_ONLY_SECRET_KEY, Settings
from app.core.rate_limit import RateLimiter
from tests.conftest import auth_headers, create_workspace, register_and_login


COMPLETE_CLINIC_SETTINGS = {
    "doctors": [{"name": "Dr. Security", "specialty": "General Practice"}],
    "services": ["Consultation"],
    "business_hours": [
        {
            "day_of_week": day,
            "open_time": "09:00:00" if day < 5 else None,
            "close_time": "17:00:00" if day < 5 else None,
            "is_closed": day >= 5,
        }
        for day in range(7)
    ],
}


# -- Twilio webhook signature verification --------------------------------------------


def _twilio_signature(auth_token: str, url: str, params: dict) -> str:
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    return base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()


@pytest.fixture()
def twilio_configured(monkeypatch):
    import app.api.telephony as telephony_module

    monkeypatch.setattr(telephony_module.settings, "telephony_provider", "twilio")
    monkeypatch.setattr(telephony_module.settings, "twilio_account_sid", "ACtest123")
    monkeypatch.setattr(telephony_module.settings, "twilio_auth_token", "test-auth-token-secret")
    yield
    monkeypatch.setattr(telephony_module.settings, "telephony_provider", "mock")
    monkeypatch.setattr(telephony_module.settings, "twilio_account_sid", "")
    monkeypatch.setattr(telephony_module.settings, "twilio_auth_token", "")


def test_webhook_without_twilio_configured_is_not_signature_checked(client, db_session):
    """Default (mock) config: the webhook is only reachable from tests/dev
    tooling anyway, so no signature is required — matches existing
    test_telephony_webhook.py behavior."""
    from app.models.workspace import Workspace

    ws = Workspace(name="No Sig Clinic", slug="no-sig-clinic")
    db_session.add(ws)
    db_session.commit()

    resp = client.post(f"/api/v1/telephony/twilio/{ws.id}/voice", data={"From": "+1", "To": "+2"})
    assert resp.status_code == 200


def test_webhook_rejects_missing_signature_when_twilio_configured(client, db_session, twilio_configured):
    from app.models.workspace import Workspace

    ws = Workspace(name="Sig Clinic", slug="sig-clinic")
    db_session.add(ws)
    db_session.commit()

    resp = client.post(f"/api/v1/telephony/twilio/{ws.id}/voice", data={"From": "+1", "To": "+2"})
    assert resp.status_code == 403


def test_webhook_rejects_forged_signature_when_twilio_configured(client, db_session, twilio_configured):
    from app.models.workspace import Workspace

    ws = Workspace(name="Sig Clinic 2", slug="sig-clinic-2")
    db_session.add(ws)
    db_session.commit()

    resp = client.post(
        f"/api/v1/telephony/twilio/{ws.id}/voice",
        data={"From": "+1", "To": "+2"},
        headers={"X-Twilio-Signature": "not-a-real-signature"},
    )
    assert resp.status_code == 403


def test_webhook_accepts_a_correctly_computed_signature(client, db_session, twilio_configured):
    from app.models.workspace import Workspace

    ws = Workspace(name="Sig Clinic 3", slug="sig-clinic-3")
    db_session.add(ws)
    db_session.commit()

    url = f"http://testserver/api/v1/telephony/twilio/{ws.id}/voice"
    params = {"From": "+15551234567", "To": "+15559990000"}
    signature = _twilio_signature("test-auth-token-secret", url, params)

    resp = client.post(
        f"/api/v1/telephony/twilio/{ws.id}/voice",
        data=params,
        headers={"X-Twilio-Signature": signature},
    )
    assert resp.status_code == 200
    # The stream URL now carries a short-lived token (see
    # app.telephony.stream_token) — minted only because the signature
    # above checked out.
    assert "token=" in resp.text


# -- WebSocket stream endpoint: token required only for the twilio path --------------


def test_stream_endpoint_rejects_twilio_connection_without_token(client, db_session, twilio_configured):
    from app.models.workspace import Workspace

    ws = Workspace(name="Stream Clinic", slug="stream-clinic")
    db_session.add(ws)
    db_session.commit()

    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/v1/telephony/stream/twilio/{ws.id}"):
            pass


def test_stream_endpoint_accepts_twilio_connection_with_a_token_minted_by_the_webhook(client, db_session, twilio_configured):
    from app.models.workspace import Workspace

    ws = Workspace(name="Stream Clinic 2", slug="stream-clinic-2")
    db_session.add(ws)
    db_session.commit()

    url = f"http://testserver/api/v1/telephony/twilio/{ws.id}/voice"
    params = {"From": "+15551234567", "To": "+15559990000"}
    signature = _twilio_signature("test-auth-token-secret", url, params)
    voice_resp = client.post(
        f"/api/v1/telephony/twilio/{ws.id}/voice", data=params, headers={"X-Twilio-Signature": signature}
    )
    token = voice_resp.text.split("token=")[1].split('"')[0]

    with client.websocket_connect(f"/api/v1/telephony/stream/twilio/{ws.id}?token={token}") as ws_conn:
        ws_conn.close()  # connection succeeded — that's the assertion


def test_stream_endpoint_mock_provider_unaffected_by_twilio_token_requirement(client, db_session, twilio_configured):
    """Even with Twilio configured elsewhere, the mock provider path (used
    by local/dev tooling and the rest of the test suite) never requires a
    token — only provider="twilio" connections do."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Stream Clinic 3", slug="stream-clinic-3")
    db_session.add(ws)
    db_session.commit()

    with client.websocket_connect(f"/api/v1/telephony/stream/mock/{ws.id}") as ws_conn:
        ws_conn.close()


# -- rate limiting -----------------------------------------------------------------


def test_rate_limiter_blocks_after_the_configured_limit():
    limiter = RateLimiter(limit=3, window_seconds=60)

    class FakeClient:
        host = "1.2.3.4"

    class FakeRequest:
        headers: dict = {}
        client = FakeClient()

    req = FakeRequest()
    for _ in range(3):
        limiter.check(req)  # must not raise
    with pytest.raises(Exception):
        limiter.check(req)


def test_login_endpoint_is_rate_limited(client):
    email = "ratelimit-login@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-1", "full_name": "RL"})

    statuses = []
    for _ in range(15):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        statuses.append(resp.status_code)
    assert 429 in statuses


def test_register_endpoint_is_rate_limited(client):
    statuses = []
    for i in range(10):
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": f"ratelimit-reg-{i}@example.com", "password": "correct-horse-1", "full_name": "RL"},
        )
        statuses.append(resp.status_code)
    assert 429 in statuses


# -- appointment IDOR: provider_id / service_id must belong to the workspace -----------


def test_cannot_create_appointment_with_another_workspaces_provider(client, db_session):
    from app.models.patient import Patient
    from app.models.provider import Provider

    owner_token = register_and_login(client, "idor-owner@example.com")
    ws_id = create_workspace(client, owner_token, "IDOR Clinic", "idor-clinic")
    patient = Patient(workspace_id=ws_id, first_name="Jane", last_name="Doe")
    db_session.add(patient)
    db_session.commit()

    other_ws_id = create_workspace(client, owner_token, "IDOR Other Clinic", "idor-other-clinic")
    foreign_provider = Provider(workspace_id=other_ws_id, name="Dr. Foreign")
    db_session.add(foreign_provider)
    db_session.commit()

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/appointments",
        headers=auth_headers(owner_token),
        json={
            "patient_id": str(patient.id),
            "provider_id": str(foreign_provider.id),
            "start_time": "2027-01-01T15:00:00Z",
            "end_time": "2027-01-01T15:30:00Z",
        },
    )
    assert resp.status_code == 404


def test_appointment_status_is_not_caller_settable(client, db_session):
    from app.models.patient import Patient

    token = register_and_login(client, "status-owner@example.com")
    ws_id = create_workspace(client, token, "Status Clinic", "status-clinic")
    patient = Patient(workspace_id=ws_id, first_name="Jane", last_name="Doe")
    db_session.add(patient)
    db_session.commit()

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/appointments",
        headers=auth_headers(token),
        json={
            "patient_id": str(patient.id),
            "status": "completed",  # extra/unknown field — ignored by Pydantic, not applied
            "start_time": "2027-01-01T15:00:00Z",
            "end_time": "2027-01-01T15:30:00Z",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "scheduled"


def test_appointment_end_before_start_is_rejected(client, db_session):
    from app.models.patient import Patient

    token = register_and_login(client, "range-owner@example.com")
    ws_id = create_workspace(client, token, "Range Clinic", "range-clinic")
    patient = Patient(workspace_id=ws_id, first_name="Jane", last_name="Doe")
    db_session.add(patient)
    db_session.commit()

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/appointments",
        headers=auth_headers(token),
        json={
            "patient_id": str(patient.id),
            "start_time": "2027-01-01T15:30:00Z",
            "end_time": "2027-01-01T15:00:00Z",
        },
    )
    assert resp.status_code == 422


# -- input validation: email / lead status ------------------------------------------


def test_lead_with_invalid_email_is_rejected(client):
    token = register_and_login(client, "invalidemail-owner@example.com")
    ws_id = create_workspace(client, token, "Email Clinic", "email-clinic")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/leads",
        headers=auth_headers(token),
        json={"name": "Jane Doe", "email": "not-an-email"},
    )
    assert resp.status_code == 422


def test_lead_with_invalid_status_is_rejected(client):
    token = register_and_login(client, "invalidstatus-owner@example.com")
    ws_id = create_workspace(client, token, "Status2 Clinic", "status2-clinic")

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/leads",
        headers=auth_headers(token),
        json={"name": "Jane Doe", "status": "<script>alert(1)</script>"},
    )
    assert resp.status_code == 422


# -- request body size limit ---------------------------------------------------------


def test_oversized_request_body_is_rejected(client):
    huge_name = "a" * (3 * 1024 * 1024)  # 3 MB, over the 2 MB cap
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "huge@example.com", "password": "correct-horse-1", "full_name": huge_name},
    )
    assert resp.status_code == 413


# -- secure-by-default config ---------------------------------------------------------


def test_settings_refuses_default_secret_key_outside_development():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", secret_key=DEV_ONLY_SECRET_KEY)


def test_settings_allows_default_secret_key_in_development():
    cfg = Settings(_env_file=None, app_env="development", secret_key=DEV_ONLY_SECRET_KEY)
    assert cfg.secret_key == DEV_ONLY_SECRET_KEY


def test_settings_allows_any_secret_key_in_production():
    cfg = Settings(_env_file=None, app_env="production", secret_key="a-real-generated-secret")
    assert cfg.is_production_like is True


# -- docs / CORS -----------------------------------------------------------------------


def test_docs_are_reachable_in_the_test_app(client):
    # The test app runs with default (development) settings, so docs stay on.
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_cors_middleware_does_not_allow_credentials():
    from app.main import app

    cors_middleware = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors_middleware.kwargs.get("allow_credentials") is False


# -- Server-side onboarding gate (per-workspace) -----------------------------------

_GATED_PATHS = [
    ("GET", "/patients"),
    ("GET", "/leads"),
    ("GET", "/appointments"),
    ("GET", "/calls"),
    ("GET", "/analytics/summary"),
    ("POST", "/ai/sessions"),
    ("GET", "/human-handoffs"),
    ("GET", "/notification-messages"),
    ("GET", "/services"),
    ("GET", "/providers"),
    ("GET", "/members"),
]


@pytest.mark.parametrize("method,suffix", _GATED_PATHS)
def test_data_routes_are_blocked_until_the_workspace_is_onboarded(client, method, suffix):
    token = register_and_login(client, "gate-blocked@example.com")
    ws_id = create_workspace(client, token, "Gate Clinic", "gate-clinic", onboarded=False)

    resp = client.request(method, f"/api/v1/workspaces/{ws_id}{suffix}", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
    assert "onboarding" in resp.json()["detail"].lower()


def test_workspace_can_still_complete_onboarding_then_use_data_routes(client):
    """The gate must not lock a workspace out of the endpoints that finish
    onboarding — otherwise the form could never be submitted."""
    token = register_and_login(client, "gate-completes@example.com")
    ws_id = create_workspace(client, token, "Completes Clinic", "completes-clinic", onboarded=False)
    hdrs = auth_headers(token)

    # These stay open (require_permission / get_current_user auth, no gate):
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=hdrs).status_code == 200
    assert client.get(f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=hdrs).status_code == 200
    assert client.patch(
        f"/api/v1/workspaces/{ws_id}", json={"name": "Renamed", "timezone": "Asia/Karachi"}, headers=hdrs
    ).status_code == 200

    # Blocked before completing setup.
    assert client.get(f"/api/v1/workspaces/{ws_id}/patients", headers=hdrs).status_code == 403

    # Completing the clinic-settings form flips workspaces.is_onboarded.
    assert client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        json=COMPLETE_CLINIC_SETTINGS,
        headers=hdrs,
    ).status_code == 200

    # Now the gated routes open up — for this workspace.
    assert client.get(f"/api/v1/workspaces/{ws_id}/patients", headers=hdrs).status_code == 200
    assert client.get(f"/api/v1/workspaces/{ws_id}/analytics/summary", headers=hdrs).status_code == 200


def test_non_member_gets_404_regardless_of_workspace_onboarding_state(client):
    """The onboarding gate runs after membership resolution: an outsider
    never learns a workspace's onboarding state — they just get the tenant
    404, whether the workspace is onboarded or not."""
    outsider = register_and_login(client, "gate-outsider@example.com")
    owner = register_and_login(client, "gate-real-owner@example.com")

    onboarded_ws = create_workspace(client, owner, "Onboarded Clinic", "gate-onboarded", onboarded=True)
    fresh_ws = create_workspace(client, owner, "Fresh Clinic", "gate-fresh", onboarded=False)

    assert client.get(
        f"/api/v1/workspaces/{onboarded_ws}/patients", headers=auth_headers(outsider)
    ).status_code == 404
    assert client.get(
        f"/api/v1/workspaces/{fresh_ws}/patients", headers=auth_headers(outsider)
    ).status_code == 404


# -- Phase 3 — the four required workspace-onboarding security scenarios -----------


def _complete_onboarding(client, token, ws_id):
    r = client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings",
        json=COMPLETE_CLINIC_SETTINGS,
        headers=auth_headers(token),
    )
    assert r.status_code == 200, r.text


def test_scenario_1_onboarded_workspace_allowed_fresh_workspace_requires_onboarding(client):
    """Workspace A (onboarded) -> allowed. Workspace B (not) -> onboarding required.
    B's state must never block A."""
    token = register_and_login(client, "s1-owner@example.com")
    ws_a = create_workspace(client, token, "S1 A", "s1-a", onboarded=True)
    ws_b = create_workspace(client, token, "S1 B", "s1-b", onboarded=False)
    hdrs = auth_headers(token)

    assert client.get(f"/api/v1/workspaces/{ws_a}/patients", headers=hdrs).status_code == 200

    resp_b = client.get(f"/api/v1/workspaces/{ws_b}/patients", headers=hdrs)
    assert resp_b.status_code == 403
    assert "onboarding" in resp_b.json()["detail"].lower()

    # And A keeps working while B is still incomplete.
    assert client.get(f"/api/v1/workspaces/{ws_a}/appointments", headers=hdrs).status_code == 200


def test_scenario_2_user_cannot_reach_another_users_workspace_by_changing_the_id(client):
    """User A attempts User B's workspace -> denied (404, existence not revealed),
    for both an onboarded and a fresh target workspace."""
    user_a = register_and_login(client, "s2-a@example.com")
    user_b = register_and_login(client, "s2-b@example.com")

    b_onboarded = create_workspace(client, user_b, "S2 B onboarded", "s2-b-on", onboarded=True)
    b_fresh = create_workspace(client, user_b, "S2 B fresh", "s2-b-fresh", onboarded=False)

    # User A even has their own onboarded workspace — still no crossover.
    create_workspace(client, user_a, "S2 A", "s2-a-ws", onboarded=True)

    for target in (b_onboarded, b_fresh):
        for suffix in ("/patients", "/appointments", "/analytics/summary", "/members"):
            r = client.get(f"/api/v1/workspaces/{target}{suffix}", headers=auth_headers(user_a))
            assert r.status_code == 404, (target, suffix, r.status_code, r.text)


def test_scenario_3_completing_B_onboarding_does_not_touch_A(client):
    """Complete Workspace B onboarding -> B becomes true, A is unchanged."""
    token = register_and_login(client, "s3-owner@example.com")
    ws_a = create_workspace(client, token, "S3 A", "s3-a", onboarded=True)
    ws_b = create_workspace(client, token, "S3 B", "s3-b", onboarded=False)
    hdrs = auth_headers(token)

    a_before = client.get(f"/api/v1/workspaces/{ws_a}", headers=hdrs).json()["is_onboarded"]
    assert a_before is True
    assert client.get(f"/api/v1/workspaces/{ws_b}", headers=hdrs).json()["is_onboarded"] is False

    _complete_onboarding(client, token, ws_b)

    state = {
        m["workspace_id"]: m["is_onboarded"]
        for m in client.get("/api/v1/auth/me", headers=hdrs).json()["memberships"]
    }
    assert state[ws_b] is True          # B flipped
    assert state[ws_a] is True          # A unchanged (was already true)
    # A never became "not onboarded" as a side effect, and its routes still work.
    assert client.get(f"/api/v1/workspaces/{ws_a}/patients", headers=hdrs).status_code == 200


def test_scenario_3b_onboarding_one_fresh_workspace_leaves_the_other_fresh(client):
    """Both start false; onboard B only -> B true, A still false and still gated."""
    token = register_and_login(client, "s3b-owner@example.com")
    ws_a = create_workspace(client, token, "S3b A", "s3b-a", onboarded=False)
    ws_b = create_workspace(client, token, "S3b B", "s3b-b", onboarded=False)
    hdrs = auth_headers(token)

    _complete_onboarding(client, token, ws_b)

    assert client.get(f"/api/v1/workspaces/{ws_b}/patients", headers=hdrs).status_code == 200
    assert client.get(f"/api/v1/workspaces/{ws_a}/patients", headers=hdrs).status_code == 403
    assert client.get(f"/api/v1/workspaces/{ws_a}", headers=hdrs).json()["is_onboarded"] is False


def test_scenario_4_user_is_not_globally_trapped_by_an_incomplete_workspace(client):
    """Workspace A is onboarded -> the user can use A fully even though
    Workspace B (and C) are incomplete. No global trap, no user-level flag."""
    token = register_and_login(client, "s4-owner@example.com")
    ws_a = create_workspace(client, token, "S4 A", "s4-a", onboarded=True)
    create_workspace(client, token, "S4 B", "s4-b", onboarded=False)
    create_workspace(client, token, "S4 C", "s4-c", onboarded=False)
    hdrs = auth_headers(token)

    me = client.get("/api/v1/auth/me", headers=hdrs).json()
    assert "is_onboarded" not in me, "there is no user-level onboarding flag any more"

    for suffix in ("/patients", "/leads", "/appointments", "/calls", "/analytics/summary"):
        assert client.get(f"/api/v1/workspaces/{ws_a}{suffix}", headers=hdrs).status_code == 200, suffix


def test_onboarded_tenant_dependency_enforces_all_six_requirements(client):
    """get_current_onboarded_user / _tenant must verify, in order:
    (1) authenticated (2) workspace exists (3) caller is a member
    (4) it's the caller's tenant (5) onboarding state read (6) 403 if false.
    """
    import uuid as _uuid

    owner = register_and_login(client, "req-owner@example.com")
    outsider = register_and_login(client, "req-outsider@example.com")
    ws_fresh = create_workspace(client, owner, "Req Fresh", "req-fresh", onboarded=False)
    ws_done = create_workspace(client, owner, "Req Done", "req-done", onboarded=True)
    path = "/patients"

    # (1) not authenticated -> 401
    assert client.get(f"/api/v1/workspaces/{ws_done}{path}").status_code == 401

    # (2) workspace does not exist -> 404 (never 403/500)
    ghost = _uuid.uuid4()
    assert client.get(f"/api/v1/workspaces/{ghost}{path}", headers=auth_headers(owner)).status_code == 404

    # (3)+(4) authenticated but not a member of this tenant -> 404 (isolation)
    assert client.get(f"/api/v1/workspaces/{ws_done}{path}", headers=auth_headers(outsider)).status_code == 404

    # (5)+(6) member, workspace exists, onboarding read -> 403 when incomplete
    r = client.get(f"/api/v1/workspaces/{ws_fresh}{path}", headers=auth_headers(owner))
    assert r.status_code == 403 and "onboarding" in r.json()["detail"].lower()

    # member + onboarded -> allowed
    assert client.get(f"/api/v1/workspaces/{ws_done}{path}", headers=auth_headers(owner)).status_code == 200
