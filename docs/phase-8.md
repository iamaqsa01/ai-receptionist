# Phase 8 — Google Calendar Integration

## Scope

Availability, create event, update event, cancel event. Store external calendar event IDs.
Prevent duplicate events. Handle authentication failure, expired credentials, unavailable slots,
API errors, timeouts. Mock mode when credentials are unavailable.

## Architecture

```
app/integrations/calendar/
  base.py            CalendarProvider interface + CalendarEvent
  exceptions.py       CalendarAuthError, CalendarCredentialsExpiredError,
                       CalendarSlotUnavailableError, CalendarTimeoutError, CalendarAPIError
  mock_provider.py    In-memory calendar, used automatically without credentials
  google_provider.py  Google Calendar API v3 (service account), unverified live
  config.py           Per-workspace opt-in (reads the `integrations` table)
  sync.py             CalendarSyncService — the graceful-degradation wrapper
  factory.py           Picks provider by CALENDAR_PROVIDER, falls back to mock
```

Same pattern as every other external integration in this project (LLM, STT, TTS, telephony): an
ABC, a real implementation imported lazily, a mock implementation, and a `get_*_provider()`
factory that transparently falls back to mock when credentials are missing.

## Two-level configuration: server credentials vs. workspace opt-in

Google Calendar needs two different things, at two different scopes, and the project's existing
two-tier settings pattern (env-level provider credentials + per-workspace `ai_agents.config`) maps
onto it directly:

- **Server-level** (`.env`): `GOOGLE_SERVICE_ACCOUNT_JSON` — one Google Cloud service account for
  the whole deployment. Service-account auth was chosen over per-user OAuth because there's no
  natural "user" to consent on a phone call — the AI Receptionist automates one shared clinic
  calendar server-to-server, which is exactly what a service account is for.
- **Workspace-level** (DB): an `integrations` row (`provider="google_calendar"`,
  `is_active=True`, `config={"calendar_id": "..."}"`) — reusing the `Integration` model Phase 2
  already defined for exactly this purpose. A workspace with no such row simply never syncs;
  calendar integration is opt-in per clinic, not a hardcoded system-wide MUST-HAVE. This is why
  none of the 202 tests from Phases 1–7 needed any changes: they don't create an `integrations`
  row, so `load_calendar_integration()` returns `None` and every calendar hook in
  `ReceptionistService` becomes a no-op, exactly as before this phase existed.

## Availability, conflict detection, and where calendar fits into Phase 7's flow

Phase 7 already had internal (DB-based) conflict detection scoped to a pinned provider. This
phase adds a second, independent check: if the workspace has calendar sync configured,
`_book_appointment` (and `_reschedule_appointment` for the new time) also calls
`CalendarSyncService.check_availability()` before writing anything. This catches a real class of
bug Phase 7 couldn't: something blocked directly on the clinic's Google Calendar — a meeting, a
day off, a provider's personal event — that this system never created and has no DB row for.

The three-way return value matters: `check_availability` returns `True` (free), `False` (busy —
a genuine `CalendarSlotUnavailableError` or an availability query that succeeded and found busy
periods), or `None` (not configured, or the check itself failed for a non-fatal reason). Only
`False` is allowed to turn a booking attempt into `BookingOutcome.CONFLICT` — `None` is treated
identically to "the calendar has nothing to say," never as a reason to refuse a booking the
system's own records say is fine. This is the same principle Phase 5 used for STT/TTS failures
and Phase 7 used for the confirm-before-create gate: a third-party integration being unavailable
must degrade gracefully, never cascade into refusing service.

**Documented limitation** carried over from Phase 7: without a pinned provider there's still no
single resource (calendar) to check contention against by default — the external check is scoped
to the *workspace's* configured `calendar_id`, so it applies regardless of provider selection
(unlike the internal provider-conflict check), but two different providers sharing one calendar_id
and one workspace would still correctly conflict with each other on the external check even if
Phase 7's internal check skipped them for having no pinned provider.

## Storing external event IDs & duplicate-event prevention

`Appointment` gained two nullable columns: `external_calendar_provider` (which backend actually
created it — useful once more than one calendar provider might exist) and
`external_calendar_event_id`, with a DB-level `UNIQUE` constraint (NULLs excluded, standard SQL)
as a backstop under the application-level guard. The real guard is in
`CalendarSyncService.create_event`: it's a no-op if `appointment.external_calendar_event_id` is
already set — an appointment is synced to the calendar **at most once**, verified directly by
`test_create_event_is_never_called_twice_for_the_same_appointment` (calling `create_event` twice
for the same appointment results in exactly one call having ever reached the provider).
Rescheduling calls `update_event` (a `PATCH` on the same event id) rather than creating a new
one; cancelling calls `cancel_event` and clears the stored id, since it no longer exists anywhere
to be duplicated against.

