# Phase 7 — Appointment Scheduling

## Scope

Availability checking, appointment creation, confirmation, cancellation, rescheduling, provider/
service selection, timezone handling, conflict detection, duplicate-booking prevention. Flow:

```
Caller request → collect information → validate → check availability → confirm with caller
→ create appointment → return result
```

Hard constraint: never tell the caller an appointment is confirmed until the backend confirms
successful creation.

## Architecture

```
app/ai/scheduling/
  rules.py       Pure overlap/conflict logic + as_aware_utc() timezone normalization
  outcomes.py    BookingOutcome enum — the only vocabulary the engine is allowed to
                 base a "confirmed"/"cancelled"/"rescheduled" reply on

app/ai/nlu/confirmation.py   Rule-based, multilingual yes/no classifier (no LLM)
```

Everything else is targeted changes to existing Phase 4–6 files: `conversation/state.py`
(`pending_booking_confirmation`, `AppointmentDraft.provider`), `conversation/effects.py`
(`BookAppointmentEffect.provider`, unchanged `Cancel`/`RescheduleAppointmentEffect`),
`conversation/instructions.py` (`WorkspaceAIProfile.providers`, `.timezone`, loaded from the
already-existing `Provider` table and `Workspace.timezone` column), `conversation/engine.py` (the
confirm-then-create flow + `render_*_outcome` methods), `receptionist_service.py` (availability/
conflict/duplicate checking, all outcome-aware), `nlu/entities.py` (`extract_provider`,
timezone-aware `extract_datetime`), and four new language-catalog template keys.

## The confirm-with-caller gate

Once every requirement is collected and validated (name, phone, service, provider if the
workspace has any configured, date/time), `ConversationEngine._handle_booking` does **not**
emit a `BookAppointmentEffect`. It sets `state.pending_booking_confirmation = True` and asks
"I have you down for {service} on {when} — shall I go ahead and book it?" — no database write,
no effect, nothing committed anywhere yet.

The caller's next message is routed straight to `_handle_pending_confirmation` (bypassing normal
intent classification, so "yes" is never misread as some other intent) and classified by
`classify_confirmation()`:
- **yes** → the `BookAppointmentEffect` is emitted now, but the engine's own reply for this turn
  is only `processing_request` ("One moment please.") — a deliberately honest placeholder.
- **no** → clears `appointment.when` only (name/phone/service/provider are kept) and re-asks for
  a date/time.
- **unclear** → asks "was that a yes or a no?" and stays in the pending state.

## Never confirmed before the backend confirms — how it's actually enforced

This isn't just a stated intention; it's structural. `ConversationEngine` has no database access
by design (unchanged since Phase 4), so it is *incapable* of knowing whether a write will
succeed — which is exactly why its reply for a booking/cancel/reschedule attempt is always a
placeholder, never wording that claims success. `ReceptionistService._apply_effects` runs
*synchronously* inside the same `handle_message()` call: it applies the effect (the real
database write, including availability/conflict/duplicate checks), gets back a `BookingOutcome`,
and immediately calls `ConversationEngine.render_booking_outcome()` (or `render_cancellation_
outcome` / `render_reschedule_outcome`) to produce the *actual* reply — overwriting the engine's
placeholder before it is ever spoken/sent to the caller (nothing has been transmitted to the
caller at this point; `EngineResult.reply` is just a string sitting in memory until the API/
telephony layer sends it). So the only way "confirmed" wording can ever reach a caller is via
the `BookingOutcome.CREATED` branch, which is only reached after `db.commit()` has already
succeeded.

This also **fixed a latent gap from Phase 4**: cancellation previously always replied "Done —
I've cancelled that appointment for you," even when no matching appointment existed (silently a
no-op). It's now genuinely outcome-driven — `BookingOutcome.NOT_FOUND` renders the (already
existing but previously unused) `no_appointment_found` template instead.

## Availability checking, conflict detection, duplicate-booking prevention

`app/ai/scheduling/rules.py` is pure, DB-free logic: `ranges_overlap()`, `find_overlapping()`
(returns the first overlapping booking from a candidate list, or `None`), and `as_aware_utc()`.
`ReceptionistService._book_appointment` does, in order:

1. **Duplicate-booking prevention**: look up the calling patient (by phone); if they already have
   a *scheduled* appointment overlapping the proposed time (any provider), the booking is
   rejected as `DUPLICATE` — this catches a caller accidentally booking themselves twice,
   independent of which provider either booking is with.
2. **Conflict detection**: only performed once a specific provider is pinned (not `None` or
   `"no_preference"`) — look up that provider's other scheduled appointments; an overlap is
   rejected as `CONFLICT`. **Documented limitation**: without a pinned provider there is no
   single resource to check contention against, so a "no preference" booking skips this check
   entirely (two different "no preference" callers can book the same time slot — realistic for a
   clinic with several providers, but a caller who explicitly names a provider is protected).
3. If both pass: the `Patient` is found-or-updated (Phase 6 behavior, unchanged), the `Service`/
   `Provider` rows are looked up by name and properly linked via `Appointment.service_id`/
   `provider_id` (previously only recorded in the notes text), and the `Appointment` is created.

