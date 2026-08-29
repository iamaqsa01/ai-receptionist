# Phase 5 — Real-Time Voice Pipeline

## Scope

Wire the Phase 4 AI Receptionist into an actual phone call:

```
Caller → Twilio/Vapi → WebSocket → FastAPI → Deepgram STT → AI Receptionist → ElevenLabs TTS → Twilio/Vapi → Caller
```

Twilio/Vapi adapter, WebSocket endpoint, streaming audio, Deepgram adapter, LLM adapter (reused
from Phase 4), ElevenLabs adapter, conversation state, call ID, disconnect handling, timeout
handling, error handling, logging — all behind provider interfaces, with mock adapters used
automatically when credentials aren't available. No dashboard functionality.

## Architecture

```
app/telephony/
  events.py             CallStarted / AudioChunk / CallEnded / UnknownEvent — the canonical,
                         provider-agnostic events every adapter parses its wire format into
  providers/
    base.py              TelephonyAdapter interface
    twilio_adapter.py     Twilio Media Streams (+ TwiML builder, webhook signature validation)
    vapi_adapter.py        Vapi (best-effort — see "Vapi" section below)
    mock_adapter.py         Own JSON protocol, used automatically without credentials
    factory.py               Picks adapter by TELEPHONY_PROVIDER, falls back to mock
  session.py             CallSession — the orchestrator; pure asyncio logic, no network code

app/ai/speech/
  stt/  base.py (SpeechToTextProvider + STTStreamSession), deepgram_provider.py,
        mock_provider.py, factory.py
  tts/  base.py (TextToSpeechProvider), elevenlabs_provider.py, mock_provider.py, factory.py

app/api/telephony.py     POST .../voice (Twilio webhook -> TwiML) and
                         WS .../stream/{provider}/{workspace_id} (the actual pipeline)
```

**Why `CallSession` has no websocket code**: exactly the same reasoning as `ConversationEngine`
in Phase 4 — it only depends on the `TelephonyAdapter`/`SpeechToTextProvider`/
`TextToSpeechProvider` interfaces and an injected `send` callable, so the entire pipeline (parse
→ STT → AI Receptionist → TTS → encode → send) is testable by pushing provider-shaped messages
into it directly, with no real socket, no real audio, and no real network call anywhere in the
test suite.

## Provider interfaces & mock mode

Every provider category follows the same pattern already established for the LLM in Phase 4:
an ABC, one or more real implementations (imported lazily, so mock mode never needs those SDKs
importable), a mock implementation, and a `get_*_provider()` factory that automatically falls
back to mock when the configured provider's credentials are missing (with a log warning) —
`TELEPHONY_PROVIDER`, `STT_PROVIDER`, `TTS_PROVIDER` in settings, all defaulting to `mock`. No
credentials were available in this environment, so mock adapters are what the entire test suite
actually exercises; the real Twilio/Deepgram/ElevenLabs code is written against each provider's
documented protocol but not verified against a live account/connection.

**Mock mode's trick for testing audio without audio**: `MockSTTProvider` treats each inbound
"audio chunk" as UTF-8 text and returns it straight back as a final transcript;
`MockTTSProvider` "synthesizes" a reply by returning its UTF-8 bytes. `MockTelephonyAdapter`
base64-wraps that same convention in a JSON envelope shaped like a real provider's wire protocol
(`{"event": "media", "call_id": ..., "payload": "<base64>"}`), so tests push what the caller
"said" as plain text and assert on what the AI Receptionist "said" back, while still exercising
the exact same encode/decode code path a real provider's binary audio would go through.

## Twilio adapter

Written against Twilio's documented Media Streams message shapes (`start`/`media`/`stop`/`mark`
events over the websocket Twilio opens after receiving TwiML from the voice webhook). `streamSid`
is used as the canonical call id — unlike `callSid`, it's present on every message type for the
connection. Caller/callee phone numbers aren't included in Twilio's `start` payload by default,
so `build_stream_twiml()` passes them through as `<Parameter>` custom parameters, and the adapter
reads them back out of `start.customParameters`. Audio stays mulaw @ 8kHz end-to-end in both
directions — Twilio's native format, and one both Deepgram (`encoding=mulaw`) and ElevenLabs
(`output_format=ulaw_8000`) support directly for telephony, so no resampling/transcoding is
needed anywhere in the pipeline. `verify_webhook_signature()` implements Twilio's documented
`X-Twilio-Signature` algorithm (`base64(HMAC-SHA1(auth_token, url + sorted "key"+"value" pairs))`)
for validating the initial HTTP webhook — no `twilio` SDK dependency needed for any of this, since
Media Streams is just JSON over a websocket and the signature scheme is a few lines of HMAC.

## Vapi adapter — confidence caveat

Vapi's raw-audio server transport is far less standardized in public documentation than Twilio's
Media Streams. `VapiAdapter` is a structurally-complete implementation of the same
`TelephonyAdapter` interface, modeled on Vapi's publicly documented message conventions (a
`type`-discriminated JSON envelope, a `call` object, 16kHz PCM rather than Twilio's 8kHz mulaw
since Vapi calls aren't always PSTN-originated) — but it is explicitly lower-confidence than the
Twilio adapter and has not been verified against a live Vapi account. This is called out directly
in the adapter's docstring. `MockTelephonyAdapter` is what's actually exercised end-to-end.

## Deepgram / ElevenLabs adapters

- **Deepgram** (`stt/deepgram_provider.py`): opens `wss://api.deepgram.com/v1/listen` via the
  `websockets` library (already a transitive dependency of `uvicorn[standard]` — no new package
  added), sends raw mulaw audio frames as binary websocket messages, and parses Deepgram's
  documented `{"type": "Results", "channel": {"alternatives": [{"transcript": ...}]}, "is_final":
  ...}` JSON responses into `TranscriptResult`s on a background task feeding an `asyncio.Queue`.
