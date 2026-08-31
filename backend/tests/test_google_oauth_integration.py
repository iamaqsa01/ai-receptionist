from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.ai.scheduling.outcomes import BookingOutcome
from app.core.config import Settings, settings
from app.integrations.calendar.factory import get_calendar_provider_for_workspace
from app.integrations.calendar.google_provider import GoogleOAuthCalendarProvider
from app.integrations.calendar.mock_provider import MockCalendarProvider
from app.integrations.calendar.token_crypto import decrypt_token
from app.models.integration import Integration
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.scheduling import AppointmentBookingRequest, AppointmentSchedulingService
from tests.conftest import auth_headers, create_workspace, register_and_login


def _configure_oauth(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "oauth-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "oauth-client-secret")
    monkeypatch.setattr(
        settings,
        "google_redirect_uri",
        "http://testserver/api/v1/integrations/google/callback",
    )


def _start_connection(client, token, workspace_id):
    response = client.get(
        "/api/v1/integrations/google/connect",
        params={"workspace_id": workspace_id},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    authorization_url = response.json()["authorization_url"]
    query = parse_qs(urlparse(authorization_url).query)
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"]
    return query["state"][0]


def test_workspace_owner_completes_oauth_and_tokens_are_encrypted(client, db_session, monkeypatch):
    _configure_oauth(monkeypatch)
    token = register_and_login(client, "google-oauth-owner@example.com")
    workspace_id = create_workspace(client, token, "OAuth Clinic", "oauth-clinic")
    state = _start_connection(client, token, workspace_id)

    pending = db_session.execute(
        select(Integration).where(Integration.workspace_id == workspace_id)
    ).scalar_one()
    assert pending.is_active is False
    assert pending.config["connected_status"] == "connecting"
    assert pending.config["oauth_pending"]["code_verifier"].startswith("enc:v1:")

    monkeypatch.setattr(
        "app.integrations.calendar.oauth.exchange_google_code",
        lambda code, verifier, cfg: {
            "access_token": "plain-access-token",
            "refresh_token": "plain-refresh-token",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar",
        },
    )
    monkeypatch.setattr(
        "app.integrations.calendar.oauth.fetch_google_calendar_identity",
        lambda access_token, cfg: ("owner@example.com", "Owner Calendar"),
    )

    callback = client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "authorization-code", "state": state},
    )
    assert callback.status_code == 200, callback.text
    replay = client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "authorization-code", "state": state},
    )
    assert replay.status_code == 400

    db_session.expire_all()
    integration = db_session.execute(
        select(Integration).where(Integration.workspace_id == workspace_id)
    ).scalar_one()
    assert integration.is_active is True
    assert integration.config["auth_type"] == "oauth"
    assert integration.config["connected_status"] == "connected"
    assert integration.config["calendar_id"] == "owner@example.com"
    assert integration.config["calendar_name"] == "Owner Calendar"
    assert integration.config["access_token"] != "plain-access-token"
    assert integration.config["refresh_token"] != "plain-refresh-token"
    assert decrypt_token(integration.config["access_token"]) == "plain-access-token"
    assert decrypt_token(integration.config["refresh_token"]) == "plain-refresh-token"
    assert "oauth_pending" not in integration.config

    status_response = client.get(
        "/api/v1/integrations/google/status",
        params={"workspace_id": workspace_id},
        headers=auth_headers(token),
    )
    assert status_response.status_code == 200
    assert status_response.json() == {
        "connected": True,
        "status": "connected",
        "auth_type": "oauth",
        "calendar_id": "owner@example.com",
        "calendar_name": "Owner Calendar",
    }
    assert "token" not in status_response.text


def test_oauth_workspace_provider_and_canonical_booking_flow(db_session, monkeypatch):
    cfg = Settings(
        _env_file=None,
        secret_key="oauth-provider-test-secret",
        google_client_id="client",
        google_client_secret="secret",
    )
    from app.integrations.calendar.token_crypto import encrypt_token

    workspace = Workspace(name="OAuth Booking Clinic", slug="oauth-booking-clinic", timezone="UTC", is_onboarded=True)
    db_session.add(workspace)
    db_session.flush()
    service = Service(workspace_id=workspace.id, name="Consultation", duration_minutes=15, is_active=True)
    db_session.add_all(
        [
            service,
            Integration(
                workspace_id=workspace.id,
                provider="google_calendar",
                is_active=True,
                config={
                    "auth_type": "oauth",
                    "connected_status": "connected",
                    "access_token": encrypt_token("access", cfg),
                    "refresh_token": encrypt_token("refresh", cfg),
                    "token_expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "calendar_id": "clinic-owner@example.com",
                    "calendar_name": "Clinic Calendar",
                },
            ),
        ]
    )
    db_session.commit()

    provider = get_calendar_provider_for_workspace(db_session, workspace.id, cfg)
    assert isinstance(provider, GoogleOAuthCalendarProvider)
    assert provider.is_available()
    refreshed_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
    provider._on_credentials_updated("refreshed-access", refreshed_expiry)
    db_session.expire_all()
    refreshed = db_session.execute(
        select(Integration).where(Integration.workspace_id == workspace.id)
    ).scalar_one()
    assert decrypt_token(refreshed.config["access_token"], cfg) == "refreshed-access"

    calendar = MockCalendarProvider()
    monkeypatch.setattr(
        "app.integrations.calendar.sync.get_calendar_provider_for_workspace",
        lambda db, workspace_id: calendar,
    )
    start = datetime.now(timezone.utc) + timedelta(days=7)
    result = AppointmentSchedulingService(db_session).book_appointment(
        AppointmentBookingRequest(
            workspace=workspace,
            service=service,
            start_time=start,
            patient_name="OAuth Patient",
            patient_phone="+15555550123",
            source="oauth_integration_test",
        )
    )
    assert result.outcome == BookingOutcome.CREATED
    assert result.appointment is not None
    assert result.appointment.external_calendar_event_id
    assert calendar.check_availability(
        "clinic-owner@example.com",
        result.appointment.start_time,
        result.appointment.end_time,
    ) is False


def test_disconnect_and_cross_workspace_authorization(client, db_session, monkeypatch):
    _configure_oauth(monkeypatch)
    owner = register_and_login(client, "google-owner-a@example.com")
    workspace_id = create_workspace(client, owner, "Google A", "google-a")
    _start_connection(client, owner, workspace_id)

    outsider = register_and_login(client, "google-owner-b@example.com")
    create_workspace(client, outsider, "Google B", "google-b")
    forbidden = client.get(
        "/api/v1/integrations/google/status",
        params={"workspace_id": workspace_id},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 404

    disconnected = client.post(
        "/api/v1/integrations/google/disconnect",
        params={"workspace_id": workspace_id},
        headers=auth_headers(owner),
    )
    assert disconnected.status_code == 200
    integration = db_session.execute(
        select(Integration).where(Integration.workspace_id == workspace_id)
    ).scalar_one()
    assert integration.is_active is False
    assert integration.config == {"auth_type": "oauth", "connected_status": "disconnected"}


def test_legacy_service_account_status_remains_connected(client, db_session):
    token = register_and_login(client, "service-account-owner@example.com")
    workspace_id = create_workspace(client, token, "Legacy Clinic", "legacy-clinic")
    db_session.add(
        Integration(
            workspace_id=workspace_id,
            provider="google_calendar",
            is_active=True,
            config={"calendar_id": "legacy@example.com"},
        )
    )
    db_session.commit()
    response = client.get(
        "/api/v1/integrations/google/status",
        params={"workspace_id": workspace_id},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["auth_type"] == "service_account"
    assert response.json()["connected"] is True
