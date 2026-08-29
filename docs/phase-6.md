# Phase 6 — Caller Qualification

## Scope

Turn a call into a qualified booking (or a captured lead): identify intent, collect required
information, identify service/department, collect appointment requirements, create/update
patient records, create/update lead records, validate information, detect booking intent. Never
invent missing patient information. Keep business rules outside the LLM.

Most of the surrounding machinery (intent detection, entity extraction, missing-information
handling, the four booking-related intents) already existed from Phase 4 — this phase adds the
qualification-specific pieces on top of it: validation, department resolution, and lead lifecycle
management.

## Architecture

```
app/ai/qualification/
  validators.py     Pure business rules: validate_phone/name/service/future_datetime,
                     resolve_department, next_lead_status. No LLM call anywhere in this file.
```

Everything else is small, targeted additions to existing Phase 4/5 files:
`app/ai/conversation/effects.py` (`UpsertLeadEffect`, `BookAppointmentEffect.department`),
`app/ai/conversation/state.py` (`AppointmentDraft.department`), `app/ai/conversation/
instructions.py` (`WorkspaceAIProfile.service_departments`), `app/ai/conversation/engine.py`
(validation wired into entity merging, lead-effect emission), `app/ai/receptionist_service.py`
(`_upsert_lead`, patient-record update logic), and four new language-catalog template strings
(`invalid_datetime_past`, one per supported language).

## Why business rules stay outside the LLM

`app/ai/qualification/validators.py` is deliberately pure, deterministic Python with zero LLM
dependency: whether a phone number is valid, whether a name is plausible, whether a service is
one the workspace actually offers, whether a proposed time is in the past, which department a
service belongs to, and whether a lead's status is allowed to move backward are all decided by
plain functions the conversation engine calls directly. `ConversationEngine` itself only ever
consults the LLM for two things, both already true from Phase 4: refining intent classification
(and only when a real, available provider is configured — the rule-based classifier runs
regardless) and generating open-ended chit-chat replies. Neither of those paths can produce a
structured field (name/phone/service/date) or a validation/department/lead decision — those only
ever come from `qualification/validators.py` and `nlu/entities.py`'s extraction functions, run
against the caller's own words.

This is verified directly, not just by architecture: `test_qualification_decisions_are_identical
_regardless_of_llm_provider` (`tests/test_qualification_conversation.py`) runs the same simulated
call through `MockLLMProvider` and a `LyingLLMProvider` that fabricates plausible-looking caller
details in every reply, and asserts the two runs land on byte-identical service, department,
name, and phone — proving the LLM's actual output is causally irrelevant to any qualification
decision.

## Service/department identification

A workspace configures which department each service belongs to via
`ai_agents.config["service_departments"]`, e.g. `{"Cleaning": "Hygiene", "Root Canal":
"Endodontics"}` — the same "workspace-specific AI instructions" mechanism Phase 4 established for
persona/instructions and supported languages. Once a service is matched (already validated
against the workspace's actual service list — extraction only ever returns a name from that
list), `resolve_department()` looks up the department; a service with no configured mapping
simply resolves to `None`, never a guess. The resolved department flows through to the persisted
`Appointment.notes` (e.g. `"Booked via AI Receptionist (Root Canal) — Endodontics"`) for staff
visibility.

## Validation

`_merge_entities` in `ConversationEngine` now runs every extracted entity through the matching
validator before writing it into conversation state — a value that fails validation is simply
never merged in, so state only ever holds real, validated, caller-provided information:

- **Phone**: `phonenumbers.is_valid_number()` (extraction already only returns matcher-validated
  numbers, so this is defense-in-depth, not the primary gate).
- **Name**: rejects empty, implausibly short, or digits-only "names" the regex-based extractor
  might otherwise capture from noisy speech.
- **Service**: must be one of the workspace's actual offered services (an empty/unconfigured
  service list is treated as "no restriction" rather than blocking every booking).
- **Appointment date/time**: rejects anything resolving to the past. This is the one validation
  failure that gets its own dedicated reply (`invalid_datetime_past`, localized in all four
  supported languages) explaining *why* the caller's answer wasn't accepted, rather than a
  generic re-ask — e.g. "That time's already passed — could you give me a day and time in the
  future?"

### A `dateparser` false-positive found and fixed while testing

While writing multi-turn simulated calls for this phase, a message like *"My phone number is
415-555-0199, just asking about your hours"* caused the AI Receptionist to respond as if the
caller had stated a date in the past — even though they never mentioned one. Root cause: the
Phase-4 date-extraction fallback (successively shorter suffix parses via `dateparser.parse()`,
added specifically to work around an earlier `dateparser.search_dates()` bug — see
`docs/phase-4.md`) had no lower bound on what counts as "looks like a date." The single word
"hours" alone was enough for `dateparser.parse()` to hallucinate a full date/time.

