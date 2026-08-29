# AI Receptionist

An AI-powered virtual receptionist system. This repository is being built in phases.

## Phase 1 — Project Scaffold

Phase 1 establishes the project skeleton only:

- FastAPI backend with configuration, CORS, logging, global error handling, and a health endpoint.
- Vanilla HTML/CSS/JS frontend shell with a landing/dashboard page.
- No database, authentication, AI, telephony, appointments, or notifications yet — those arrive in later phases.

## Phase 2 — Database Layer

Phase 2 adds the persistence layer on top of Phase 1:

- PostgreSQL + SQLAlchemy 2.0 (declarative, typed `Mapped[...]` models) + Alembic migrations.
- Models: `users`, `workspaces`, `workspace_members`, `patients`, `leads`, `calls`,
  `call_transcripts`, `call_summaries`, `appointments`, `providers`, `services`,
  `business_hours`, `ai_agents`, `integrations`, `notifications`, `audit_logs`.
- UUID primary keys, foreign keys with sensible `ON DELETE` behavior, indexes on FKs and
  commonly-filtered columns, `created_at`/`updated_at` timestamps, and a `workspace_id` on every
  tenant-owned table for multi-tenancy.
- `app/database/session.py` provides the SQLAlchemy engine, `SessionLocal`, and a `get_db()`
  FastAPI dependency.
- No authentication or AI logic — this phase is schema and session plumbing only.

## Phase 3 — Authentication, RBAC & Multi-Tenancy

- JWT bearer-token auth (`app/core/security.py`) with bcrypt password hashing. Every issued
  token is also tracked in an `auth_sessions` table so **logout actually revokes it** — it isn't
  just a client-side "forget the token".
- Endpoints: `POST /api/v1/auth/register`, `/login`, `/logout`, `GET /auth/me`.
- Workspace creation (`POST /api/v1/workspaces`) and membership management
  (`GET/POST /api/v1/workspaces/{id}/members`) — the creator becomes that workspace's Owner.
- Five roles: **Super Admin** (platform-wide, `User.is_super_admin`, bypasses membership checks),
  **Owner**, **Admin**, **Receptionist**, **Analyst** (workspace-scoped, `WorkspaceMember.role`).
  Permission matrix lives in `app/core/rbac.py`.
- Tenant access validation (`app/api/deps.py: get_tenant_context` / `require_permission`): every
  request to a workspace-scoped route resolves the caller's membership in that specific
  workspace and 404s (not 403, to avoid confirming the workspace exists) if they're not a
  member. Every resource query is additionally filtered by `workspace_id` at the DB level, so a
  guessed ID from another tenant can never be returned.
- Tenant-scoped resource endpoints demonstrating the pattern across every required resource
  type: `patients`, `leads`, `appointments`, `calls` (+ `transcripts`), and workspace `settings`
  (`GET/PATCH /workspaces/{id}`) — all under `/api/v1/workspaces/{workspace_id}/...`.
- No AI or telephony logic.

## Phase 4 — Core AI Receptionist Service

- Conversation engine (`app/ai/conversation/engine.py`): tracks per-call state (language, caller
  info, appointment draft, missing fields, status) and history, detects intent, extracts
  entities, and routes to booking / cancellation / reschedule / human-transfer handling, asking
  for missing information one field at a time.
- Intent detection + entity extraction (`app/ai/nlu/`): a fast, deterministic, multilingual
  rule-based classifier runs first (works identically offline/in tests); a real, available LLM
  provider additionally refines the intent via a structured JSON completion, with the rule-based
  result kept as a safe fallback if that fails. Names/phones/dates are extracted with
  `phonenumbers` and `dateparser` (multilingual, structured, and normalized — a phone always
  comes out as E.164, dates as real `datetime` objects — regardless of the language spoken).
- **Multilingual by design**: `app/ai/language/` detects the caller's language per turn
  (`langdetect`) and renders every reply from a localized template catalog (English, Spanish,
  French, German out of the box). Adding a language is calling `register_language()` once — no
  engine/NLU code changes. Low-confidence input asks the caller to repeat (then offers a human
  transfer); a confidently-detected but unsupported language lists what *is* supported and offers
  transfer. A language, once established, only switches on a high-confidence signal from a
  substantial message — not on the routine ambiguity of short slot-filling answers ("Cleaning",
  a phone number), which a statistical detector otherwise misreads constantly.
- **Workspace-specific instructions**: each workspace's `ai_agents.config` supplies its own
  persona/instructions, supported-language list, and (via `services`) its own service menu — no
  code change needed per clinic.
- **LLM abstraction** (`app/ai/llm/`): OpenAI and Anthropic providers behind one `LLMProvider`
  interface; business logic (NLU, conversation engine) only ever depends on that interface, never
  a provider SDK directly. No API credentials configured → automatic, deterministic **mock mode**
  (default), so the whole thing runs and tests without any external service.
- **Safety guardrail**: a fixed system instruction plus a keyword-based filter refuse
  diagnosis/prescription/clinical-decision requests in every supported language and offer a
  human transfer instead — applied both to classifying the caller's request and, defense in
  depth, to anything the LLM generates.
- Effects (booking/cancelling/rescheduling an appointment, raising a human-transfer notification)
  are applied by `app/ai/receptionist_service.py` against the existing Patient/Appointment/
  Notification tables, fully tenant-scoped (reuses the Phase 3 pattern) — the conversation engine
  itself never touches the database, which is what makes it testable with pure in-memory
  "simulated conversations."
- Thin API for driving/testing sessions: `POST/GET /api/v1/workspaces/{id}/ai/sessions[/...]`.
- Does **not** diagnose, prescribe, or make clinical decisions — administrative tasks only.

## Phase 5 — Real-Time Voice Pipeline

Wires the Phase 4 AI Receptionist into an actual phone call:

```
Caller → Twilio/Vapi → WebSocket → FastAPI → Deepgram STT → AI Receptionist → ElevenLabs TTS → Twilio/Vapi → Caller
```

- **Telephony adapters** (`app/telephony/providers/`): `TelephonyAdapter` interface with Twilio
  Media Streams, a best-effort Vapi adapter, and a mock adapter (own JSON protocol, used
  automatically without credentials). Twilio's adapter also validates `X-Twilio-Signature` on the
  initial voice webhook and builds the TwiML that opens the Media Stream.
- **WebSocket endpoint**: `WS /api/v1/telephony/stream/{provider}/{workspace_id}` — one connection
  per call. `POST /api/v1/telephony/twilio/{workspace_id}/voice` is Twilio's HTTP entry point,
  returning TwiML pointing at that WebSocket. Not authenticated (real callers don't log in);
  `workspace_id` existence is still validated.
- **Streaming audio**: inbound audio chunks stream in over the socket and are forwarded live to
  the STT provider as they arrive — no buffering the whole utterance first.
- **STT/TTS adapters** (`app/ai/speech/`): `SpeechToTextProvider`/`TextToSpeechProvider`
  interfaces; Deepgram (live websocket) and ElevenLabs (telephony-ready `ulaw_8000` REST output)
  behind them, each with an automatic mock fallback (`MockSTTProvider` decodes "audio" bytes
  straight back to text; `MockTTSProvider` "synthesizes" text straight back to bytes) — this is
  what makes the whole pipeline runnable and testable without any audio codec or network call.
- **LLM adapter**: reused as-is from Phase 4 (OpenAI/Anthropic behind `LLMProvider`, mock
  fallback) — no changes needed to wire it into the live pipeline.
- **Conversation state & call ID**: `CallSession` (`app/telephony/session.py`) orchestrates one
  call — parses events, feeds STT, calls the AI Receptionist, synthesizes and sends the reply —
  keyed by the provider's own call/stream ID, with no websocket/network code of its own (fully
  unit-testable by pushing provider-shaped messages through it directly).
