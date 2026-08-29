import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.ai.language.catalog import get_language
from app.ai.receptionist_service import ReceptionistService
from app.ai.speech.stt.base import SpeechToTextProvider
from app.ai.speech.tts.base import TextToSpeechProvider
from app.core.config import settings
from app.core.logging_context import bind_call_id
from app.models.call import Call
from app.telephony.events import AudioChunk, CallEnded, CallStarted, TelephonyEvent, UnknownEvent
from app.telephony.providers.base import TelephonyAdapter

logger = logging.getLogger(__name__)

SendFn = Callable[[str | bytes], Awaitable[None]]


class CallSession:
    """Orchestrates one call end-to-end:

        caller audio -> TelephonyAdapter.parse_message -> STT stream
        -> ReceptionistService (AI Receptionist) -> TTS
        -> TelephonyAdapter.encode_audio_message -> caller

    This class contains no websocket/network code of its own — it only
    knows about the TelephonyAdapter/STT/TTS interfaces and an injected
    `send` function. That's what makes it directly unit-testable: push
    provider-shaped messages in, assert on what gets "sent" back, all
    without a real WebSocket, real audio, or a real STT/TTS/LLM provider.
    """

    def __init__(
        self,
        *,
        workspace_id: uuid.UUID,
        adapter: TelephonyAdapter,
        stt: SpeechToTextProvider,
        tts: TextToSpeechProvider,
        receptionist: ReceptionistService,
        send: SendFn,
    ) -> None:
        self.workspace_id = workspace_id
        self._adapter = adapter
        self._stt = stt
        self._tts = tts
        self._receptionist = receptionist
        self._send = send

        self.call_id: str | None = None
        self._provider_call_id: str | None = None
        self._conversation_session_id: uuid.UUID | None = None
        self._stt_session = None
        # Language the STT stream is currently configured for. None = the
        # provider is auto-detecting (used until the conversation engine
        # has established a concrete language). When the engine later
        # reports a different language — the caller started in, or switched
        # to, another language — the stream is torn down and reopened with
        # the new language so transcription stays accurate (see
        # _sync_stt_language). The TTS side needs no such restart: it's
        # told the language per utterance in _handle_final_transcript.
        self._stt_language: str | None = None
        self._pending_stt_language: str | None = None
        self._sample_rate: int = 8000
        self._consumer_task: asyncio.Task | None = None
        self._closed = False
        self._idle_strikes = 0
        # The durable Call row for this session (app.models.call.Call) —
        # created on call start, finalized (status/ended_at/duration) on
        # close. None if persisting it ever fails; every other part of the
        # call must keep working regardless (see _create_call_row).
        self._call_row: Call | None = None
        self._call_started_at: datetime | None = None
        # Guards every asyncio.to_thread() call that touches
        # self._receptionist.db (_create_call_row, handle_message inside
        # _handle_final_transcript, _finalize_call_row): a plain SQLAlchemy
        # Session is not safe to use from two threads at once, and
        # cancelling the asyncio Task awaiting a to_thread() call does NOT
        # stop the underlying thread if it has already started (a
        # documented asyncio/executor limitation) — so close() racing an
        # in-flight transcript-processing call (e.g. a caller hangs up the
        # instant after saying "yes", right as the booking/calendar/
        # notification writes for that turn are still running) could
        # previously corrupt the session (SQLAlchemy
        # IllegalStateChangeError), reproduced directly while building
        # Phase 15's end-to-end test. Holding this lock for the duration
        # of each to_thread() call serializes them at the asyncio level,
        # which cancellation can't bypass the way it can with threads.
        self._db_lock = asyncio.Lock()

    # -- inbound dispatch --------------------------------------------------

    async def handle_raw_message(self, raw: str | bytes) -> None:
        event = self._adapter.parse_message(raw)
        await self.handle_event(event)

    async def handle_event(self, event: TelephonyEvent) -> None:
        # Bound for structured logging (app.core.logging_context) even on
        # the very first (CallStarted) event, where self.call_id isn't set
        # yet — every event type carries its own call_id.
        with bind_call_id(getattr(event, "call_id", None) or self.call_id):
            if isinstance(event, CallStarted):
                await self._on_call_started(event)
            elif isinstance(event, AudioChunk):
                await self._on_audio_chunk(event)
            elif isinstance(event, CallEnded):
                await self._on_call_ended(event)
            elif isinstance(event, UnknownEvent):
                logger.debug("call_id=%s ignoring unrecognized telephony message", self.call_id)

    async def _on_call_started(self, event: CallStarted) -> None:
        self.call_id = event.call_id
        self._provider_call_id = event.provider_call_id or event.call_id
        state = self._receptionist.start_session(self.workspace_id)
        self._conversation_session_id = state.session_id
        # Off the event loop, same reason _handle_final_transcript below
        # runs receptionist.handle_message() via to_thread: this shares
        # self._receptionist.db with the transcript-consumer task, and
        # SQLAlchemy sessions aren't safe to touch from two threads/tasks
        # concurrently — see self._db_lock.
        async with self._db_lock:
            await asyncio.to_thread(self._create_call_row, event)

        logger.info(
            "call_id=%s workspace_id=%s call started (from=%s to=%s sample_rate=%s)",
            self.call_id,
            self.workspace_id,
            event.from_number,
            event.to_number,
            event.sample_rate,
        )

        self._sample_rate = event.sample_rate
        # Start with the provider auto-detecting the caller's language; the
        # conversation engine narrows it down from the first transcripts
        # and _sync_stt_language reconfigures the stream once it has.
        self._stt_session = await self._stt.start_stream(
            language=self._stt_language, sample_rate=event.sample_rate
        )
        self._consumer_task = asyncio.create_task(self._consume_transcripts())

    def _create_call_row(self, event: CallStarted) -> None:
        # `started_at` is cached on the session (self._call_started_at)
        # rather than re-read off the ORM object later: the session's
        # default expire_on_commit=True means every attribute would
        # otherwise be re-fetched from the DB on next access, and SQLite
        # (used in tests) silently drops tzinfo on round-trip — the same
        # naive/aware pitfall app.ai.scheduling.rules works around by
        # never reading a datetime field back after a commit.
        started_at = datetime.now(timezone.utc)
        try:
            call = Call(
                workspace_id=self.workspace_id,
                conversation_session_id=self._conversation_session_id,
                direction="inbound",
                from_number=event.from_number,
                to_number=event.to_number,
                status="in_progress",
                started_at=started_at,
            )
            self._receptionist.db.add(call)
            self._receptionist.db.commit()
            self._call_row = call
            self._call_started_at = started_at
        except Exception:
            logger.exception("call_id=%s failed to create Call row", self.call_id)
            self._receptionist.db.rollback()
            self._call_row = None
            self._call_started_at = None

    def _finalize_call_row(self) -> None:
        if self._call_row is None:
            return
        try:
            ended_at = datetime.now(timezone.utc)
            self._call_row.status = "completed"
            self._call_row.ended_at = ended_at
            if self._call_started_at is not None:
                self._call_row.duration_seconds = int((ended_at - self._call_started_at).total_seconds())
            self._receptionist.db.add(self._call_row)
            self._receptionist.db.commit()
        except Exception:
            logger.exception("call_id=%s failed to finalize Call row", self.call_id)
            self._receptionist.db.rollback()

    async def _on_audio_chunk(self, event: AudioChunk) -> None:
        if self._stt_session is None:
            logger.warning("call_id=%s received audio before call start; dropping", event.call_id)
            return
        # A language change the conversation engine settled on last turn is
        # applied here (on the event loop, between chunks) rather than from
        # inside the transcript consumer task, which can't safely tear
        # itself down.
        if self._pending_stt_language and self._pending_stt_language != self._stt_language:
            await self._restart_stt(self._pending_stt_language)
        self._idle_strikes = 0
        try:
            await self._stt_session.send_audio(event.payload)
        except Exception:
            # A transient STT connection hiccup shouldn't take the whole
            # call down — log it and keep the session alive for the next
            # chunk (mirrors the TTS failure handling below).
            logger.exception("call_id=%s failed to forward audio to STT", self.call_id)

    async def _restart_stt(self, language: str) -> None:
        """Reopen the STT stream configured for `language`. Used when the
        caller starts in — or switches to — a language different from the
        one the stream was opened for. Best-effort: on any failure the
        existing stream is left in place."""
        if self._closed:
            return
        old_session = self._stt_session
        old_consumer = self._consumer_task
        try:
            new_session = await self._stt.start_stream(language=language, sample_rate=self._sample_rate)
        except Exception:
            logger.exception("call_id=%s failed to restart STT for language=%s; keeping current stream", self.call_id, language)
            return

        self._stt_session = new_session
        self._stt_language = language
        self._pending_stt_language = None
        self._consumer_task = asyncio.create_task(self._consume_transcripts())
        logger.info("call_id=%s STT stream reconfigured for language=%s", self.call_id, language)

        if old_consumer is not None:
            old_consumer.cancel()
        if old_session is not None:
            try:
                await old_session.finish()
            except Exception:
                logger.debug("call_id=%s error finishing previous STT session", self.call_id, exc_info=True)

    async def _on_call_ended(self, event: CallEnded) -> None:
        logger.info("call_id=%s call ended by provider", event.call_id)
        await self.close()

    # -- transcript -> AI Receptionist -> TTS -> caller ----------------------

    async def _consume_transcripts(self) -> None:
        try:
            async for result in self._stt_session.transcripts():
                if not result.is_final or not result.text.strip():
                    continue
                await self._handle_final_transcript(result.text)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("call_id=%s transcript consumer failed", self.call_id)

    async def _handle_final_transcript(self, text: str) -> None:
        logger.info("call_id=%s caller said: %r", self.call_id, text)
        try:
            # ReceptionistService uses a synchronous SQLAlchemy session (same
            # as the rest of this codebase); running it in a thread keeps
            # the DB round-trip from blocking this event loop, which also
            # has to keep servicing the websocket for other calls.
            # self._db_lock (not just this method's own sequential await)
            # is what stops this from ever overlapping _create_call_row /
            # _finalize_call_row on the same session — see its docstring.
            async with self._db_lock:
                engine_result = await asyncio.to_thread(
                    self._receptionist.handle_message,
                    self.workspace_id,
                    self._conversation_session_id,
                    text,
                    telephony_adapter=self._adapter,
                    provider_call_id=self._provider_call_id,
                )
        except Exception:
            logger.exception("call_id=%s AI Receptionist failed to handle message", self.call_id)
            return

        logger.info(
            "call_id=%s intent=%s language=%s reply=%r",
            self.call_id,
            engine_result.state.intent,
            engine_result.state.language,
            engine_result.reply,
        )

        # If the conversation engine has established (or the caller has
        # switched to) a language the STT stream isn't configured for, flag
        # it — the actual stream restart happens in _on_audio_chunk.
        established_language = engine_result.state.language
        if established_language and established_language != self._stt_language:
            self._pending_stt_language = established_language

        try:
            audio = await self._tts.synthesize(engine_result.reply, language=engine_result.state.language)
        except Exception:
            logger.exception("call_id=%s TTS synthesis failed", self.call_id)
            return

        await self._send(self._adapter.encode_audio_message(self.call_id, audio))

    # -- timeout handling ------------------------------------------------------

    async def handle_idle_timeout(self) -> bool:
        """Called by the WebSocket endpoint when no inbound message has
        arrived within the idle window. Nudges the caller, or — after
        repeated silence — ends the call. Returns True if the call should
        be closed."""
        if self.call_id is None:
            return False  # call hasn't started yet; nothing to nudge

        with bind_call_id(self.call_id):
            return await self._handle_idle_timeout()

    async def _handle_idle_timeout(self) -> bool:
        self._idle_strikes += 1
        language = None
        if self._conversation_session_id is not None:
            state = self._receptionist.store.get(self._conversation_session_id)
            language = state.language if state else None
        language = language or "en"
        catalog = get_language(language) or get_language("en")

        should_close = self._idle_strikes >= settings.call_max_idle_strikes
        template_key = "low_confidence_offer_transfer" if should_close else "low_confidence_repeat"
        text = catalog.templates[template_key]

        logger.info(
            "call_id=%s idle timeout (strike %s/%s)%s",
            self.call_id,
            self._idle_strikes,
            settings.call_max_idle_strikes,
            " — ending call" if should_close else "",
        )

        try:
            audio = await self._tts.synthesize(text, language=language)
            await self._send(self._adapter.encode_audio_message(self.call_id, audio))
        except Exception:
            logger.exception("call_id=%s failed to send idle-timeout prompt", self.call_id)

        return should_close

    # -- lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        with bind_call_id(self.call_id):
            if self._stt_session is not None:
                try:
                    await self._stt_session.finish()
                except Exception:
                    logger.exception("call_id=%s error finishing STT session", self.call_id)

            if self._consumer_task is not None:
                self._consumer_task.cancel()
                try:
                    await self._consumer_task
                except (asyncio.CancelledError, Exception):
                    pass

            async with self._db_lock:
                await asyncio.to_thread(self._finalize_call_row)

        logger.info("call_id=%s session closed", self.call_id)
