"""Per-workspace Google OAuth authorization and credential persistence."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings as default_settings
from app.core.rbac import role_allows
from app.integrations.calendar.token_crypto import decrypt_token, encrypt_token
from app.models.integration import Integration
from app.models.user import User
from app.models.workspace_member import WorkspaceMember


GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_STATE_LIFETIME_MINUTES = 10


class GoogleOAuthError(RuntimeError):
    pass


def _require_oauth_config(cfg: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("GOOGLE_CLIENT_ID", cfg.google_client_id),
            ("GOOGLE_CLIENT_SECRET", cfg.google_client_secret),
            ("GOOGLE_REDIRECT_URI", cfg.google_redirect_uri),
        )
        if not value.strip()
    ]
    if missing:
        raise GoogleOAuthError(f"Google OAuth is not configured: missing {', '.join(missing)}")


def get_google_integration(db: Session, workspace_id: uuid.UUID) -> Integration | None:
    return db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.provider == "google_calendar",
        )
    ).scalar_one_or_none()


def _get_or_create_google_integration(db: Session, workspace_id: uuid.UUID) -> Integration:
    integration = get_google_integration(db, workspace_id)
    if integration is None:
        integration = Integration(
            workspace_id=workspace_id,
            provider="google_calendar",
            config={},
            is_active=False,
        )
        db.add(integration)
        db.flush()
    return integration


def build_google_authorization_url(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    cfg: Settings | None = None,
) -> str:
    cfg = cfg or default_settings
    _require_oauth_config(cfg)

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    state_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=_STATE_LIFETIME_MINUTES)
    state = jwt.encode(
        {
            "purpose": "google_calendar_oauth",
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "jti": state_id,
            "iat": now,
            "exp": expires_at,
        },
        cfg.secret_key,
        algorithm=cfg.jwt_algorithm,
    )

    integration = _get_or_create_google_integration(db, workspace_id)
    config = dict(integration.config or {})
    config["oauth_pending"] = {
        "state_id": state_id,
        "user_id": str(user_id),
        "expires_at": expires_at.isoformat(),
        "code_verifier": encrypt_token(verifier, cfg),
    }
    config["connected_status"] = "connecting"
    integration.config = config
    db.add(integration)
    db.commit()

    return GOOGLE_AUTHORIZATION_ENDPOINT + "?" + urlencode(
        {
            "client_id": cfg.google_client_id,
            "redirect_uri": cfg.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


def _validated_pending_connection(
    db: Session, state: str, cfg: Settings
) -> tuple[Integration, dict[str, Any], uuid.UUID]:
    try:
        payload = jwt.decode(state, cfg.secret_key, algorithms=[cfg.jwt_algorithm])
        workspace_id = uuid.UUID(payload["workspace_id"])
        user_id = uuid.UUID(payload["user_id"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise GoogleOAuthError("Invalid or expired Google OAuth state") from exc
    if payload.get("purpose") != "google_calendar_oauth" or not payload.get("jti"):
        raise GoogleOAuthError("Invalid Google OAuth state")

    integration = get_google_integration(db, workspace_id)
    pending = dict((integration.config or {}).get("oauth_pending") or {}) if integration else {}
    if not integration or pending.get("state_id") != payload["jti"] or pending.get("user_id") != str(user_id):
        raise GoogleOAuthError("Google OAuth state has already been used or does not match")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise GoogleOAuthError("The user who started this connection is no longer active")
    if not user.is_super_admin:
        membership = db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).scalar_one_or_none()
        if membership is None or not role_allows(membership.role, "integrations:manage"):
            raise GoogleOAuthError("The user no longer has permission to connect this workspace")
    return integration, pending, user_id


def exchange_google_code(
    code: str, code_verifier: str, cfg: Settings, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.Client(timeout=cfg.google_calendar_timeout_seconds)
    try:
        response = client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": cfg.google_client_id,
                "client_secret": cfg.google_client_secret,
                "redirect_uri": cfg.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GoogleOAuthError("Google rejected the authorization code") from exc
    finally:
        if owns_client:
            client.close()
    if not payload.get("access_token"):
        raise GoogleOAuthError("Google token response did not include an access token")
    return payload


def fetch_google_calendar_identity(access_token: str, cfg: Settings) -> tuple[str, str]:
    import httplib2
    from google.oauth2.credentials import Credentials
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    credentials = Credentials(token=access_token, scopes=GOOGLE_CALENDAR_SCOPES)
    try:
        http = httplib2.Http(timeout=cfg.google_calendar_timeout_seconds)
        service = build(
            "calendar",
            "v3",
            http=AuthorizedHttp(credentials, http=http),
            cache_discovery=False,
        )
        entries = service.calendarList().list(maxResults=250, minAccessRole="writer").execute(num_retries=0)
    except Exception as exc:
        raise GoogleOAuthError("Connected Google account has no writable calendar access") from exc
    calendars = entries.get("items", [])
    selected = next((item for item in calendars if item.get("primary")), None)
    if selected is None and calendars:
        selected = calendars[0]
    if selected is None or not selected.get("id"):
        raise GoogleOAuthError("Connected Google account has no writable calendar")
    return str(selected["id"]), str(selected.get("summaryOverride") or selected.get("summary") or selected["id"])


def complete_google_oauth(
    db: Session,
    *,
    code: str,
    state: str,
    cfg: Settings | None = None,
) -> Integration:
    cfg = cfg or default_settings
    _require_oauth_config(cfg)
    integration, pending, user_id = _validated_pending_connection(db, state, cfg)
    verifier = decrypt_token(pending.get("code_verifier", ""), cfg)
    token_data = exchange_google_code(code, verifier, cfg)

    refresh_token = token_data.get("refresh_token")
    if not refresh_token and (integration.config or {}).get("auth_type") == "oauth":
        refresh_token = decrypt_token((integration.config or {}).get("refresh_token", ""), cfg)
    if not refresh_token:
        raise GoogleOAuthError("Google did not issue a refresh token; reconnect and grant consent")

    calendar_id, calendar_name = fetch_google_calendar_identity(token_data["access_token"], cfg)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    integration.config = {
        "auth_type": "oauth",
        "connected_status": "connected",
        "access_token": encrypt_token(token_data["access_token"], cfg),
        "refresh_token": encrypt_token(refresh_token, cfg),
        "token_expiry": expires_at.isoformat(),
        "calendar_id": calendar_id,
        "calendar_name": calendar_name,
        "scopes": token_data.get("scope", " ".join(GOOGLE_CALENDAR_SCOPES)).split(),
        "connected_by_user_id": str(user_id),
    }
    integration.is_active = True
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def google_integration_status(db: Session, workspace_id: uuid.UUID) -> dict[str, Any]:
    integration = get_google_integration(db, workspace_id)
    if integration is None:
        return {"connected": False, "status": "disconnected", "auth_type": None, "calendar_id": None, "calendar_name": None}
    config = integration.config or {}
    auth_type = config.get("auth_type") or ("service_account" if integration.is_active else None)
    pending = bool(config.get("oauth_pending"))
    connected = bool(integration.is_active and (auth_type == "service_account" or config.get("connected_status") == "connected"))
    status = "connecting" if pending and not connected else ("connected" if connected else config.get("connected_status", "disconnected"))
    if status not in {"connected", "connecting", "disconnected", "error"}:
        status = "disconnected"
    return {
        "connected": connected,
        "status": status,
        "auth_type": auth_type,
        "calendar_id": config.get("calendar_id"),
        "calendar_name": config.get("calendar_name") or config.get("calendar_id"),
    }


def disconnect_google_integration(db: Session, workspace_id: uuid.UUID) -> None:
    integration = get_google_integration(db, workspace_id)
    if integration is None:
        return
    integration.config = {"auth_type": "oauth", "connected_status": "disconnected"}
    integration.is_active = False
    db.add(integration)
    db.commit()
