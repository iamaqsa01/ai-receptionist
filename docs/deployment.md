# Deployment Guide

Phase 16 — production readiness. This document covers what's needed to actually run this system
somewhere other than a developer's laptop: configuration, migrations, health checks, logging,
Docker, and concrete deployment paths for the backend (AWS / GCP / DigitalOcean) and frontend
(Vercel / Netlify). Nothing in this repository deploys automatically — every command below is
something a human runs deliberately.

**No healthcare regulatory compliance (HIPAA or otherwise) is implemented or claimed.** This guide
gets the application running securely and reliably; it is not a compliance program. See
[Phase 14's security audit](../README.md#phase-14--security-audit) for exactly what was and wasn't
addressed.

## Contents

- [Prerequisites](#prerequisites)
- [Environment variables](#environment-variables)
- [Migration instructions](#migration-instructions)
- [Health checks](#health-checks)
- [Production logging](#production-logging)
- [Docker](#docker)
- [Backend deployment](#backend-deployment)
- [Frontend deployment](#frontend-deployment)
- [Verify the production build locally](#verify-the-production-build-locally)
- [Production checklist](#production-checklist)
- [Rollback](#rollback)

## Prerequisites

- A PostgreSQL 14+ database (managed is strongly recommended — RDS / Cloud SQL / DigitalOcean
  Managed Databases; SQLite is dev/test-only and is what the test suite runs against, never use it
  in production).
- A real `SECRET_KEY` — the app **refuses to start** without one once `APP_ENV` isn't
  `development`/`test`/`local` (see [Phase 14](../README.md#phase-14--security-audit)). Generate
  one with:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- Whichever third-party provider credentials you intend to use for real (Twilio, OpenAI/Anthropic,
  Deepgram, ElevenLabs, Google Calendar, WhatsApp, SendGrid). None are required to boot the
  app — every provider falls back to a deterministic mock adapter when its credentials are
  missing, the same pattern used throughout local development and the test suite. Ship with mocks
  first, add real credentials provider-by-provider once each is actually ready.

## Environment variables

`backend/.env.example` is the single source of truth — every variable the app reads is listed
there with an inline comment. Copy it to `.env` (or your platform's equivalent secret/env store)
and fill in real values. The ones that matter most for a production deployment specifically:

| Variable | Production value |
|---|---|
| `APP_ENV` | `production` (anything outside `development`/`dev`/`test`/`testing`/`local` enables the production-mode checks below) |
| `SECRET_KEY` | A real generated secret — **the app will not start without one** in this mode |
| `DEBUG` | `false` (this is now the default — see Phase 14) |
| `DATABASE_URL` | Your managed Postgres connection string (or the discrete `POSTGRES_*` vars) |
| `CORS_ORIGINS` | Your deployed frontend's exact origin(s), comma-separated — e.g. `https://your-app.vercel.app` |
| `LOG_FORMAT` | `json` (default — see [Production logging](#production-logging)) |
| `LOG_LEVEL` | `INFO` (or `WARNING` once the deployment is stable) |

In this mode, `APP_ENV=production` also disables `/docs`, `/redoc`, and `/openapi.json`, and
disallows the insecure default `SECRET_KEY` — both enforced at startup, not just documented.

## Migration instructions

Migrations are **never** run automatically by the app or the container start command — they're a
deliberate, separate step, run once per deployed schema change:

```bash
cd backend
alembic upgrade head
```

Run this:
- Against the target database, with `DATABASE_URL` (or `POSTGRES_*`) pointing at it.
- **Before** rolling out a new backend version that depends on the new schema, and after any
  version that depended on the *old* schema has been fully drained (standard rolling-deploy
  ordering — this project's migrations are additive-only so far, see below).
- From wherever you already run one-off admin commands for your platform: `docker compose exec
  backend alembic upgrade head`, an ECS one-off task, a Cloud Run job, a DigitalOcean App Platform
  console command, or straight from a machine with network access to the DB and the same
  `requirements.txt` installed.

Check the current/available revisions without applying anything:

```bash
alembic current
alembic history
```

Every migration in `backend/alembic/versions/` so far only adds tables/columns — none drop or
rename anything — so applying them is safe to do ahead of a deploy without breaking the
still-running previous version. If a future migration ever needs to drop/rename a column, do it in
two deploys (add the new shape, migrate reads/writes, then a later migration removes the old
shape) rather than one — this project hasn't needed that yet, but plan for it.

## Health checks

Two endpoints, deliberately different in what they check (see `app/api/health.py`):

- **`GET /api/v1/health`** — liveness. Touches no dependency (no DB, no provider) — only fails if
  the process itself is wedged. Point your orchestrator's liveness probe / restart policy here.
- **`GET /api/v1/health/ready`** — readiness. Checks the database is actually reachable
  (`SELECT 1`), returns `200` with `{"status": "ok", "checks": [...]}` when healthy or `503` with
  `{"status": "error", ...}` otherwise. Point your load balancer's target-group health check /
  orchestrator's readiness probe here — this is what should pull an instance out of rotation during
  a DB blip without restarting it.

Both are unauthenticated (health checks can't log in) and return no sensitive information.

## Production logging

Structured JSON logs are the default (`LOG_FORMAT=json`, set in Phase 13) — one JSON object per
line to stdout, with `timestamp`, `level`, `logger`, `message`, and whichever of `request_id` /
`workspace_id` / `call_id` are bound for that log line (see `app/core/logging_context.py`). Every
HTTP request also gets a structured summary line (method, path, status, duration) from
`RequestContextMiddleware`, and the response carries the same `X-Request-ID` header — hand a user
their request ID and you can find the exact log lines for their request.

This is already in the shape most log aggregation platforms expect out of the box — CloudWatch
Logs, Google Cloud Logging, and DigitalOcean's log forwarding all ingest JSON-lines-on-stdout
without extra configuration; just point the platform's log driver at the container's stdout (the
default in every deployment path below). `LOG_FORMAT=text` remains available for local dev tailing
readability, but should not be used in production — it's harder to query/alert on.

## Docker

`backend/Dockerfile` builds a production image: `python:3.12-slim`, non-root user, a container
`HEALTHCHECK` against `/api/v1/health`, and `gunicorn` managing a pool of `uvicorn` worker
processes (the standard production ASGI process model — a bare `uvicorn` process only uses one CPU
core and has no worker-restart supervision, fine for local dev, not for production).

```bash
cd backend
docker build -t ai-receptionist-backend .
docker run --env-file .env -p 8000:8000 ai-receptionist-backend
```

`WEB_CONCURRENCY` (default `2` in the image) sets the gunicorn worker count — size it to the host's
CPU count (a common starting point is `2 × cores + 1`), e.g.:

```bash
docker run --env-file .env -e WEB_CONCURRENCY=4 -p 8000:8000 ai-receptionist-backend
```

The repo-root `docker-compose.yml` wires this image up with a real Postgres container for local
verification (see [Verify the production build locally](#verify-the-production-build-locally)) —
it is not itself a deployment target; use it to prove the image works before shipping it to one of
the platforms below.

## Backend deployment

The backend is a standard containerized ASGI app with one hard dependency (Postgres) — any
container-hosting platform works. Three concrete paths:

### DigitalOcean (App Platform)

The simplest of the three — App Platform builds directly from `backend/Dockerfile`.

1. Create a Managed PostgreSQL database (DigitalOcean → Databases). Note its connection string.
2. App Platform → Create App → point at this repo, source directory `backend/`. App Platform
   detects the `Dockerfile` automatically.
3. Set environment variables (App Platform's "Environment Variables" panel, marked "Encrypted" for
   secrets) from the table above — `DATABASE_URL` from step 1, a generated `SECRET_KEY`,
   `APP_ENV=production`, `CORS_ORIGINS` set once you know the frontend's URL.
4. Health check: App Platform's HTTP health check path → `/api/v1/health/ready`.
5. Deploy. Then run migrations once via `doctl apps console` (or App Platform's console tab)
   against the running container: `alembic upgrade head`.

### AWS (App Runner + RDS)

App Runner is the closest AWS equivalent to App Platform — it builds/runs a container without
needing to hand-configure ECS/ALB/VPC networking for a first deployment (a full ECS Fargate +
Application Load Balancer + RDS setup is the natural next step once this outgrows App Runner, but
is materially more setup for the same result).

1. Create an RDS PostgreSQL instance (or Aurora Postgres). Put it in a VPC App Runner can reach
   (App Runner's VPC connector, if the DB isn't publicly reachable).
2. Push the image to ECR: `aws ecr create-repository --repository-name ai-receptionist-backend`,
   then `docker build`, `docker tag`, `docker push` per ECR's own push commands.
3. App Runner → Create service → source: the ECR image. Port `8000`.
4. Environment variables: same table as above, via App Runner's configuration (use AWS Secrets
   Manager for `SECRET_KEY`/`DATABASE_URL` and reference them, rather than plaintext env vars, once
   this is truly production).
5. Health check: App Runner's health check path → `/api/v1/health/ready`.
6. Deploy. Run migrations via `aws ecs run-task` (if fronted by ECS) or a one-off `docker run`
   against the same image with the production `DATABASE_URL`, from a machine/bastion with network
   access to RDS.

### GCP (Cloud Run + Cloud SQL)

Cloud Run is a natural fit — it's built around exactly this shape (stateless container, one
external dependency).

1. Create a Cloud SQL for PostgreSQL instance.
2. `gcloud builds submit --tag gcr.io/PROJECT_ID/ai-receptionist-backend backend/` (or push to
   Artifact Registry).
3. `gcloud run deploy ai-receptionist-backend --image gcr.io/PROJECT_ID/ai-receptionist-backend
   --add-cloudsql-instances PROJECT_ID:REGION:INSTANCE --port 8000`
4. Environment variables: `gcloud run services update ... --set-env-vars` or (preferred for
   secrets) `--set-secrets` against Secret Manager. `DATABASE_URL` uses Cloud SQL's Unix-socket
   connection form when using `--add-cloudsql-instances`; see Cloud Run's Cloud SQL docs for the
   exact DSN shape.
5. Health check: Cloud Run infers liveness from the container serving traffic; explicitly configure
   a startup/liveness probe against `/api/v1/health` in the service YAML if you want the same
   behavior as the other two platforms.
6. Deploy. Run migrations via `gcloud run jobs` (a one-off job using the same image and
   `alembic upgrade head` as its command) or `gcloud sql connect` + running it from a workstation.

All three: set `WEB_CONCURRENCY` to match the instance's CPU allocation, and start with the
platform's smallest instance size — this app has no heavy compute of its own (LLM/STT/TTS calls are
all outbound to third-party APIs), so it's I/O-bound, not CPU-bound, until real call volume says
otherwise.

## Frontend deployment

`frontend/` is static HTML/CSS/JS with **no build step** — this makes Vercel/Netlify configuration
almost trivial, but it also means the one thing a build step would normally inject (the backend's
URL) has to be edited by hand instead. See `frontend/js/config.js` (added this phase specifically
for this):

```js
window.__AI_RECEPTIONIST_CONFIG__ = {
  API_BASE_URL: "https://your-backend.example.com/api/v1",
};
```

Before deploying, also update the CSP `connect-src` in `frontend/index.html`'s `<meta
http-equiv="Content-Security-Policy">` tag to include that same backend URL — the page's own CSP
(Phase 14) will otherwise silently block every API call to it. Both are marked in each file with a
`Phase 16` comment.

### Vercel

1. Import the repo. Framework preset: "Other" (no build detected, which is correct — there isn't
   one). Root directory: `frontend/`.
2. Build command: none / leave empty. Output directory: `frontend/` itself (Vercel serves it as a
   static site).
3. Deploy. Then set `CORS_ORIGINS` on the **backend** to include the Vercel-assigned URL (and any
   custom domain), and redeploy the backend for that to take effect.

### Netlify

1. Import the repo. Base directory: `frontend/`. Build command: none. Publish directory: `frontend`
   (relative to the base directory, i.e. the repo's `frontend/` folder itself — there's nothing to
   build into a separate `dist/`).
2. Deploy. Same CORS step as Vercel above.

### Any static host (equivalent path)

Since there's no build step, this also works unmodified on S3+CloudFront, Cloudflare Pages, GitHub
Pages, or literally `python -m http.server` behind any reverse proxy — copy `frontend/`'s contents
to wherever static files get served from, after editing `config.js` and the CSP as above.

## Verify the production build locally

Before shipping any of the above, prove the app actually behaves correctly under production-mode
settings, on this machine. Two levels, depending on what's available to you:

**With a working Docker daemon** (the full stack — this is the path to actually prove the
Dockerfile/gunicorn/Postgres combination works together, and the recommended one wherever Docker is
available):

```bash
cd "AI RECEPTIONIST"
cp backend/.env.example backend/.env.docker
# edit backend/.env.docker: set APP_ENV=production and a real SECRET_KEY
# (python -c "import secrets; print(secrets.token_urlsafe(48))")
echo -e "POSTGRES_USER=postgres\nPOSTGRES_PASSWORD=<pick-one>\nPOSTGRES_DB=ai_receptionist" > .env

docker compose up --build -d
docker compose exec backend alembic upgrade head

curl -s http://localhost:8000/api/v1/health          # liveness
curl -s http://localhost:8000/api/v1/health/ready     # readiness — should report the DB as "ok"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs   # 404 — confirms prod-mode doc-hiding is active

# Frontend (nginx container, see docker-compose.yml) at http://localhost:5500 —
# edit frontend/js/config.js's API_BASE_URL to http://localhost:8000/api/v1
# (already the default) and the CSP connect-src to match before testing this leg.

docker compose down -v   # tear down, including the Postgres volume, when done
```

**Without Docker available** (what was actually run while writing this phase — the sandbox this was
built in had a Docker Desktop installed but its engine was unresponsive, `docker info` timed out
rather than erroring cleanly): the same production settings and the same app code path can be
verified directly, just without gunicorn itself (which is Linux/POSIX-only — `fcntl` isn't
available on Windows — so this substitutes `uvicorn --workers N`, which the Dockerfile's `CMD`
delegates to *inside* gunicorn's process manager anyway) and with SQLite substituting for Postgres:

```bash
cd backend
DATABASE_URL="sqlite:///./prodverify.db" alembic upgrade head

APP_ENV=production \
SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
DEBUG=false \
DATABASE_URL="sqlite:///./prodverify.db" \
CORS_ORIGINS="http://localhost:5500" \
LOG_FORMAT=json \
uvicorn app.main:app --workers 2 --host 127.0.0.1 --port 8020
```

This was run exactly as shown, and confirmed: the app **refuses to start** with the default
`SECRET_KEY` once `APP_ENV=production` (tested separately — see Phase 14); with a real one, it
starts multi-worker successfully; `/api/v1/health` returns `{"status": "ok", ..., "app_env":
"production"}`; `/api/v1/health/ready` returns `{"status": "ok", "checks": [{"name": "database",
"status": "ok", ...}]}`; `/docs` and `/openapi.json` both return `404`; every response carries a
unique `X-Request-ID` header; and a full register → login round-trip produces exactly the expected
structured JSON log lines (a `app.request` line per HTTP request with method/path/status/duration,
an `app.audit` line for `user.registered`/`user.login`), matching Phase 13's structured-logging
design and this document's [Production logging](#production-logging) section above.

What this substitution does **not** prove: the actual `Dockerfile`/gunicorn combination, or
behavior against real Postgres specifically (SQLite's own quirks are called out throughout this
codebase — e.g. dropping timezone info on round-trip — and are the reason the test suite already
runs against SQLite while production always targets Postgres). Run the Docker path above at least
once, in an environment with a working Docker daemon, before a first real deployment.

## Production checklist

- [ ] `SECRET_KEY` is a real generated secret, stored as a platform secret (not committed, not a
      plaintext env var if the platform offers a secrets manager)
- [ ] `APP_ENV=production`
- [ ] `DATABASE_URL` points at a managed Postgres instance, not SQLite
- [ ] `CORS_ORIGINS` lists the deployed frontend's exact origin(s) — not `*`, not localhost
- [ ] `alembic upgrade head` has been run against the production database
- [ ] `frontend/js/config.js`'s `API_BASE_URL` and `frontend/index.html`'s CSP `connect-src` both
      point at the real backend URL
- [ ] `/api/v1/health/ready` returns `200` against the production database
- [ ] `/docs`, `/redoc`, `/openapi.json` all return `404`
- [ ] Real provider credentials are set for whichever integrations you're actually using (Twilio,
      LLM, STT/TTS, calendar, WhatsApp/email) — anything left unset falls back to its mock adapter,
      which is safe but silently non-functional for real traffic
- [ ] Rate limiting (`app/core/rate_limit.py`) is understood to be per-process, not distributed —
      if you're running more than one backend instance, its effective limit is N× the configured
      value; that's an accepted, documented limitation (see Phase 14), not a bug

## Rollback

There's no automated rollback tooling here — this is a manual runbook, matching "do not deploy
automatically":

1. **Application code**: redeploy the previous container image/version through whichever platform
   mechanism above you used (App Platform/App Runner/Cloud Run all keep prior revisions and support
   redeploying one directly).
2. **Database schema**: only relevant if the version being rolled back *from* had already run a new
   migration. Since every migration so far is additive-only (new tables/columns, nothing dropped or
   renamed), the previous application version keeps working against the *new* schema unmodified —
   there is usually nothing to revert. If a future migration ever needs `alembic downgrade
   <revision>`, treat that as an explicit, deliberate step taken only after confirming no
   already-written data depends on the column/table being removed.