- **ElevenLabs** (`tts/elevenlabs_provider.py`): a single `httpx` POST to
  `/v1/text-to-speech/{voice_id}` requesting `output_format=ulaw_8000` (their telephony-ready
  format) and the `eleven_multilingual_v2` model, so replies in any Phase-4-supported language
  are voiced correctly — no ElevenLabs SDK needed, `httpx` was already a dependency.

Both are written correctly against each provider's current documented API but **not exercised
against a live connection** in this environment (no API keys available). `MockSTTProvider` /
`MockTTSProvider` are what the test suite actually runs against, per the project's established
"mock mode when credentials are unavailable" pattern.

## Conversation state & call ID

`CallSession` starts a Phase-4 `ConversationState` (via `ReceptionistService.start_session`) the
moment a `CallStarted` event arrives, and keeps the provider's own call/stream id (`call_id`)
alongside it purely for logging/correlation — the two identifiers are deliberately kept distinct
since a Twilio `streamSid` is a string like `MZ...`, not a UUID. Every final transcript is run
through the same `ReceptionistService.handle_message()` used by the Phase 4 API and test suite,
so booking/cancellation/reschedule/human-transfer/multilingual/safety behavior is identical
whether the caller is typing through the HTTP API or speaking through this pipeline — nothing
about the conversation logic itself changed in this phase.

## Disconnect / timeout / error handling

- **Disconnect**: `WebSocketDisconnect` is caught in the endpoint's receive loop; the `finally`
  block always calls `session.close()` (closes the STT stream, cancels the transcript-consumer
  task) regardless of how the loop exited.
- **Idle timeout**: `asyncio.wait_for(websocket.receive_text(), timeout=CALL_IDLE_TIMEOUT_SECONDS)`
  around each receive. On timeout, `CallSession.handle_idle_timeout()` sends a localized "could
  you repeat that?" prompt (using whatever language the call has established) and, after
  `CALL_MAX_IDLE_STRIKES` consecutive timeouts, sends a transfer-offer prompt and the endpoint
  closes the connection. Any inbound audio resets the strike counter.
- **Error handling**: a per-turn `try/except` around STT forwarding and around
  TTS synthesis (`CallSession`) means a single bad chunk or a transient provider failure is
  logged and the call continues, rather than one bad turn ending the whole call. The endpoint's
  outer `try/except Exception` catches anything unexpected, logs the full traceback, and closes
  the socket with `1011 Internal Error` instead of leaking the exception into the ASGI server
  (which would otherwise take that connection down uncleanly, or in a naive implementation,
  crash the worker).
- **Logging**: every stage is logged with `call_id=...` (and `workspace_id=...` at connection
  time) — call start (from/to/sample rate), each caller transcript, the detected intent/language
  and generated reply, idle-timeout strikes, disconnects, and call close — enough to reconstruct
  a call's timeline from logs alone.

## Testing — as far as possible without real credentials/network

100 tests total (93 from Phases 1–4 unaffected, +37 new in this phase; note the file-by-file
counts below sum to 37 across five new test files):

- `tests/test_telephony.py` (6) — full pipeline over a **real FastAPI WebSocket** connection
  (`TestClient.websocket_connect`, the standard way to test ASGI websockets — exercises the
  actual Starlette/uvicorn websocket protocol, not a bypass): a complete booking conversation
  start→media→media→...→stop; abrupt client disconnect mid-call followed by a fresh call
  proving the server kept running; an unknown `workspace_id` being rejected before `accept()`;
  call-id consistency; a malformed message not derailing the rest of the call; and the idle
  timeout escalating from a repeat-prompt to ending the call after repeated silence
  (`monkeypatch`-shortened timeout/strike settings so the test runs in under a second).
- `tests/test_telephony_session.py` (7) — `CallSession` unit tests with a recording fake `send`:
  call id capture, a full booking flow that actually persists a `Patient`/`Appointment` through
  the real `ReceptionistService`, a TTS provider that always raises (session survives, nothing
  sent for that turn), an STT provider that always raises on `send_audio` (session survives,
  logged not propagated), idempotent `close()`, audio arriving before `start` being dropped
  safely, and the idle-timeout prompt actually using the call's already-established language.
- `tests/test_telephony_providers.py` (15) — Twilio adapter parsing (start/media/stop, custom
  params, unknown events), audio round-trip encoding, webhook signature validation (valid,
  tampered, and no-auth-token-configured cases), TwiML generation; Vapi adapter parsing; and the
  provider factory's mock-fallback behavior for both Twilio and Vapi.
- `tests/test_telephony_webhook.py` (2) — the Twilio voice HTTP webhook returns TwiML containing
  the correct WebSocket URL and passed-through phone numbers; unknown workspace → 404.
- `tests/test_speech_providers.py` (7) — Deepgram/ElevenLabs provider classes raise without an
  API key and report available once one is set (construction only, no real network call); the
  STT/TTS factories fall back to mock without credentials; `MockSTTProvider` round-trips text
  correctly.

**Not yet verified** (would require real credentials/network, unavailable in this environment):
an actual call through real Twilio Media Streams, a real Deepgram websocket connection, a real
ElevenLabs synthesis request, or Vapi's actual wire format. Everything upstream and downstream of
those three network boundaries — event parsing, encoding, the full conversation flow, state
management, disconnect/timeout/error handling, and logging — is exercised end-to-end via mock
adapters, which is "as far as possible" without live credentials.

## Out of scope (per instructions)

No dashboard functionality was built in this phase.
