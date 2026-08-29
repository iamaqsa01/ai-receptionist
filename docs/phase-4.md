# Phase 4 — Core AI Receptionist Service

## Scope

The AI Receptionist as a text-level conversation service: conversation state and history, intent
detection, entity extraction, caller-information collection, the four required intents
(appointment booking, cancellation, reschedule, human transfer), missing-information handling,
workspace-specific instructions, and a genuinely multilingual architecture. An LLM abstraction
supports OpenAI and Anthropic, kept strictly separate from business logic. No AI/telephony audio
integration — no diagnosis, prescription, or clinical decision-making, ever.

## Architecture (`backend/app/ai/`)

```
llm/            LLMProvider abstraction: base.py (interface), mock/openai/anthropic providers,
                factory.py (picks provider, falls back to mock without credentials)
language/       detector.py (langdetect wrapper), catalog.py (per-language reply templates,
                extensible via register_language() — no other code changes needed)
nlu/            schema.py (Intent, ExtractedEntities), keywords.py (multilingual intent
                keywords), entities.py (phone/date/name/service extraction), safety.py
                (clinical-content guard), engine.py (NLUEngine: rule-based first, LLM-refined
                when a real provider is available)
conversation/   state.py (ConversationState/Turn/CallerInfo/AppointmentDraft), store.py
                (ConversationStore abstraction, in-memory default), instructions.py (loads a
                workspace's ai_agents.config into a WorkspaceAIProfile), effects.py (structured
                Book/Cancel/Reschedule/TransferToHuman effects), engine.py (ConversationEngine —
                the orchestrator; pure logic, no I/O)
receptionist_service.py   Façade: resolves workspace profile, runs the engine, applies effects to
                the real database (Patient/Appointment/Notification), tenant-scoped throughout.
```

**Why this split**: `ConversationEngine` never imports SQLAlchemy or an LLM SDK — it only depends
on the `LLMProvider` interface and returns structured `Effect`s. That's what makes "simulated
conversations" possible as pure in-memory unit tests (no DB, no network), and what keeps the LLM
code (`llm/`) genuinely separate from business logic (`conversation/`, `nlu/`,
`receptionist_service.py`) per the requirement.

## Conversation state & history

`ConversationState` (in-memory, per session) holds: `language`, `status`, `intent`, `caller`
(name/phone), `appointment` (service/when/new_when — a *draft*, not a DB row), `history` (every
turn, both sides), `missing_fields`. It's intentionally not a DB model: it's working memory for
one call, not a durable business record. Durable outcomes (a patient, an appointment, a
human-handoff notification) are written to the database — via the existing Phase 2/3
`Patient`/`Appointment`/`Notification` tables, fully `workspace_id`-scoped — only once a flow
actually produces one, by `receptionist_service.py`. This mirrors how a real receptionist's
short-term memory of the current call differs from the permanent chart they update afterward.

## Intent detection & entity extraction

`NLUEngine.analyze()` runs a fast, deterministic, **multilingual keyword-based classifier** first
(`nlu/keywords.py` — one dict per language; CLINICAL_REQUEST and HUMAN_TRANSFER are checked
before administrative intents, so a message mentioning both is treated as the higher-stakes
case). This is what mock mode and every test use, so behavior is stable and doesn't depend on any
network call. When a real, available LLM provider is configured, its result is *refined* by
asking the model for a JSON `{"intent": ..., "confidence": ...}` classification — if that call
fails or returns something unparseable, the rule-based result is kept, so a flaky LLM call can
never break the conversation.

