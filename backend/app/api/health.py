import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.schemas.health import HealthResponse, ReadinessCheck, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe: "is the process up and able to answer HTTP requests
    at all". Deliberately touches no dependency (no DB, no external
    provider) — a load balancer/orchestrator should restart the process
    only when *the process itself* is wedged, not because Postgres had a
    momentary blip (that's what /health/ready is for)."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env,
        version="0.1.0",
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check(response: Response, db: Session = Depends(get_db)) -> ReadinessResponse:
    """Readiness probe: "is this instance actually able to serve real
    traffic right now". Checks the one hard dependency every request in
    this app needs (the database). Returns 200 when every check passes,
    503 otherwise — the shape orchestrators (Kubernetes, ECS, App
    Platform's health checks, a load balancer's target group) expect to
    pull an unready instance out of rotation without restarting it."""
    checks = [_check_database(db)]
    overall_ok = all(check.status == "ok" for check in checks)
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if overall_ok else "error", checks=checks)


def _check_database(db: Session) -> ReadinessCheck:
    try:
        db.execute(text("SELECT 1"))
        return ReadinessCheck(name="database", status="ok")
    except Exception as exc:
        logger.error("readiness check: database unreachable: %s", exc, exc_info=True)
        return ReadinessCheck(name="database", status="error", detail="database unreachable")
