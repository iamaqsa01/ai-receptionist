from typing import Literal

from pydantic import BaseModel


class GoogleConnectResponse(BaseModel):
    authorization_url: str


class GoogleIntegrationStatus(BaseModel):
    connected: bool
    status: Literal["connected", "connecting", "disconnected", "error"]
    auth_type: Literal["oauth", "service_account"] | None = None
    calendar_id: str | None = None
    calendar_name: str | None = None


class GoogleDisconnectResponse(BaseModel):
    disconnected: bool = True
