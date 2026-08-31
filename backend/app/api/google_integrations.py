import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import TenantContext, require_permission
from app.database.session import get_db
from app.integrations.calendar.oauth import (
    GoogleOAuthError,
    build_google_authorization_url,
    complete_google_oauth,
    disconnect_google_integration,
    google_integration_status,
)
from app.schemas.google_integration import (
    GoogleConnectResponse,
    GoogleDisconnectResponse,
    GoogleIntegrationStatus,
)


router = APIRouter(prefix="/integrations/google", tags=["google-calendar-integration"])


@router.get("/connect", response_model=GoogleConnectResponse)
def connect_google_calendar(
    workspace_id: uuid.UUID = Query(...),
    ctx: TenantContext = Depends(require_permission("integrations:manage")),
    db: Session = Depends(get_db),
) -> GoogleConnectResponse:
    try:
        authorization_url = build_google_authorization_url(
            db,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user.id,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return GoogleConnectResponse(authorization_url=authorization_url)


@router.get("/callback", response_class=HTMLResponse)
def google_oauth_callback(
    code: str | None = Query(default=None),
    state_token: str | None = Query(default=None, alias="state"),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if error or not code or not state_token:
        return _callback_page(False, "Google Calendar connection was cancelled or denied.", status.HTTP_400_BAD_REQUEST)
    try:
        complete_google_oauth(db, code=code, state=state_token)
    except GoogleOAuthError as exc:
        return _callback_page(False, str(exc), status.HTTP_400_BAD_REQUEST)
    return _callback_page(True, "Google Calendar connected successfully.", status.HTTP_200_OK)


@router.get("/status", response_model=GoogleIntegrationStatus)
def get_google_calendar_status(
    workspace_id: uuid.UUID = Query(...),
    ctx: TenantContext = Depends(require_permission("integrations:read")),
    db: Session = Depends(get_db),
) -> GoogleIntegrationStatus:
    return GoogleIntegrationStatus(**google_integration_status(db, ctx.workspace_id))


@router.post("/disconnect", response_model=GoogleDisconnectResponse)
def disconnect_google_calendar(
    workspace_id: uuid.UUID = Query(...),
    ctx: TenantContext = Depends(require_permission("integrations:manage")),
    db: Session = Depends(get_db),
) -> GoogleDisconnectResponse:
    disconnect_google_integration(db, ctx.workspace_id)
    return GoogleDisconnectResponse()


def _callback_page(success: bool, message: str, status_code: int) -> HTMLResponse:
    tone = "#166534" if success else "#991b1b"
    title = "Connected" if success else "Connection failed"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Google Calendar {title}</title></head>
<body style="font-family:system-ui,sans-serif;padding:40px;text-align:center;color:#172033">
<h1 style="color:{tone}">{title}</h1><p>{message}</p><p>You may close this window.</p>
<script>if(window.opener){{window.opener.postMessage({{"type":"google-calendar-oauth","success":{str(success).lower()}}}, window.location.origin);setTimeout(()=>window.close(),700);}}</script>
</body></html>"""
    return HTMLResponse(html, status_code=status_code, headers={"Cache-Control": "no-store"})