Fixed with a cheap pre-filter, `_looks_like_a_date_phrase()` in `app/ai/nlu/entities.py`: before
attempting to parse at all, the (phone-stripped, filler-stripped) text must contain either a
digit or one of a small multilingual set of genuine date/time signal words (weekday names, month
names, "today/tomorrow/yesterday", "am/pm", etc. — one set per supported language). Text with
none of those signals returns `None` immediately rather than being handed to `dateparser` at all.
Verified this doesn't regress any legitimate phrasing already covered by Phase 4/5's test suite
(`next Tuesday at 3pm`, `el próximo viernes a las 10am`, `Move it to next Wednesday at 10am`,
`yesterday at 3pm`, and the bare-word-should-return-None cases like `Cleaning`/`Limpieza`) — all
re-verified after the fix, plus a new regression test for the exact failing phrase.

## Lead create/update

A caller becomes a `Lead` the moment we know how to reach them (a phone number) — chosen as the
trigger because a lead with no contact method is useless to follow up on, and because it avoids
creating a lead per keystroke before the caller has said anything identifying. Cancel/reschedule/
transfer callers are never treated as leads — they're identified *by* phone against existing
patient records, not prospects.

- **Mid-booking, still incomplete** → `status="qualifying"`.
- **Booking completes** → `status="converted"` (emitted alongside the `BookAppointmentEffect` on
  the same turn).
- **General inquiry / greeting with a known phone** (e.g. "what are your hours?") → `status="new"`.

`qualification.next_lead_status()` enforces that status only ever escalates
(`new → qualifying → converted`) — implemented as `receptionist_service._upsert_lead()` looking up
any existing lead by phone and taking `max(current, proposed)` by that ordering, so a later,
less-informative turn (or an unrelated follow-up call that only reaches "new") can never
downgrade a lead that already progressed further. Contact name/notes are still refreshed to
whatever the caller most recently said.

## Patient record update

`_find_or_create_patient` now updates an existing patient's name if a returning caller (matched
by phone) gives a different one this call, rather than only ever matching-or-creating. This
covers the common real case of a caller correcting or completing their name on a later call
(e.g. "Jane Doe" → "Jane Anne Doe").

## Never invent missing patient information

Structural guarantee, not just a rule: `_handle_open_ended`'s LLM-generated text is used **only**
as the reply string returned to the caller — it is never parsed back into `state.caller` or
`state.appointment`. Every structured field is populated exclusively by `nlu/entities.py`'s
extraction functions run against the caller's own utterance, gated by the validators above. So
even if an LLM's free-form reply fabricates a name or phone number in its prose (as a real LLM
occasionally will), that fabrication cannot become a database write.

Verified directly: `test_llm_generated_text_never_populates_structured_caller_fields` uses a fake
`LyingLLMProvider` whose every reply invents a caller name and phone number
("Sure thing! I've got you down as John Fabricated at 555-000-1111...") and asserts
`state.caller.name`/`state.caller.phone` stay `None` and no effect is produced — plus a DB-level
test (`test_no_patient_or_appointment_created_while_information_is_incomplete`) confirming no
`Patient`/`Appointment` row is ever written while required fields are still missing.

## Testing — multiple simulated calls

134 tests total (127 from Phases 1–5 unaffected — two intentionally updated for the new
lead-conversion effect a completed booking now also produces — +34 new in this phase, one shared
across test-file counts below):

- `tests/test_qualification.py` (14) — pure unit tests for every validator and `next_lead_status`,
  no engine/DB involved.
- `tests/test_qualification_conversation.py` (13) — engine-level simulated conversations: service/
  department identification (including the "no configured mapping" and "unrecognized service"
  cases), past-datetime rejection and recovery, lead-effect emission at every stage (before phone
  is known, mid-booking, on completion, on a phone-bearing general inquiry, never for
  cancellation callers), the "never invent" guardrail, and the "identical regardless of LLM
  provider" guardrail.
- `tests/test_qualification_service.py` (7) — the same qualification behavior through
  `ReceptionistService` against a real (SQLite) database: lead creation → conversion, lead status
  never downgrading across two separate calls, per-workspace lead isolation, a returning caller's
  patient record actually being updated (not duplicated), department landing in the persisted
  appointment notes, and no DB writes while information is incomplete. The capstone
  `test_multiple_simulated_calls_against_the_same_workspace` runs four independent simulated
  calls in a row against one workspace — a completed English booking, a Spanish-language inquiry
  that becomes a lead, a caller who abandons mid-flow (correctly produces nothing), and the first
  caller calling back to reschedule — and asserts the database's final state (patients,
  appointments, and lead statuses) matches exactly what each call's outcome implies, with no
  cross-call interference.

## Out of scope (unchanged)

AI engine limits from Phase 4 (no diagnosis/prescription/clinical decisions) and no dashboard
functionality still apply; this phase only adds qualification logic on top of the existing
conversation and telephony pipeline.
