# Production image for the AI Receptionist backend (FastAPI).
#
# Build:  docker build -t ai-receptionist-backend .
# Run:    docker run --env-file .env -p 8000:8000 ai-receptionist-backend
#
# Migrations are NOT applied automatically on container start (see
# docs/deployment.md — "Migration instructions") — run
# `alembic upgrade head` as a separate, explicit step (a one-off task/job)
# before rolling out a new version, the same way any stateful-schema change
# should be applied: deliberately, not as a side effect of a process
# restarting.

FROM python:3.12-slim AS base

# Keeps python from writing .pyc files / buffering stdout — the latter
# matters for this app specifically, since structured logs (Phase 13) are
# only useful if they actually reach the container's log stream promptly.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed to build psycopg2-binary's transitive requirements on
# a slim base image; removed from the final layer via apt cleanup.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Runs as a non-root user — standard container hardening, not specific to
# this app, but cheap and worth doing.
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

# Container-level liveness check (independent of whatever orchestrator
# health-check config is layered on top in AWS/GCP/DigitalOcean — see
# docs/deployment.md): curl the liveness endpoint, which touches no
# dependency, so this only fails if the process itself is wedged.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# gunicorn manages a pool of uvicorn worker processes — the standard
# production process model for an ASGI app (a single uvicorn process is
# fine for local dev, but doesn't use more than one CPU core and has no
# worker-restart supervision). WEB_CONCURRENCY overrides the worker count
# (default below assumes a small instance; size it to the host's CPU count
# in real deployments — see docs/deployment.md).
ENV WEB_CONCURRENCY=2
CMD ["sh", "-c", "gunicorn app.main:app --workers ${WEB_CONCURRENCY} --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --access-logfile - --error-logfile -"]
