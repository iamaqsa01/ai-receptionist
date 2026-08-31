import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings as default_settings
from app.integrations.calendar.base import CalendarProvider
from app.integrations.calendar.mock_provider import default_mock_calendar_provider
from app.integrations.calendar.token_crypto import TokenDecryptionError, decrypt_token, encrypt_token
from app.models.integration import Integration

logger = logging.getLogger(__name__)


def get_calendar_provider(cfg: Settings | None = None) -> CalendarProvider:
    cfg = cfg or default_settings
    provider_name = cfg.calendar_provider.lower().strip()

    if provider_name == "google":
        from app.integrations.calendar.google_provider import GoogleCalendarProvider

        service_account_info = None
        if cfg.google_service_account_json:
            try:
                service_account_info = json.loads(cfg.google_service_account_json)
            except (TypeError, ValueError):
                logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON; falling back to mock calendar")

        provider = GoogleCalendarProvider(service_account_info, timeout_seconds=cfg.google_calendar_timeout_seconds)
        if provider.is_available():
            return provider
        logger.warning(
            "CALENDAR_PROVIDER=google but GOOGLE_SERVICE_ACCOUNT_JSON is missing/invalid; "
            "falling back to mock calendar"
        )
        return default_mock_calendar_provider

    return default_mock_calendar_provider


def get_calendar_provider_for_workspace(
    db: Session,
    workspace_id: uuid.UUID,
    cfg: Settings | None = None,
) -> CalendarProvider:
    """Prefer this workspace's OAuth grant; otherwise retain global provider behavior."""
    cfg = cfg or default_settings
    integration = db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.provider == "google_calendar",
            Integration.is_active.is_(True),
        )
    ).scalar_one_or_none()
    config = integration.config if integration is not None else {}
    if integration is None or config.get("auth_type") != "oauth":
        return get_calendar_provider(cfg)

    from app.integrations.calendar.google_provider import GoogleOAuthCalendarProvider

    try:
        access_token = decrypt_token(config.get("access_token", ""), cfg)
        refresh_token = decrypt_token(config.get("refresh_token", ""), cfg)
    except TokenDecryptionError:
        logger.exception("workspace_id=%s has unreadable Google OAuth credentials", workspace_id)
        access_token = None
        refresh_token = None

    expiry = None
    if config.get("token_expiry"):
        try:
            expiry = datetime.fromisoformat(config["token_expiry"].replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry.utcoffset() is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            logger.warning("workspace_id=%s has an invalid Google OAuth token expiry", workspace_id)

    def persist_refreshed_credentials(token: str, token_expiry: datetime | None) -> None:
        latest = dict(integration.config or {})
        latest["access_token"] = encrypt_token(token, cfg)
        latest["token_expiry"] = token_expiry.isoformat() if token_expiry else None
        latest["connected_status"] = "connected"
        integration.config = latest
        db.add(integration)
        db.commit()

    return GoogleOAuthCalendarProvider(
        access_token=access_token,
        refresh_token=refresh_token,
        token_expiry=expiry,
        client_id=cfg.google_client_id,
        client_secret=cfg.google_client_secret,
        timeout_seconds=cfg.google_calendar_timeout_seconds,
        on_credentials_updated=persist_refreshed_credentials,
    )