- **Disconnect / timeout / error handling**: `WebSocketDisconnect` and unexpected exceptions are
  caught and logged without taking the server down; a per-connection idle-audio watchdog nudges
  a silent caller and ends the call after repeated silence; STT/TTS failures on one turn are
  logged and don't kill the call.
- **Logging** throughout, call-scoped (`call_id=... workspace_id=...`) at every stage: call start,
  each transcript, detected intent/language, each reply, and call end.
- No dashboard functionality (explicitly out of scope for this phase).

## Phase 6 — Caller Qualification

Business rules for turning a call into a qualified booking, kept entirely in `app/ai/qualification/`
(pure Python, no LLM call anywhere in it — the LLM is never asked to validate or decide these things):

- **Identify intent** and **detect booking intent**: unchanged from Phase 4's `NLUEngine` — rule-based,
  multilingual, LLM-independent (see `test_qualification_decisions_are_identical_regardless_of_llm_provider`).
- **Identify service/department**: a matched service is looked up against the workspace's own
  `service_departments` mapping (`ai_agents.config`) to resolve a department — e.g.
  `{"Root Canal": "Endodontics"}`. A service with no configured mapping simply has no department;
  it's never guessed.
- **Collect required information / appointment requirements**: unchanged flow from Phase 4/5 —
  name, phone, service, and date/time, asked for one at a time.
- **Validate information**: `qualification/validators.py` — phone numbers via `phonenumbers`
  (rejects unparseable/invalid numbers), names (rejects empty/too-short/digits-only), services
  (must be one the workspace actually offers), and appointment date/times (rejects anything in
  the past, with a dedicated "that time's already passed" reply telling the caller *why* it wasn't
  accepted, in their own language) — a value that fails validation is never written into
  conversation state.
- **Create/update patient records**: booking a returning caller (matched by phone) now updates
  their name on file if they gave a different one this call, rather than only ever matching or
  creating.
- **Create/update lead records**: a caller becomes a `Lead` the moment we know how to reach them
  (a phone number) and isn't already an identified existing patient — capturing prospects who
  browse, ask questions, or abandon a booking partway through. Status only ever escalates
  (`new → qualifying → converted`, enforced by `qualification.next_lead_status`) so a later,
  less-informative turn can never downgrade a lead that already progressed further; booking
  completion escalates the matching lead to `converted`.
- **Never invent missing patient information**: structured fields (name/phone/service/date) are
  *only* ever populated from entity extraction run against what the caller actually said — the
  LLM's free-text output (used only for open-ended chit-chat replies) is never parsed back into
  state. Verified directly: `test_llm_generated_text_never_populates_structured_caller_fields`
  feeds the engine a fake LLM that fabricates a name and phone number in its reply text, and
  confirms none of it ever reaches `state.caller` or produces a database write.
- **Keep business rules outside the LLM**: every qualification decision above is deterministic
  Python with no LLM dependency; `test_qualification_decisions_are_identical_regardless_of_llm_provider`
  runs the same simulated call through both the mock LLM and a "lying" fake LLM and asserts
  identical qualification outcomes.

## Phase 7 — Appointment Scheduling

```
collect information → validate → check availability → confirm with caller → create appointment → return result
```

- **Confirm-with-caller gate**: once every booking requirement is collected and validated, the AI
  Receptionist asks "I have you down for {service} on {when} — shall I go ahead and book it?" and
  waits for a yes/no answer (`app/ai/nlu/confirmation.py`, rule-based, multilingual) before
  attempting anything. Declining clears just the date/time and re-asks, keeping name/phone/service.
