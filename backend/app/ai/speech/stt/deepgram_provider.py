import asyncio
import json
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

from app.ai.speech.stt.base import STTStreamSession, SpeechToTextProvider, TranscriptResult

logger = logging.getLogger(__name__)

_DEEPGRAM_LIVE_URL = "wss://api.deepgram.com/v1/listen"


class DeepgramSTTStreamSession(STTStreamSession):
    """Wraps one Deepgram live-transcription websocket connection for the
    duration of a call. Audio is forwarded as raw binary frames; Deepgram's
    JSON results are parsed into TranscriptResult and pushed onto an
    internal queue that `transcripts()` drains.

    Written against Deepgram's documented streaming protocol
    (wss://api.deepgram.com/v1/listen, Authorization: Token <key>, binary
    audio frames in, JSON {"channel": {"alternatives": [...]}, "is_final":
    ...} results out). Not exercised against a live Deepgram connection in
    this environment (no API key available) — MockSTTProvider is what the
    test suite actually runs against.
    """

    def __init__(self, connection) -> None:
        self._connection = connection
        self._queue: asyncio.Queue[TranscriptResult | None] = asyncio.Queue()
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw_message in self._connection:
                try:
                    payload = json.loads(raw_message)
                except (TypeError, json.JSONDecodeError):
                    continue
                if payload.get("type") != "Results":
                    continue
                alternatives = payload.get("channel", {}).get("alternatives", [])
                if not alternatives:
                    continue
                text = alternatives[0].get("transcript", "")
                if not text:
                    continue
                # When started in auto-detect mode Deepgram reports the
                # language it recognised on the channel; pass it through so
                # the caller (CallSession) can react to a language switch.
                detected_language = payload.get("channel", {}).get("detected_language") or payload.get(
                    "detected_language"
                )
                await self._queue.put(
                    TranscriptResult(
                        text=text,
                        is_final=bool(payload.get("is_final")),
                        language=detected_language,
                    )
                )
        except Exception:
            logger.exception("Deepgram STT read loop failed")
        finally:
            await self._queue.put(None)

    async def send_audio(self, chunk: bytes) -> None:
        if chunk:
            await self._connection.send(chunk)

    async def transcripts(self) -> AsyncIterator[TranscriptResult]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def finish(self) -> None:
        try:
            await self._connection.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass
        finally:
            await self._connection.close()
            self._reader_task.cancel()


class DeepgramSTTProvider(SpeechToTextProvider):
    name = "deepgram"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def start_stream(
        self, *, language: str | None = None, sample_rate: int = 8000
    ) -> STTStreamSession:
        if not self._api_key:
            raise RuntimeError("Deepgram STT provider is not configured (missing API key)")

        import websockets  # imported lazily so mock mode never needs this package importable

        params = {
            "model": self._model,
            "encoding": "mulaw",
            "sample_rate": sample_rate,
            "channels": 1,
            "interim_results": "true",
            "punctuate": "true",
        }
        if language:
            params["language"] = language
        else:
            # No language yet — let Deepgram identify it from the audio and
            # report it back on each result (see _read_loop).
            params["detect_language"] = "true"

        url = f"{_DEEPGRAM_LIVE_URL}?{urlencode(params)}"
        connection = await websockets.connect(
            url, additional_headers={"Authorization": f"Token {self._api_key}"}
        )
        return DeepgramSTTStreamSession(connection)
