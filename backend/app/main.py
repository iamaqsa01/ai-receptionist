import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.root import router as root_router
from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging_config import setup_logging
from app.core.logging_context import get_request_id
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("%s starting up in %s mode", settings.app_name, settings.app_env)

    # Day-of appointment reminders (app/jobs/scheduler.py). Skipped under
    # pytest so the test suite never spawns a real background thread /
    # touches the configured database on import.
    reminder_scheduler_started = False
    if settings.reminders_enabled and "pytest" not in sys.modules:
        from app.jobs.scheduler import start_reminder_scheduler

        reminder_scheduler_started = start_reminder_scheduler() is not None

    yield

    if reminder_scheduler_started:
        from app.jobs.scheduler import shutdown_reminder_scheduler

        shutdown_reminder_scheduler()
    logger.info("%s shutting down", settings.app_name)


# API exposure (Phase 14): interactive docs/schema are genuinely useful in
# development but are unnecessary attack-surface/recon material once this
# is running somewhere reachable by more than its own developers — disabled
# outside development/test rather than left on by default.
_docs_enabled = not settings.is_production_like

app = FastAPI(
    title=settings.app_name,
    description="AI Receptionist backend API",
    version="0.1.0",
    debug=settings.debug,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # This API is bearer-token (Authorization header) authenticated, never
    # cookie-based — allow_credentials is what governs cross-origin
    # *cookie*/HTTP-auth-prompt sharing, so leaving it on here would only
    # relax the CORS contract for no actual benefit to this app.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# Registered after CORSMiddleware but runs first (Starlette applies
# middleware outermost-added-last), so the request ID is bound before CORS
# preflight/response handling and every downstream log line is correlated.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(BodySizeLimitMiddleware)

app.include_router(root_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("AppException on %s %s: %s", request.method, request.url.path, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "request_id": get_request_id()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": get_request_id()},
    )