- **Never tell the caller "confirmed" before the backend confirms**: the engine's own reply for
  the actual booking/cancel/reschedule attempt is only ever a provisional placeholder ("One moment
  please.") — `ReceptionistService` always overwrites it with an outcome-aware reply
  (`ConversationEngine.render_*_outcome`) computed *after* the database write actually happens.
  There is no code path where success wording is produced before `db.commit()` succeeds.
- **Availability checking / conflict detection** (`app/ai/scheduling/`): once a specific provider
  is selected, a new booking (or reschedule) is checked against that provider's other scheduled
  appointments for a time overlap; a conflict is rejected with an explanation and the caller is
  asked for a different time, keeping everything else they already provided. (Documented
  limitation: without a pinned provider there's no single resource to check contention against,
  so a "no preference" booking skips this check.)
- **Duplicate-booking prevention**: independently of provider conflicts, a new booking is checked
  against the *same caller's* (by phone) other scheduled appointments for a time overlap —
  catching a caller accidentally booking themselves twice.
- **Provider/service selection**: service selection is unchanged from Phase 6; if a workspace has
  any active providers configured, the caller is also asked which one (or "no preference"),
  extracted the same substring-match way as service (`app/ai/nlu/entities.py: extract_provider`).
- **Timezone handling**: appointment times are parsed anchored to the workspace's own timezone
  (`Workspace.timezone`, already in the Phase 2 schema) via `dateparser`'s
  `TIMEZONE`/`RETURN_AS_TIMEZONE_AWARE` settings — "3pm" means 3pm at the clinic, not the server.
  Every time is normalized to UTC before being compared or persisted
  (`app/ai/scheduling/rules.py: as_aware_utc`), which also papers over SQLite silently dropping
  timezone info on round-trip (PostgreSQL is unaffected either way).
- Cancellation and reschedule also gained honest outcome reporting as part of this phase: a
  cancel/reschedule request that doesn't match any appointment now correctly says so instead of
  claiming success (a latent gap from Phase 4 — see docs/phase-7.md).

## Phase 8 — Google Calendar Integration

- **Provider abstraction** (`app/integrations/calendar/`): `CalendarProvider` interface —
  `check_availability`, `create_event`, `update_event`, `cancel_event` — with a `GoogleCalendarProvider`
  (service-account auth, written against the documented Calendar API v3) and an automatic
  `MockCalendarProvider` fallback when no credentials are configured, same pattern as every other
  provider in this project.
- **Opt-in per workspace**: a workspace only syncs to a calendar if it has an active `integrations`
  row (`provider="google_calendar"`, `config.calendar_id`) — server-level credentials say *how* to
  authenticate; the per-workspace row says *whether* and *where*.
- **Availability / conflict**: booking and rescheduling now also check the external calendar (in
  addition to Phase 7's internal DB conflict check) — catches something blocked directly on Google
  Calendar that this system never wrote itself. A calendar-sourced conflict rejects the booking the
  same way an internal one does; a calendar-check *failure* (auth/timeout/API error) never does —
  only a genuine busy answer affects the booking outcome.
- **Store external event IDs**: `Appointment.external_calendar_event_id` /
  `.external_calendar_provider` (nullable — an appointment is fully valid whether or not calendar
  sync succeeded). Rescheduling `PATCH`es the same event id instead of creating a new one;
  cancelling deletes it and clears the id.
- **Duplicate-event prevention**: `CalendarSyncService.create_event` is a no-op if the appointment
  already has an `external_calendar_event_id` — an appointment is synced to the calendar at most once.
- **Error handling**: authentication failure, expired credentials, unavailable slots, generic API
  errors, and timeouts are each their own exception type
  (`app/integrations/calendar/exceptions.py`), handled distinctly by `CalendarSyncService` — every
  category except "slot unavailable" is caught, logged, and raised as a staff-facing `Notification`
  ("Google Calendar sync failed") without ever blocking the booking itself, which always still
  succeeds in this system's own database.

## Phase 9 — Notification Adapters (WhatsApp + Email)

- **Provider abstractions** (`app/integrations/notifications/`): a `WhatsAppProvider` interface
  (`TwilioWhatsAppProvider`, `MetaWhatsAppProvider`) and an `EmailProvider` interface
  (`SendGridEmailProvider`), each with an automatic `Mock*Provider` fallback when no credentials
  are configured — same pattern as calendar/telephony. `WHATSAPP_PROVIDER` selects `mock` |
  `twilio` | `meta`; `EMAIL_PROVIDER` selects `mock` | `sendgrid`.
- **Supported events** (`NotificationService.notify_appointment_event`): appointment confirmation,
  cancellation, and rescheduling. Each event sends a patient-facing copy (WhatsApp to
  `Patient.phone`, email to `Patient.email` — whichever are on file) and, if the workspace has an
  active `integrations` row (`provider="clinic_notifications"`, `config.whatsapp_number` /
  `config.email`), a clinic/receptionist-facing copy on the same channels — opt-in per workspace,
  same split as calendar sync.
- **Tracking** (`NotificationMessage` model / `notification_messages` table): one row per delivery
  attempt — channel, event type, audience (patient/clinic), recipient, provider, provider message
  id, status (`pending`/`sent`/`failed`), failure reason, subject/body, and `sent_at`. Exposed
  read-only at `GET /api/v1/workspaces/{workspace_id}/notification-messages`.
- **Duplicate-notification prevention**: a `(workspace, appointment, event_type, channel,
  recipient)` combination that already has a `status="sent"` row is never sent again — the
  existing row is returned instead. A `"failed"` row does *not* block a retry, so a transient
  outage doesn't permanently block a notification the way a real terminal success would.
- **Error handling**: auth failure, invalid recipient, rate limiting, timeouts, and generic API
  errors are each their own exception type (`app/integrations/notifications/exceptions.py`),
  caught by `NotificationService` and recorded as `status="failed"` with a specific
  `failure_reason` — a notification failure never raises out of the service or blocks the booking
  it's describing.

## Phase 10 — Human Receptionist Escalation

- **Five transfer triggers, one shared mechanism** (`app.ai.conversation.effects.TransferToHumanEffect`,
  now carrying a `trigger` field): caller explicitly asks for a person (`caller_request`); the AI
  can't classify what the caller wants for 3 consecutive turns before any real request has been
  identified, or repeatedly fails to detect the caller's spoken language (`repeated_misunderstanding`);
  the message matches a request category the AI never handles — billing, insurance, legal, refunds
  (`unsupported_request`, `app/ai/nlu/keywords.py`); the caller's message matches a workspace-configured
  keyword rule, e.g. "emergency" (`clinic_rule`, `ai_agents.config["escalation_keywords"]`, checked
  before every other intent); or the AI Receptionist's own logic raises an unhandled exception
  (`technical_failure`, caught in `ReceptionistService.handle_message` so a bug never leaves the
  caller hanging).
- **Recorded before any transfer is attempted** (`HumanHandoff` model / `human_handoffs` table):
  trigger, reason, the full conversation transcript up to that point (`conversation_context`), a
  snapshot of caller info/intent/appointment draft/language (`call_state`), and the timestamp
  (`created_at`) — this write always happens, live transfer or not. Exposed read-only at
  `GET /api/v1/workspaces/{workspace_id}/human-handoffs`.
- **Twilio/Vapi integration** (`TelephonyAdapter.supports_live_transfer()` / `.transfer_call()`,
  `app/telephony/providers/`): Twilio redirects the *live* call via its documented "update a call"
  REST API (`POST /Calls/{CallSid}.json` with a new `<Dial>` TwiML) — which needs the call's actual
  CallSid, now captured separately from the streamSid used as `call_id` throughout this pipeline
  (`CallStarted.provider_call_id`). Vapi uses a best-effort call-control transfer request, same
  unverified-against-a-live-account caveat as the rest of that adapter. Both fall back to
  `MockTelephonyAdapter.transfer_call` (records every attempted transfer in memory) when
  unavailable — same pattern as every other provider in this project. A transfer is only attempted
  when the call is live (`CallSession` passes its adapter + provider_call_id through) *and* the
  workspace has set `ai_agents.config["human_transfer_number"]`; otherwise the handoff is still
  recorded, just with `status="pending"` instead of `"transferred"`/`"failed"`.

## Phase 11 — Premium Dashboard UI (HTML5 / CSS3 / vanilla JS)

- **No frameworks**: the whole dashboard (`frontend/index.html`, `css/dashboard.css`,
  `js/app.js`, `js/charts.js`, `js/mock-data.js`) is hand-rolled HTML5/CSS3/vanilla JS — no
  React/Vue/Angular, no build step, no bundler. `js/charts.js` hand-generates inline SVG for
  every chart (line/area, bar, donut, sparkline) rather than pulling in a charting library.
- **12 pages, one shell**: Overview, Live Calls, Leads, Patients, Appointments, Call History, AI
  Receptionist, Analytics, Automations, Integrations, Team, Settings — a single-page app with
  hash-based routing (`#/leads`, ...) toggling `.page.is-active` sections inside one collapsible
  sidebar + topbar shell, rather than 12 separate HTML files repeating the same chrome.
- **The human staff role reads "Receptionist"** everywhere a role badge/label appears
  (`roleLabel()` in `app.js`), matching the backend's `WorkspaceRole.RECEPTIONIST` value exactly.
- **Design system** (`css/dashboard.css`): CSS custom properties for a full light/dark palette
  (`:root` / `:root[data-theme="dark"]` / `prefers-color-scheme`), a collapsible sidebar (icon-only
  when collapsed, off-canvas drawer on mobile), advanced KPI cards with inline sparklines, data
  tables with search/filter/sort/pagination, generic modal and toast systems, and dedicated
  loading (skeleton), empty, and error visual states used consistently across every page.

## Phase 12 — Frontend ↔ Backend Wiring

- **Reusable API service layer** (`frontend/js/api-service.js`, `const Api = ...`): every backend
  call goes through one `request()` function — attaches the bearer token, serializes/parses JSON,
  and normalizes every failure into an `ApiError { message, status }`. Organized into
  `Api.auth` / `.workspaces` / `.leads` / `.patients` / `.appointments` / `.calls` (+ `.transcripts`)
  / `.handoffs` / `.notificationMessages` / `.ai` / `.analytics`, mirroring the backend's own
  router split.
- **Connected with real data**: authentication (register/login/me/logout), dashboard Overview
  (aggregated client-side from real calls/appointments/leads), Leads, Patients, Appointments, Call
  History (+ transcript modal via `GET /calls/{id}/transcripts`), Team (`GET/POST
  /workspaces/{id}/members`), and workspace profile Settings all read and write through the real
  FastAPI backend — mock data was removed from these pages entirely.
- **Honestly still a preview where the backend has no endpoint for it**: AI Receptionist settings,
  Integrations, and Automations have no CRUD API yet (`ai_agents` config and `Integration` rows
  aren't exposed for staff editing) — those pages render `MOCK` data behind a visible
  `demoNote(...)` banner rather than silently faking a connection.
- **Handles loading / errors / empty states / auth expiry / failed requests**: every connected page
  goes through a shared `loadInto()` helper (skeleton → data, or the shared empty/error state with
  a Retry button) in `app.js`. A 401 from any request makes `Api` broadcast a one-time
  `ar:auth-expired` window event; `app.js` listens for it, clears the session, and drops the user
  back to the login screen with a toast — no page has to special-case token expiry itself.

## Phase 13 — Metrics, Structured Logging & Analytics

- **Tracked metrics** (`app/services/analytics.py: compute_analytics_summary`): total calls,
  answered calls, average call duration, qualified leads, appointments, lead conversion rate, AI
  resolution rate, Receptionist transfers, and integration failures — computed from real rows
  (`Call`, `Lead`, `Appointment`, `HumanHandoff`, `IntegrationLog`), scoped to one workspace and
  optionally a `since`/`until` date range. AI resolution rate is computed via
  `Call.conversation_session_id` (new column) joined against `HumanHandoff.conversation_session_id`
  — the fraction of calls that were *not* escalated to a human.
- **Structured (JSON) logging** (`app/core/logging_config.py`): one JSON object per log line by
  default (`LOG_FORMAT=json`; `LOG_FORMAT=text` for a human-readable dev format) — timestamp,
  level, logger name, message, and whichever correlation IDs are bound.
- **Request IDs, call IDs, workspace IDs** (`app/core/logging_context.py`, `contextvars`-based, safe
  across concurrent asyncio tasks): `RequestContextMiddleware` binds a request ID to every HTTP
  request (reusing an inbound `X-Request-ID` header, or generating one) and echoes it back on the
  response and in every error body; `get_tenant_context` binds workspace ID for the duration of any
  workspace-scoped request; `CallSession` binds call ID for the duration of each telephony event.
  Every log line emitted while any of these are bound is automatically stamped with them.
- **Calls are now persisted** (`CallSession._create_call_row` / `_finalize_call_row`,
  `app/telephony/session.py`): a real `Call` row is created the moment a call connects and
  finalized (status/ended_at/duration) when it ends — previously the live telephony pipeline never
  wrote a `Call` row at all, which meant `total_calls`/`answered_calls`/`average_duration` had
  nothing to aggregate.
- **Audit logs** (`app/services/audit.py: record_audit_log`, writing to the pre-existing but
  previously-unused `AuditLog` model): wired into registration, login, logout, workspace
  create/update, member invites, and lead/patient/appointment creation — each an immutable,
  independently-committed row (actor, action, resource, extra data).
- **Integration logs** (`app/models/integration_log.py`, new `IntegrationLog` model / table): one
  row per attempted call to an external provider — calendar sync (`CalendarSyncService`),
  WhatsApp/email notifications (`NotificationService`), and telephony live transfer
  (`ReceptionistService._attempt_live_transfer`) each record success/failure, which is what
  `integration_failures` in the analytics summary counts.
- **Connected to the dashboard**: `GET /workspaces/{workspace_id}/analytics/summary` (optional
  `since`/`until` query params) is wired into the frontend's Analytics page
  (`Api.analytics.summary()`, `frontend/js/app.js`), replacing its client-side-derived KPIs with
  the real backend aggregate, with a 7/30/90-day/all-time range toggle. Trend charts (calls-by-hour,
  top services) stay demo data behind a `demoNote()`, since the backend currently exposes only an
  aggregate summary, not a time-series/breakdown endpoint.

## Phase 14 — Security Audit

A full pass over authentication, authorization, tenant isolation, input validation, CORS,
secrets, API exposure, database access, rate limiting, sensitive logging, webhook validation, and
frontend security. What follows is what was actually found and actually fixed — most of the
codebase's existing tenant-isolation and RBAC design (every workspace-scoped query already
filtered by a verified `ctx.workspace_id`, no raw SQL anywhere, no secrets in frontend code) held
up and needed no changes.

**No healthcare regulatory compliance (HIPAA or otherwise) is claimed anywhere in this project.**
Nothing here has been audited or certified as HIPAA-compliant — encryption-at-rest, BAAs with
subprocessors, breach-notification procedures, and formal access-control audits are all
unaddressed. Treat this as security hardening for a demo/pre-production system, not a compliance
attestation.

Genuine issues found and fixed:

- **Twilio webhook was unauthenticated** (`app/api/telephony.py`): `POST /telephony/twilio/{workspace_id}/voice`
  never verified `X-Twilio-Signature`, even though `TwilioAdapter.verify_webhook_signature` already
  existed. Anyone who learned a workspace_id could hit it directly and receive a working Media
  Stream URL. Now verified (when Twilio is the configured provider) via the existing HMAC-SHA1
  check, rejecting with 403 on a missing/invalid signature.
- **The WebSocket stream endpoint had no equivalent gate**: even with the webhook now signed,
  anyone who learned the stream URL shape could connect directly and drive the AI Receptionist as
  a fake caller (cost abuse, prompt injection). New short-lived signed tokens
  (`app/telephony/stream_token.py`) are minted by the webhook only after its own signature check
  passes, and required by the stream endpoint for the `twilio` provider path only — the mock
  adapter (tests, local dev) is unaffected.
- **Tenant-isolation gap on appointment creation** (`app/api/appointments.py`): `provider_id` and
  `service_id` were accepted from the client and written straight into the new `Appointment` row
  with no check that they belonged to the caller's own workspace — a cross-tenant IDOR. Both are
  now verified the same way `patient_id` already was.
- **`Appointment.status` was client-settable on create** (`app/schemas/appointment.py`): removed —
  a new appointment always starts `"scheduled"` server-side. Also added `end_time > start_time`
  validation (previously unchecked) and a `notes` length cap.
- **Unvalidated/unbounded input**: `Lead.status` accepted any string up to 32 chars (now a
  `Literal` of the four real statuses); `Lead.email`/`Patient.email` accepted any string (now
  `EmailStr`, matching how `auth` schemas already validated email); `LoginRequest.password` had no
  `max_length` at all (unauthenticated endpoint + unbounded input = an easy resource-exhaustion
  vector); `RegisterRequest.password`'s 128-char cap exceeded bcrypt's actual 72-byte limit, so two
  different long passwords sharing a 72-byte prefix would have silently hashed identically — capped
  at 72 to match what bcrypt actually checks.
- **No request body size limit anywhere**: a new `BodySizeLimitMiddleware` (`app/core/middleware.py`)
  rejects any request over 2 MB via `Content-Length` before Pydantic even parses it.
- **No rate limiting anywhere**: a small in-memory, per-process limiter (`app/core/rate_limit.py`,
  explicitly documented as not distributed-safe — a real deployment with multiple workers needs
  Redis or similar) now guards `/auth/login` (10/min), `/auth/register` (5/min), and the Twilio
  webhook (30/min) — the endpoints an unauthenticated attacker can actually reach.
- **Insecure defaults with no production guard**: `SECRET_KEY`'s dev-only fallback had no check
  stopping a deployment from silently running with it — the app now refuses to start
  (`Settings` raises at construction) if `APP_ENV` is production-like and `SECRET_KEY` is still the
  fallback. `DEBUG` now defaults to `False` (was `True`) — secure-by-default rather than relying on
  every deployment remembering to override it.
- **Unnecessary CORS permissiveness**: `allow_credentials=True` was set despite this API being
  bearer-token-only (never cookie-based) — that flag only relaxes cross-origin *credentialed*
  request handling, which this app never needed; now `False`.
- **API docs exposed unconditionally**: `/docs`, `/redoc`, and `/openapi.json` are now disabled
  outside development/test — real attack-surface reduction, since the full API shape is otherwise
  handed to anyone who asks.
- **Unescaped XML in the Twilio TwiML response** (`app/telephony/providers/twilio_adapter.py`):
  `From`/`To` webhook fields were interpolated into XML attributes with no escaping — low severity
  (real Twilio only ever sends E.164 numbers, and this only reaches Twilio's own TTS parser, not a
  browser), but fixed anyway with proper `xml.sax.saxutils.quoteattr` encoding.
- **Frontend**: confirmed no API keys or provider secrets exist anywhere in `frontend/` (they never
  did — the frontend only ever talks to this app's own backend, never a third-party provider
  directly) and that every place API/user data is rendered goes through `escapeHtml()` (already
  true from Phase 11/12, re-verified here). Added a `Content-Security-Policy` meta tag
  (`frontend/index.html`) restricting script execution to same-origin as defense-in-depth beyond
  that existing output-escaping discipline.

Explicitly *not* changed, with reasoning: workspace `Owner`/`Admin` roles currently carry identical
permissions in `app/core/rbac.py` (a design choice, not a privilege-escalation bug, since an Admin
inviting someone as "Owner" grants nothing an Admin couldn't already do); password complexity rules
were deliberately not added (current NIST guidance favors length over composition rules, and
`min_length=8` plus the new rate limiting already covers brute-force risk reasonably). A
pre-existing `dateparser` bug (unrelated to security — "next Tuesday" resolves incorrectly when
today literally is a Tuesday) was left alone; a separate pre-existing test-timing race (a fixed
`asyncio.sleep()` shorter than `langdetect`'s cold-process model-load time) was fixed with polling
instead of a longer guess, since it started intermittently failing once this phase's new test files
shifted collection order — a test-only change, no production code involved.

## Phase 15 — End-to-End Testing

A full test pass across every layer (authentication, RBAC, tenant isolation, database, the AI
Receptionist, lead qualification, appointment booking, duplicate-booking prevention, Google
Calendar, WhatsApp, email, WebSocket, the voice pipeline, Receptionist handoff, API failures) plus
one true end-to-end scenario test (`tests/test_end_to_end_scenario.py`) driving a real call all the
way through: **caller → AI Receptionist → STT → LLM → TTS → qualification → appointment →
database → calendar → WhatsApp → email → dashboard** — the last step being the staff-facing HTTP
API itself, not just a direct DB read, so the test genuinely proves the dashboard reflects what the
call actually did. Also covers duplicate-booking prevention, a Receptionist handoff reaching the
dashboard, and calendar/WhatsApp failures never blocking the booking — all through that same live
pipeline rather than each integration tested only in isolation.

Two genuine, previously-shipped bugs were caught and fixed by writing this scenario test:

- **WhatsApp/email confirmations were never actually sent.** `NotificationService` (built in Phase 9)
  and `ReceptionistService` (which owns the actual booking/cancellation/reschedule flow) were never
  wired together — every notification adapter, template, and delivery-tracking row from Phase 9
  worked perfectly in isolation, but a real booking never called any of it. Every unit/integration
  test up through Phase 14 tested `NotificationService` directly, so nothing caught the missing
  wiring. Now fixed: `ReceptionistService.__init__` constructs a `NotificationService`, and
  `_book_appointment` / `_cancel_appointment` / `_reschedule_appointment` each call
  `notify_appointment_event(...)` after their DB write (and after calendar sync) succeeds — same
  "never blocks the caller-facing outcome" resilience as calendar sync already had.
- **A real concurrency bug in the voice pipeline** (`app/telephony/session.py`): `CallSession`
  processes each caller turn via `asyncio.to_thread` (a synchronous SQLAlchemy `Session` can't share
  the event loop), and — once notifications were wired in and a booking turn started doing real work
  (DB write, calendar sync, WhatsApp send) — a caller hanging up (or a test closing the session)
  immediately after their final "yes" could call `close()` while that turn's DB work was still
  in-flight on another thread. Cancelling the asyncio Task awaiting `to_thread()` does **not** stop
  an already-started thread (a documented asyncio/executor limitation) — so `close()`'s own
  `_finalize_call_row` could end up touching the same `Session` concurrently, raising
  SQLAlchemy's `IllegalStateChangeError`. Fixed with an `asyncio.Lock` (`CallSession._db_lock`)
  held for the duration of every `to_thread()` call that touches the session — `_create_call_row`,
  the per-turn `handle_message`, and `_finalize_call_row` — which serializes them at the asyncio
  level in a way cancellation can't bypass.

A third bug, unrelated to any single integration but caught the same way, was fixed in
`app/ai/nlu/entities.py`: `dateparser` has a reproducible bug where a bare weekday-name phrase
("Tuesday at 3pm", "next Tuesday") parsed *on that same weekday* can resolve to an entirely wrong
weekday, weeks in the past (reproduced directly — parsing "Tuesday at 3pm" on an actual Tuesday
returned a Saturday three weeks prior). This was previously visible only as an intermittent test
failure (three booking tests failed only on days when "next Tuesday" happened to be the current
day) and would have produced the same wrong result for a real caller. Fixed by recomputing the date
from Python's own weekday arithmetic (keeping dateparser's correctly-parsed time-of-day) whenever
the phrase names a weekday, rather than trusting dateparser's day-of-week resolution for that case.

Final state: 301 backend tests passing, zero known failures (previously 294 passing / 3 failing,
all three caused by the dateparser bug above).

## Phase 16 — Production Readiness

Full deployment guide: **[`docs/deployment.md`](docs/deployment.md)** — environment variables,
migration instructions, health checks, production logging, Docker, concrete deployment paths for
AWS/GCP/DigitalOcean (backend) and Vercel/Netlify (frontend), a production checklist, and rollback.
Summary of what changed this phase:

- **Health checks split into liveness vs. readiness** (`app/api/health.py`): `GET /api/v1/health`
  touches no dependency (only fails if the process itself is wedged — for a restart policy);
  `GET /api/v1/health/ready` checks the database is actually reachable and returns `503` if not
  (for a load balancer's target-group / orchestrator readiness probe, to pull an instance out of
  rotation without restarting it).
- **Docker**: `backend/Dockerfile` (multi-stage-ready `python:3.12-slim`, non-root user, a
  container `HEALTHCHECK`, `gunicorn` managing a pool of `uvicorn` workers — the standard
  production ASGI process model) and a repo-root `docker-compose.yml` wiring it up with a real
  Postgres container for local verification.
- **Frontend is now deployable somewhere that isn't localhost**: `frontend/js/config.js` (new)
  holds the one thing a build step would normally inject — the backend's URL
  (`window.__AI_RECEPTIONIST_CONFIG__.API_BASE_URL`) — since this frontend intentionally has no
  build step at all. Previously hardcoded to `http://localhost:8000/api/v1` directly in
  `api-service.js`, which would have silently broken every API call on a real Vercel/Netlify
  deployment.
- **Production logging** was already structured JSON by default (Phase 13) and needed no changes —
  confirmed it lands in the shape CloudWatch Logs/Cloud Logging/DigitalOcean's log forwarding all
  ingest natively (see `docs/deployment.md`).

**What was verified, and what wasn't**: the sandbox this was built in has Docker Desktop installed,
but its engine was unresponsive (`docker info` timed out rather than erroring cleanly) — the actual
`docker compose up` + real Postgres path could not be run here. What *was* verified directly: the
production app (multi-worker `uvicorn`, `APP_ENV=production`, a real generated `SECRET_KEY`,
`DEBUG=false`) starts correctly, refuses to start with the insecure default secret (Phase 14,
re-confirmed here), serves `/api/v1/health` and `/api/v1/health/ready` correctly, returns `404` for
`/docs`/`/openapi.json`, and produces correct structured JSON logs with request-ID correlation for
a full register/login round-trip — against SQLite standing in for Postgres, since gunicorn itself
is POSIX-only and doesn't run on this Windows sandbox outside a Linux container. `docs/deployment.md`
states this substitution explicitly and says what still needs verifying (the real Docker image
against real Postgres) before a first production deployment — no claim is made that Docker was
actually exercised end-to-end here.

## Phase 17 — Final Audit

A full pass across every area of the project (architecture, backend, frontend, database, auth,
RBAC, multi-tenancy, the AI Receptionist, voice pipeline, patient/lead system, appointments,
Google Calendar, WhatsApp, email, Receptionist handoff, analytics, security, logging, testing,
deployment). One genuine, launch-blocking issue was found and fixed:

- **No API existed to create `Service` or `Provider` records** — the only way they ever got a row
  was a test fixture inserting one directly. Since a workspace with zero services can never have a
  caller successfully specify one (`extract_service`/`validate_service` in
  `app/ai/nlu/entities.py` always fail to match against an empty list, and there's no upper bound
  on retries), **the AI Receptionist's core booking flow was completely unusable for any real,
  newly-signed-up clinic** — a fresh workspace had no way, through the API or the dashboard, to
  configure what it offers. Fixed with a `Service`/`Provider` CRUD API (`app/api/services.py`,
  `app/api/providers.py`) mirroring the existing Lead/Patient pattern exactly — tenant-isolated,
  RBAC-gated (`services:write`/`providers:write` are Owner/Admin-only, matching `settings:manage`'s
  tier; reads are broader, matching every other resource), audited. No schema migration was needed
  — both tables already existed from Phase 2, only unreachable through the API. Verified with a
  live server: created a service and provider through the real HTTP API, then ran an actual AI
  Receptionist conversation through to a completed booking, then confirmed it via the dashboard's
  own `/appointments` and `/analytics/summary` endpoints.
- Also removed three genuinely dead files with no remaining references anywhere
  (`frontend/js/api.js`, `frontend/js/main.js`, `frontend/css/styles.css` — Phase 1 scaffold,
  superseded by `api-service.js`/`app.js`/`dashboard.css` since Phase 11/12) and one unused import
  (`app/models/auth_session.py`).

Everything else audited held up without changes needed — see each phase's own section above for
what was built and verified at the time. Remaining known gaps (not fixed this phase — see the
audit's final report) are lower-severity, non-blocking polish items: no dashboard UI yet for
managing services/providers/AI settings/integrations (the APIs that exist are usable directly;
some, like AI-agent config and third-party integrations, have no API yet at all — those pages stay
honestly labeled as previews), `BusinessHours` is modeled but never enforced by scheduling, and the
Docker/Postgres deployment path from Phase 16 still needs a run in an environment with a working
Docker daemon (verified there via direct production-mode `uvicorn` + SQLite instead, for the same
environment reason noted in that phase).

## Phase 18 — Frontend Update: Timezone, Sidebar, Team Phone & Settings Routing

Targeted updates to the existing vanilla-JS dashboard (`frontend/index.html`,
`css/dashboard.css`, `js/app.js`, `js/api-service.js`) — no framework introduced, no page
rebuilt, existing design tokens/components reused throughout.

### 1. Dynamic IANA timezone selector (Settings → Workspace)

The Workspace tab's timezone field is now a searchable `<select>` built at render time from
**`Intl.supportedValuesOf('timeZone')`** (~418 zones in current browsers) — no hardcoded list.
Each option shows a friendly label plus the live UTC offset, e.g. `New York — America (UTC-4)`,
`Karachi — Asia (UTC+5)`, `UTC`. A very small static fallback list is used only if the browser
predates `Intl.supportedValuesOf`.

- **Load**: `GET /api/v1/workspaces/{id}` (`Api.workspaces.get`) — the saved `timezone` string is
  pre-selected. A skeleton shows while the request is in flight (via the shared `loadInto`
  helper); a load failure shows the shared error state with Retry.
- **Save**: `PATCH /api/v1/workspaces/{id}` with body `{ "name": "<string>", "timezone": "<IANA string>" }`
  (`WorkspaceUpdate` schema — both fields optional server-side; the UI always sends the current
  value of both). The Save button shows its spinner and is disabled while the request runs;
  success re-syncs `state.workspace` and re-renders the dropdown from the value the backend
  returned; failure shows an inline `.field__error` **and** a toast.
- **Preserve existing**: a currently-saved timezone that isn't in this browser's IANA list is
  appended to the options so it is never silently dropped. Empty clinic name is blocked
  client-side before the request.

Backend fields used, unchanged: `Workspace.timezone` (`String(64)`), `WorkspaceUpdate.timezone`,
`WorkspaceOut.timezone`. No new endpoint, no separate timezone store.

### 2. Responsive hamburger / sidebar

The mobile hamburger (`#mobile-menu-btn`, already in the markup, shown by CSS `≤ 860px`) now has
real state management in `initSidebar()`:

- Desktop (`> 860px`): sidebar is the normal sticky column; the collapse toggle
  (`localStorage: ar_sidebar_collapsed`) is unchanged.
- Mobile/tablet (`≤ 860px`): the button toggles `#app-shell.is-mobile-open` — the off-canvas
  sidebar slides in over a dimmed `#scrim`.
- Closes on: tapping the scrim, pressing **Escape**, and navigating to any page (the router calls
  `closeMobileDrawer()`), so a nav tap on mobile always dismisses the drawer.
- Background scroll is locked while the drawer is open (`body.is-drawer-open { overflow: hidden }`).
- Crossing back to desktop width force-closes the drawer (a `matchMedia('(max-width: 860px)')`
  `change` listener) **and** CSS `@media (min-width: 861px)` hard-hides the scrim/anchors the
  sidebar — so a leftover overlay can never cover the restored desktop layout.
- `aria-controls` / `aria-expanded` are set on the button.

### 3. Team invite — phone number

The **Team → Invite member** modal has a new optional **Phone number** field between Email and
Role, with client-side validation (`+` optional, then 7–15 digits allowing spaces / `(` `)` `-`
`.`); an invalid value shows a friendly inline error and blocks submit. Email validation is
unchanged (now also inline instead of a bare toast).

- **Payload**: the existing `POST /api/v1/workspaces/{id}/members` endpoint — **no second
  endpoint**. Body is now:

  ```json
  { "email": "colleague@clinic.com", "role": "receptionist", "phone_number": "+1 415 555 0100" }
  ```

  `phone_number` is **omitted entirely** when the field is left blank.
- **Backend**: `MemberInvite` (`app/schemas/workspace.py`) gained `phone_number: str | None`
  (`max_length=32`). `add_member` (`app/api/workspaces.py`) writes it to the invited user's global
  **`User.phone`** column **only if that user has no phone on file** — an invite never overwrites
  an existing number. The audit-log entry records `phone_applied: true/false`.

### 4. Settings tab routing (Workspace / Notifications / Security)

Rebuilt on the existing hash router as the single source of truth:

- Tabs are addressable: `#/settings`, `#/settings/notifications`, `#/settings/security`.
- The router (`parseRoute` → `renderRoute`) parses `page/sub`; `navigate()` only writes the hash,
  `renderRoute()` (driven by `hashchange`, and once on boot) is the only thing that paints — so
  the active tab, the URL, and browser back/forward can never desync or get "stuck".
- Deep-linking and refresh land on the right tab; back/forward move between tabs.
- **Bug fixed**: the Notifications tab called an undefined `settingsToggle()` helper and threw a
  `ReferenceError` on click (the tab appeared frozen). The helper is now defined
  (`.settings-row` + `.switch`, matching the existing component CSS).

### 5. Loading states / no fake data on the Overview

- The Overview greeting subtitle now reads the **real** workspace name (`state.workspace.name`) —
  the hardcoded `"Willow Creek Family Dental"` placeholder is gone.
- Every Overview KPI (`Calls today`, `Answered calls`, `Avg. call duration`, `Appointments
  today`, `New leads`) now renders the **real** number from `/calls`, `/appointments`, `/leads` —
  the `value || MOCK.kpis.*` fallbacks that used to flash fabricated figures (e.g. "47 calls")
  when the backend returned an empty list are removed. A real `0` renders as `0`.
- The call-volume line chart and call-outcomes donut are derived entirely from the real `/calls`
  payload (7-day buckets / `status` counts). With no calls, each shows an empty state instead of
  a fixture chart.
- "Recent activity" is built from the newest real calls / appointments / leads (or an empty
  state) — no more static `MOCK.recentActivity`. "Upcoming appointments" no longer falls back to
  `MOCK.appointments`.
- The **notifications dropdown** (top bar bell) now fetches `GET /api/v1/workspaces/{id}/notification-messages`
  and renders real delivery rows (event type · channel · recipient · status · relative time),
  with skeleton / empty / error states — it previously showed `MOCK.recentActivity`.
- The sidebar "Live Calls" item no longer shows a fake unread badge.
- Still honestly-labelled previews (unchanged — no backend endpoint exists): **Live Calls**,
  **AI Receptionist** config, **Automations**, **Integrations**, and the Analytics "Trends"
  block. Each carries its existing "preview" note. Settings → Notifications / Security likewise
  keep a preview note (no preferences/password endpoint yet) — their controls no longer claim to
  save.

### Cleanup

Removed `frontend/components/` and `frontend/pages/` — empty placeholder directories containing
only `.gitkeep`, referenced from no import, route, or build step. Every other frontend file
(`config.js`, `mock-data.js`, `charts.js`, `api-service.js`, `setup.js`, `app.js`, both
stylesheets, `index.html`) is still in active use and was kept. `mock-data.js` is still required
by the preview pages listed above.

### Tests

- Backend: `backend/tests/test_workspace_member_phone.py` — invite sets `User.phone` when absent,
  is accepted without a phone, and never overwrites an existing number. Full suite: **369 passed**.
- Frontend: pure helpers (route parsing, phone/email validation, timezone option building)
  verified under Node; `node --check` passes on every JS file. Browser-driven click-through of the
  four flows against a live backend was not run here (no browser automation available in this
  environment) — see each feature's behaviour described above.

## Phase 19 — Real Data for Live Calls & AI Test Widget, Multilingual Fix, Dead Code Removal

An audit pass against the actual backend contracts (not assumptions) turned up three real gaps
left behind by Phase 18, plus dead frontend code. Everything else audited — onboarding guard,
IANA timezone dropdown, hamburger drawer, team-invite phone field, settings tab routing — was
already correct and is unchanged.

### 1. `PreferredLanguage` didn't cover the clinic's actual languages

`ClinicSettingsUpdate.preferred_language` (`app/schemas/clinic_settings.py`) only accepted
`Urdu` / `English` / `Roman Urdu`, even though the live-voice pipeline
(`app/ai/language/pakistan.py`) has spoken Punjabi, Saraiki, Sindhi, and Pashto since an earlier
phase. Worse, the AI Receptionist page's "Supported languages" badges were hardcoded to
`["English", "Spanish", "French", "German"]` — actively wrong for this system, not just
incomplete.

- **Backend**: `PreferredLanguage` enum widened to `Urdu`, `English`, `Roman Urdu`, `Punjabi`,
  `Saraiki`, `Sindhi`, `Pashto`. Stored inside the `ai_agents.config` JSON blob, so this is a
  pure application-level change — **no migration needed**. New tests:
  `test_pakistani_languages_are_accepted`, `test_invalid_language_is_rejected`
  (`backend/tests/test_clinic_settings.py`).
- **Frontend**: the onboarding wizard's "Preferred language" dropdown (`js/setup.js`) now lists
  all seven. The AI Receptionist page's language badges now show the backend's real default
  list (`app/core/config.py: default_supported_languages`) instead of the fabricated one.

### 2. Live Calls page rendered fake calls

`renderLiveCalls()` painted three invented callers (`MOCK.liveCalls`) with fields — sentiment,
intent, spoken language, caller name — that don't exist on the `Call` model at all
(`backend/app/models/call.py` has `direction`, `from_number`, `to_number`, `status`,
`started_at`, `duration_seconds` — nothing else). Rewritten to fetch
`GET /workspaces/{id}/calls` (already implemented, already wired into `Api.calls.list()`) and
filter client-side to calls with no `ended_at`. Shows only real fields; a client-side timer still
ticks the duration between refreshes. This is a snapshot on load/refresh, not a push-updated
feed — the dashboard still has no WebSocket subscription to the live telephony stream, and the
preview note says so honestly instead of pretending otherwise.

### 3. "Test the AI Receptionist" was a fake toast

The chat widget on the AI Receptionist page showed a canned sample conversation and replied
"Preview only" to every message — despite `Api.ai.startSession` / `Api.ai.sendMessage` already
existing in `api-service.js` and the backend conversation API
(`POST /workspaces/{id}/ai/sessions`, `POST .../messages`) already being fully implemented and
permission-gated (`ai:interact`: Owner/Admin/Receptionist). Its own docstring calls this out as
built for exactly this: *"text-only caller (e.g. the staff dashboard's 'try it' demo)"*. Rewired
to start a real session on page load and hold a real conversation through the actual NLU /
conversation engine — the same one live calls use. The persona/escalation-keywords/providers
panel on the same page stays a labeled preview (`ai_agents.config` still has no CRUD endpoint).

### 4. Dead fixture data removed

`js/mock-data.js` carried ~200 lines of fixtures (fake leads, patients, appointments, call
history, team, KPIs, recent activity, providers, heatmap, outcome breakdown, 7-day call volume)
that nothing in `app.js` referenced any more — every one of those pages has fetched real data
from the API since Phase 12. Trimmed to exactly what's still used by the remaining
honestly-labeled preview surfaces: `automations`, `integrations` (no backend endpoint — the
`Integration` model exists but `app/api/router.py` mounts no router for it), and the Analytics
"Trends" block's `callsByHour` / `topServices` (no time-series endpoint yet, only
`/analytics/summary`). `aiConfig` was trimmed to the fields the (still-preview) persona panel
uses; its fake sample conversation and fake language list were removed now that the test widget
and language badges are real.

### Verification

- `node --check` passes on every frontend JS file (`app.js`, `mock-data.js`, `setup.js`,
  `api-service.js`, `charts.js`, `config.js`).
- `backend/app/schemas/clinic_settings.py` parses cleanly (`ast.parse`); the widened enum is a
  pure JSON-blob change with no migration.
- **Not verified**: this environment has no network access, so `pytest` could not actually be
  run against the two new backend tests or the existing suite. The new tests follow the exact
  pattern of the passing tests around them (`test_get_returns_defaults_before_anything_saved`,
  `test_invalid_tone_is_rejected`) — run `pytest backend/tests/test_clinic_settings.py` yourself
  before relying on this. Browser click-through against a live backend also wasn't run here (no
  browser automation available); the Live Calls and AI test-widget rewrites were verified by
  reading the exact response shapes their endpoints return, not by clicking through them.

## Project Structure

```
/backend
  /alembic          # migration environment + versions/
  /app
    /api            # route definitions
    /core           # config, logging, exceptions, middleware, rate limiting (Phase 14)
    /models         # SQLAlchemy ORM models (one file per entity)
    /schemas        # Pydantic schemas
    /services       # audit logs, integration logs, analytics (Phase 13)
    /database       # SQLAlchemy Base/mixins, engine, session, get_db()
    /integrations   # Google Calendar (Phase 8) + WhatsApp/email notification adapters (Phase 9)
    /ai             # LLM abstraction, multilingual NLU, conversation engine, STT/TTS,
                    # caller qualification + scheduling rules (Phase 4-7), human escalation (Phase 10)
    /telephony      # Twilio/Vapi adapters + live call transfer, WebSocket call-session
                    # orchestrator (Phase 5, transfer added Phase 10)
    /utils          # (empty — future shared utilities)
    main.py
  /tests
  alembic.ini
  requirements.txt
  .env.example
  Dockerfile        # production image (Phase 16 — see docs/deployment.md)
  .dockerignore

/frontend
  /css
  /js               # config.js (Phase 16 — backend URL for a real deployment), mock-data.js,
                    # charts.js, api-service.js, setup.js, app.js
  index.html

/docs
  deployment.md     # Phase 16 — full production deployment guide

docker-compose.yml  # backend + Postgres + a static-file frontend container, for local
                    # verification only — not itself a deployment target (Phase 16)
```

## Backend — Getting Started

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env       # Windows (cp on macOS/Linux)
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Health check: `GET http://localhost:8000/api/v1/health`

### Database setup

1. Provision a PostgreSQL database (locally, in Docker, or a managed instance).
2. Copy `.env.example` to `.env` and fill in `POSTGRES_USER`, `POSTGRES_PASSWORD`,
   `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` — or set `DATABASE_URL` directly.
   No credentials are hardcoded anywhere in the repo.
3. Apply migrations:

   ```bash
   cd backend
   alembic upgrade head
   ```

To generate a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe the change"
```

### Running tests

```bash
cd backend
pytest
```

The test suite validates the ORM models and settings structurally (registered tables, PK/FK/
index shape, timestamp columns) without requiring a live database, so it runs the same with or
without PostgreSQL available.

### AI Receptionist / LLM setup

No setup required by default — `LLM_PROVIDER=mock` runs a deterministic offline LLM, so
booking/cancellation/reschedule/transfer flows, multilingual detection, and the safety guardrail
all work with zero API credentials. To use a real model, set in `.env`:

```
LLM_PROVIDER=openai        # or: anthropic
OPENAI_API_KEY=sk-...
```

If the selected provider's API key is missing, the app automatically falls back to mock mode
(with a log warning) rather than failing to start.

### Voice pipeline setup (Twilio/Vapi + Deepgram + ElevenLabs)

No setup required by default — `mock` is the default for `TELEPHONY_PROVIDER`, `STT_PROVIDER`,
and `TTS_PROVIDER`, so the full caller → AI Receptionist → caller pipeline runs end-to-end with
zero external credentials (see `tests/test_telephony.py`). To use real providers, set in `.env`:

```
TELEPHONY_PROVIDER=twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...

STT_PROVIDER=deepgram
DEEPGRAM_API_KEY=...

TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

Point a Twilio phone number's voice webhook at
`POST https://<your-host>/api/v1/telephony/twilio/{workspace_id}/voice`; Twilio will then open a
Media Stream to `wss://<your-host>/api/v1/telephony/stream/twilio/{workspace_id}`, which is where
this phase's pipeline takes over. As with every other provider in this project, a missing API key
for the selected provider falls back to its mock automatically rather than failing to start.

### Google Calendar setup

No setup required by default — `CALENDAR_PROVIDER=mock` runs a deterministic in-memory calendar,
so booking/cancelling/rescheduling all sync correctly with zero external credentials (see
`tests/test_calendar_service_integration.py`). To use real Google Calendar:

```
CALENDAR_PROVIDER=google
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key":"...",...}
```

Then, per workspace, add an `integrations` row to opt that workspace in:

```python
Integration(
    workspace_id=..., provider="google_calendar", is_active=True,
    config={"calendar_id": "clinic@example.com"},  # or "primary"
)
```

Share that calendar with the service account's email (found in the JSON key) so it has edit
access. A missing/invalid `GOOGLE_SERVICE_ACCOUNT_JSON` falls back to the mock calendar
automatically; a workspace with no `integrations` row simply never syncs (bookings still work
normally, just without a calendar side effect).

### Notifications setup (WhatsApp + email)

No setup required by default — `WHATSAPP_PROVIDER=mock` and `EMAIL_PROVIDER=mock` run
deterministic in-memory adapters, so confirmation/cancellation/reschedule notifications all "send"
successfully with zero external credentials (see `tests/test_notification_service.py`). To use
real providers:

```
WHATSAPP_PROVIDER=twilio         # or: meta
TWILIO_ACCOUNT_SID=AC...         # reuses the telephony credentials above
TWILIO_AUTH_TOKEN=...
WHATSAPP_FROM_NUMBER=+14155238886

# or, for Meta's WhatsApp Cloud API:
META_WHATSAPP_ACCESS_TOKEN=...
META_WHATSAPP_PHONE_NUMBER_ID=...

EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG...
EMAIL_FROM_ADDRESS=clinic@example.com
```

Then, per workspace, add an `integrations` row to enable clinic/receptionist copies of every
notification:

```python
Integration(
    workspace_id=..., provider="clinic_notifications", is_active=True,
    config={"whatsapp_number": "+15551234567", "email": "frontdesk@example.com"},
)
```

A missing/invalid credential for the selected provider falls back to its mock automatically; a
workspace with no `clinic_notifications` integration simply gets no clinic-facing copies (patient
notifications still send normally).

## Frontend — Getting Started

The frontend is static HTML/CSS/JS with no build step. Open `frontend/index.html` directly in a browser,
or serve it with any static file server, e.g.:

```bash
cd frontend
python -m http.server 5500
```

Then visit `http://localhost:5500`. The dashboard calls the backend health endpoint at
`http://localhost:8000/api/v1/health` — make sure the backend is running and its CORS origins
(`CORS_ORIGINS` in `.env`) include the frontend's origin.

## Explicitly Out of Scope

Phase 1 excluded: database, authentication, AI, telephony, appointments, notifications.
Phase 2 added the database layer (schema only). Phase 3 added authentication, RBAC, and
multi-tenancy. Phase 4 added the core AI Receptionist conversation service (text-level; it does
not diagnose, prescribe, or make clinical decisions). Phase 5 added the real-time voice pipeline
(Twilio/Vapi + Deepgram + ElevenLabs, with mock adapters throughout). Phase 6 added caller
qualification (validation, service/department identification, lead/patient record
create-and-update — all rule-based, outside the LLM). Phase 7 added full appointment scheduling
(availability checking, conflict detection, duplicate-booking prevention, timezone handling, and
a confirm-with-caller gate that guarantees the caller is never told "confirmed" before the
backend actually confirms it). Phase 8 added Google Calendar integration (availability, event
create/update/cancel, external event ID storage, duplicate-event prevention, and graceful
handling of auth failure/expired credentials/API errors/timeouts — with a mock calendar when no
credentials are configured). Phase 9 added WhatsApp/email notification adapters (Twilio/Meta
WhatsApp, SendGrid email, each with a mock fallback) for appointment confirmation, cancellation,
rescheduling, and clinic/receptionist notification, with per-attempt delivery tracking and
duplicate-notification prevention. Phase 10 added human Receptionist escalation: five transfer
triggers (caller request, repeated misunderstanding, unsupported request, clinic-configured
keyword rule, technical failure), each recording a `HumanHandoff` row (reason, conversation
context, call state, timestamp) before attempting a live Twilio/Vapi call transfer where one is
possible. Phase 11 built a premium staff dashboard (12 pages, HTML5/CSS3/vanilla JS, no
frameworks). Phase 12 connected that dashboard to the real backend (auth, leads, patients,
appointments, calls/transcripts, team) via a reusable API service layer, with loading/error/empty
states and auth-expiry handling; pages with no backend endpoint yet (AI Receptionist settings,
Integrations, Automations) stay clearly-labeled previews rather than a fake connection. Phase 13
added tracked metrics (calls, leads, appointments, conversion/resolution rates, transfers,
integration failures) via a real `/analytics/summary` endpoint wired into the dashboard, structured
JSON logging with request/call/workspace correlation IDs, audit logs, and integration logs. Phase
14 was a security audit: Twilio webhook signature verification (previously unenforced), a signed
short-lived token gating the WebSocket stream endpoint, closed tenant-isolation/IDOR gaps on
appointment creation, tightened input validation, rate limiting on the unauthenticated endpoints
that can actually be reached, a request body size cap, secure-by-default config (refuses to start
with the insecure default `SECRET_KEY` outside development, `DEBUG` now defaults off, API docs
disabled outside development) — no healthcare regulatory compliance is claimed anywhere. Phase 15
added a true end-to-end scenario test (caller → STT → LLM → TTS → qualification → appointment →
database → calendar → WhatsApp → email → dashboard) that caught two real, previously-shipped bugs
no isolated unit test had: `NotificationService` was never actually wired into the booking flow,
and a real `asyncio`/thread concurrency race in the voice pipeline — both fixed, plus a
`dateparser` bug that mis-resolved certain weekday-name phrases. Phase 16 prepared the app for
production: split liveness/readiness health checks, a `Dockerfile` + `docker-compose.yml`, a
configurable frontend backend URL (previously hardcoded to localhost), and a full deployment guide
(`docs/deployment.md`) covering AWS/GCP/DigitalOcean (backend) and Vercel/Netlify (frontend) — see
that document for exactly what was and wasn't verified locally.

See `docs/` for further documentation as the project grows.