## Error handling — five distinct failure modes

Each gets its own exception type (`exceptions.py`) so `CalendarSyncService` can react differently
per category, not with one generic `except Exception`:

| Failure | Exception | Effect on the booking |
|---|---|---|
| Authentication failure | `CalendarAuthError` | None — booking succeeds, staff notified |
| Expired credentials | `CalendarCredentialsExpiredError` | None — booking succeeds, staff notified ("please reconnect") |
| Unavailable slot | `CalendarSlotUnavailableError` | **Yes** — the one case that's a real conflict |
| API error (4xx/5xx) | `CalendarAPIError` (carries `status_code`) | None — booking succeeds, staff notified |
| Timeout | `CalendarTimeoutError` | None — booking succeeds, staff notified |

For every non-fatal category, `CalendarSyncService._report_failure` logs the full exception and
writes a `Notification` (`type="calendar_sync_error"`) with wording specific to that category —
so front-desk staff see *why* an appointment might be missing from the calendar and what to do
about it, without ever losing the booking itself or leaving the caller with a failed call.

`GoogleCalendarProvider` translates the underlying SDK's exceptions into these types: a
`socket.timeout`/`TimeoutError` → `CalendarTimeoutError`; `google.auth.exceptions.RefreshError`
(an invalidated/expired credential during token refresh) → `CalendarCredentialsExpiredError`; an
`HttpError` with status 401 or 403 → `CalendarAuthError`; a 404/410 on `cancel_event` specifically
is treated as success (already gone = already cancelled, not an error); everything else →
`CalendarAPIError` carrying the real status code. The request timeout itself is enforced via
`httplib2.Http(timeout=...)` wrapped in `google_auth_httplib2.AuthorizedHttp` — `googleapiclient`'s
`execute()` has no timeout parameter of its own; it has to be set on the underlying HTTP
transport. Written correctly against the documented API shapes but **not exercised against a
live Google account** in this environment (no credentials available) — `MockCalendarProvider` is
what the test suite actually runs against, and `_FailingProvider` test doubles
(`tests/test_calendar_sync.py`) simulate each of the five failure modes directly to prove
`CalendarSyncService` handles each one correctly without needing a real API to fail on demand.

## Testing

202 tests total (167 from Phases 1–7 unaffected, +35 new in this phase):

- **`test_calendar_mock_provider.py`** (9) — the mock provider itself: availability, create/
  update/cancel, that `create_event` doesn't itself reject overlaps (mirrors real Google
  semantics — callers must check availability first), calendars are independent per
  `calendar_id`, updating an unknown event raises, cancelling an already-gone event is idempotent.
- **`test_calendar_sync.py`** (15) — `CalendarSyncService` in isolation using `_FailingProvider`/
  `_WorkingProvider` test doubles: no-op when a workspace hasn't opted in; each of the four
  non-fatal failure categories during `create_event` is caught, doesn't touch the appointment,
  and writes a category-specific `Notification`; `CalendarSlotUnavailableError` from
  `check_availability` returns `False` (and raises no notification — a real conflict isn't a sync
  failure); the other four categories from `check_availability` return `None`; update/cancel
  failures are reported without losing the already-committed change; the happy path stores the
  external id; duplicate-create prevention (parametrized across all four failure types).
- **`test_calendar_service_integration.py`** (6) — the full AI Receptionist conversation flow
  wired to a real (SQLite) database and a real `MockCalendarProvider`: a successful booking
  actually creates a calendar event and blocks that slot; a workspace with no `integrations` row
  never touches the calendar at all; a slot blocked directly on the calendar (with no internal DB
  conflict) correctly rejects the booking; cancelling removes the calendar event and frees the
  slot; rescheduling moves the *same* event (not a new one) and frees the old slot; a simulated
  calendar outage during booking still completes the booking normally and raises a notification.
- **`test_calendar_provider_factory.py`** (5) — factory mock-fallback behavior (no provider name,
  missing credentials, invalid JSON) and `GoogleCalendarProvider` credential-gating (construction
  only, no real network call).

## Out of scope (unchanged)

AI/clinical limits (Phase 4) and no dashboard functionality still apply.