Rescheduling reuses the same conflict check against the *new* proposed time (scoped to the
appointment's own provider, excluding the appointment being moved) — `RESCHEDULE_CONFLICT`
rejects it and asks for a different time, leaving the original appointment untouched.

## Provider/service selection

Unchanged from Phase 6 for service. Provider selection is new: if a workspace has any active
`Provider` rows, the caller is asked to pick one (or say they have no preference) as part of the
same missing-field collection loop service/datetime already use. `extract_provider()`
(`nlu/entities.py`) matches by substring against the workspace's own provider names, exactly like
`extract_service()`, plus a small multilingual "no preference" phrase list that resolves to the
sentinel string `"no_preference"` — a real, positive answer, not "still missing."

## Timezone handling

`Workspace.timezone` (already in the Phase 2 schema, e.g. `"America/New_York"`) flows into
`WorkspaceAIProfile.timezone` and from there into `extract_datetime()`'s `timezone_name`
parameter, which sets dateparser's `TIMEZONE` + `RETURN_AS_TIMEZONE_AWARE` settings — "3pm" is
interpreted as 3pm at the clinic, never the server's own timezone. Every appointment time is
normalized to aware UTC via `as_aware_utc()` immediately before comparison or persistence.

### A subtle, real bug this normalization fixed

`as_aware_utc()` treats a naive datetime as if it's already UTC. That's correct for values coming
back from SQLite (used in tests), which silently drops tzinfo on round-trip — but only if the
value that was actually **stored** was already UTC in the first place. Initially, appointment
times were stored exactly as extracted (e.g. `15:00:00-04:00`, still in the workspace's local
zone) — so SQLite would strip the offset and hand back a naive `15:00:00`, which `as_aware_utc`
then (correctly, per its own contract, but on bad input) treated as `15:00:00 UTC` — four hours
off from the real instant. Two callers booking the exact same real time with the same provider
therefore failed to conflict, because one side of the comparison was silently shifted. Fixed by
normalizing to UTC *before* the value is ever written to the database, not just before comparison
— PostgreSQL is unaffected either way (it preserves tzinfo correctly), so this only ever mattered
for the SQLite test path, but a wrong test would have hidden a real conflict-detection bug.

### A second real bug found while testing this phase: substring keyword matching

Both `_looks_like_a_date_phrase()` (the Phase-6 date-extraction pre-filter) and the new
`classify_confirmation()` checked keywords with plain `word in text` containment. That matches
`"am"` inside `"name"`, and `"no"` inside `"know"` — so the message **"My name is Patient One"**
was being sent to `dateparser` (because "name" contains "am") and hallucinated into a nonsense
date months away, silently corrupting `state.appointment.when` on a turn that never mentioned a
date at all; separately, **"I know that works"** classified as a confirmation **"no"** (because
"know" contains "no"). Both fixed by switching to `\b`-bounded regex word-boundary matching
instead of substring containment. Caught by writing multi-caller simulated-conversation tests for
this phase's conflict-detection scenario (two different callers, each introducing themselves by
name before anything else) — a good illustration of why testing multiple simulated calls in
sequence matters more than testing single flows in isolation.

## Testing

167 tests total (134 from Phases 1–6, several updated for the new confirm-then-create flow, +33
new in this phase):

- **`test_scheduling_rules.py`** (9) — pure overlap/`as_aware_utc` unit tests, no engine or DB.
- **`test_scheduling_conversation.py`** (12) — engine-level: the confirmation classifier in all
  four languages, no effect until the caller confirms, yes emits the effect (provisional reply
  only), no clears the date and keeps other info, unclear re-prompts and still works on a later
  clear answer, provider asked/not-asked depending on workspace configuration, naming a specific
  provider vs. "no preference", and timezone-anchored extraction.
- **`test_scheduling_service.py`** (12) — the five explicitly required scenarios against a real
  (SQLite) database, plus the scoping/edge cases that make them meaningful:
  - **Successful booking** — creates a real `Appointment` linked to real `Service`/`Provider` rows.
  - **Unavailable slot** — a second caller into the same provider/time is rejected, the caller is
    never told "confirmed" anywhere in the reply, and the flow recovers cleanly on a different time.
  - **Duplicate booking** — the same caller can't double-book themselves at an overlapping time
    (scoped correctly: a *different* patient at the same time, no provider pinned, is fine).
  - **Cancellation** — both the success path and the "nothing to cancel" honest-failure path.
  - **Rescheduling** — both the success path and rejecting a reschedule into an already-occupied
    slot (leaving the original appointment untouched), plus the "nothing to reschedule" path.
- Existing Phase 4–6 tests that exercised a full booking to completion were updated to send the
  new required "Yes" confirmation turn; two tests were re-scoped because lead-conversion and
  final booking-success wording moved from the engine (pre-Phase-7) to `ReceptionistService`'s
  outcome-aware path (post-Phase-7) — documented inline in each updated test.

## Out of scope (unchanged)

AI/clinical limits (Phase 4) and no dashboard functionality still apply.
