import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, status

from app.core.config import settings

_TOKEN_TYPE = "vapi_availability"


@dataclass(frozen=True)
class AvailabilityTokenData:
    workspace_id: uuid.UUID
    service_id: uuid.UUID
    provider_id: uuid.UUID
    start_time: datetime
    end_time: datetime


def verify_vapi_tool_request(authorization: str | None = Header(default=None)) -> None:
    configured = settings.vapi_tool_webhook_secret
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vapi tool authentication is not configured",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Vapi tool credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_availability_token(
    *,
    workspace_id: uuid.UUID,
    service_id: uuid.UUID,
    provider_id: uuid.UUID,
    start_time: datetime,
    end_time: datetime,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": _TOKEN_TYPE,
        "jti": str(uuid.uuid4()),
        "workspace_id": str(workspace_id),
        "service_id": str(service_id),
        "provider_id": str(provider_id),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "iat": now,
        "exp": now + timedelta(seconds=settings.vapi_availability_token_expire_seconds),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_availability_token(token: str) -> AvailabilityTokenData:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != _TOKEN_TYPE:
            raise jwt.InvalidTokenError("wrong token type")
        return AvailabilityTokenData(
            workspace_id=uuid.UUID(payload["workspace_id"]),
            service_id=uuid.UUID(payload["service_id"]),
            provider_id=uuid.UUID(payload["provider_id"]),
            start_time=datetime.fromisoformat(payload["start_time"]),
            end_time=datetime.fromisoformat(payload["end_time"]),
        )
    except (KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
        raise ValueError("Invalid or expired availability token") from exc