Entities:
- **Phone numbers** — `phonenumbers` (Google's libphonenumber), normalized to E.164 regardless
  of the caller's language or how they said the digits.
- **Dates/times** — `dateparser`, which natively understands many languages. Preserved as real
  `datetime` objects, not text.
- **Names** — simple per-language regex patterns ("my name is X" / "me llamo X" / ...), a
  deterministic fallback that needs no LLM call; a real provider can supply better recall in the
  intent-refinement step this architecture already has a hook for.
- **Service** — substring match against the calling workspace's own `Service` names, so it's
  language-agnostic by construction (the clinic already named its services in whatever language
  it operates in).

## Multilingual requirement — how each point is met

- **No hardcoded single language**: every user-facing string, including the greeting, is looked
  up from `language/catalog.py` by a language code obtained at runtime; there is no string in the
  conversation engine that assumes English.
- **Automatic detection, respond in the same language**: `detect_language()` runs on every
  message; once established for a call, replies render in that language via the template
  catalog.
- **Natural language switching mid-call**: if the caller's message is substantial (≥5 words) and
  detected with high confidence (≥0.95) as a different, supported language, the call's language
  switches immediately.
- **Extensible without rewriting**: adding a language is one call to
  `language.catalog.register_language(...)` with a fully localized `LanguageProfile`, plus
  (optionally) an entry in `nlu/keywords.py` for faster/offline intent matching in that language.
  No changes to `ConversationEngine`, `NLUEngine`, the API layer, or any other language's code.
- **Structured info preserved across languages**: phone numbers, dates/times, and appointment
  fields are normalized (E.164, `datetime`) independent of the language they were spoken in —
  verified directly in tests (`test_appointment_datetime_is_preserved_as_structured_value_not_just_text`,
  the Spanish booking-flow test).
- **Unsupported/low-confidence handling**: a confidently-detected but workspace-unsupported
  language gets a reply (in the caller's already-established language, or the workspace's
  primary language) listing what *is* supported, plus the option to transfer to a human. Genuine
  low-confidence input asks the caller to repeat; after repeated low confidence it offers a human
  transfer instead of looping forever.
- **STT/TTS choice**: out of scope for this phase (no telephony/audio pipeline yet), but the
  architecture is built to receive plain text turns regardless of source — a future telephony
  phase only needs to feed transcribed text in and speak `EngineResult.reply` back out. langdetect
  was chosen for text-language ID (light, no model download, works offline — appropriate given
  mock mode must work without any external service); a production telephony integration would
  likely also pass STT's own detected-language hint into `ConversationEngine`, which the
  `WorkspaceAIProfile.supported_languages` gate already accommodates.

## Statistical language ID pitfalls found and fixed while testing

Short/ambiguous text is a well-known weak point for statistical language detectors, and this
surfaced repeatedly while running simulated conversations:

1. **Naive per-turn re-detection derailed slot-filling.** A short answer like "Limpieza" or a
   phone number was sometimes misdetected (even at high confidence) as an unrelated language,
   which would incorrectly flip the call into "please choose a supported language" mid-booking.
   Fixed by requiring both a substantially longer message (≥5 words) *and* very high confidence
   (≥0.95) to reconsider an already-established language — a deliberate switch reads very
   differently from a two-word answer.
2. **One- or two-word openers ("Hi", "Hola") are unreliable for first-contact language ID** — a
   bare "Hi" was once detected as Dutch with near-100% confidence. Fixed by defaulting to the
   workspace's primary configured language for very short opening messages rather than gambling
   on detection; it self-corrects on the caller's next, longer message if wrong.

## Date/time parsing pitfalls found and fixed

1. `dateparser.parse("next Tuesday at 3pm")` returned `None` outright (the "next" + weekday + "at"
   combination broke the whole-string parser), while `dateparser.parse("Tuesday at 3pm")`
   (PREFER_DATES_FROM=future) correctly resolved to the next Tuesday. Fixed by stripping
   "next"/"próximo"/"prochain"/"nächsten"-style filler words before parsing — safe, since
   `PREFER_DATES_FROM=future` already gives a bare weekday its next-occurrence meaning.
2. `dateparser.search.search_dates()` (tried as a fallback for sentences a whole-string parse
   can't handle) has a reproducible bug: any "<weekday> at 10am" phrasing resolved to a nonsense
   date months in the future ("Wednesday, October 24" instead of the actual next Wednesday),
   independent of language. Fixed by replacing it with a same-library, more reliable technique:
   plain `dateparser.parse()` on successively shorter suffixes of the message (dropping one
   leading word at a time) until one parses — this finds the same real date without invoking the
   buggy code path.
3. `search_dates` also occasionally matched a short, common word (Spanish "Mi" = "my") as a bogus
   date fragment on its own. The suffix-parse replacement above sidesteps this too, since a bare
   1–2 letter fragment essentially never parses as a date on its own.
4. **Phone numbers were being misread as dates.** `dateparser` would parse the digits in a phone
   number ("415-555-0199") into a bogus date, corrupting `appointment.when` during the
   phone-collection turn of a booking flow. Fixed by extracting the phone number first (via
   `phonenumbers.PhoneNumberMatcher`, which validates against real numbering plans) and removing
   that exact matched span before running date/name extraction — deliberately not a blunt
   "strip long digit runs" regex, since that would also eat a legitimate ISO date.

These fixes are in `app/ai/nlu/entities.py` and `app/ai/conversation/engine.py`, each with an
inline comment explaining the specific failure it addresses.

## Safety guardrail (must NOT diagnose, prescribe, or make clinical decisions)

Defense in depth, in `app/ai/nlu/safety.py`:
1. `SAFETY_SYSTEM_INSTRUCTION` is unconditionally appended to every LLM system prompt for
   open-ended replies — no workspace-configured `instructions` can remove it.
2. Incoming messages are checked against a multilingual clinical-keyword list
   (diagnose/prescribe/dosage/... and their Spanish/French/German equivalents) *before* normal
   intent routing — a match short-circuits straight to a refusal-and-offer-transfer reply.
3. Every generated reply (used for open-ended chat) is filtered by the same check before being
   returned to the caller, in case a free-form LLM completion drifts into clinical territory
   despite the system instruction.

## LLM abstraction

`LLMProvider` (`app/ai/llm/base.py`) is the only interface `NLUEngine`/`ConversationEngine` see.
`OpenAILLMProvider` and `AnthropicLLMProvider` wrap their respective SDKs (imported lazily, only
when a real API key is configured, so mock mode never needs those packages importable at all);
`MockLLMProvider` is a deterministic offline stand-in. `get_llm_provider()` selects by
`LLM_PROVIDER` and transparently falls back to mock if the matching API key is absent — the app
always runs, with or without credentials.

## Testing — simulated conversations

63 tests total (56 from Phases 1–3 unaffected, +7 in-process). New in this phase:

- `tests/test_ai_conversation.py` (16) — pure in-memory simulated conversations against
  `ConversationEngine` directly (no DB, no network): full booking/cancellation/reschedule/
  human-transfer flows, missing-information ordering, clinical refusal in English and Spanish,
  Spanish-language detection and response, mid-call language switching, short-answer language
  stability, unsupported-language handling (including a workspace configured for English only),
  and LLM-abstraction/mock-mode checks.
- `tests/test_ai_receptionist_service.py` (7) — same flows through the full façade against a real
  (SQLite, per Phase 2/3's portability layer) database: booking creates a scoped `Patient` +
  `Appointment`; cancel/reschedule mutate the right row; human transfer raises a `Notification`;
  a session created under one workspace is rejected when driven from another workspace's ID; a
  booking in one workspace is invisible when querying another's patients — the same tenant
  isolation guarantee from Phase 3, now proven for AI-driven writes too.
- `tests/test_ai_api.py` (3) — the thin HTTP layer: full session lifecycle, tenant isolation at
  the API level, and RBAC (Analyst can't drive an AI session; Owner/Admin/Receptionist can).
- `tests/test_llm_providers.py` (4) — OpenAI/Anthropic provider classes raise
  `LLMNotConfiguredError` without a key and report available once one is set, without making any
  real network call (no credentials were available in this environment).

## Out of scope (unchanged intent, updated detail)

Telephony/audio (STT/TTS wiring, real phone calls) — the conversation engine takes and returns
plain text turns by design so a later telephony phase can plug in without rewriting this one.
No diagnosis, prescription, or clinical decision-making, enforced as described above.
