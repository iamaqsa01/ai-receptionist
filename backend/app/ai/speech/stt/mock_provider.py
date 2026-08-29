import asyncio
from typing import AsyncIterator

from app.ai.speech.stt.base import STTStreamSession, SpeechToTextProvider, TranscriptResult


class MockSTTStreamSession(STTStreamSession):
    """Deterministic, offline stand-in for a real streaming STT session.

    Since there is no real audio in mock mode, each "audio chunk" pushed in
    is treated as the UTF-8-encoded text the caller said — decoded straight
    back out as a final transcript. This is what makes the whole pipeline
    (telephony adapter -> STT -> conversation engine -> TTS -> telephony
    adapter) testable end-to-end without any real audio codec or network
    call: a test can push `"Hello".encode()` and assert the AI Receptionist
    replies to the text "Hello".
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[TranscriptResult | None] = asyncio.Queue()
        self._finished = False

    async def send_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        if text.strip():
            await self._queue.put(TranscriptResult(text=text, is_final=True))

    async def transcripts(self) -> AsyncIterator[TranscriptResult]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def finish(self) -> None:
        if not self._finished:
            self._finished = True
            await self._queue.put(None)


class MockSTTProvider(SpeechToTextProvider):
    name = "mock"

    def is_available(self) -> bool:
        return True

    async def start_stream(
        self, *, language: str | None = None, sample_rate: int = 8000
    ) -> STTStreamSession:
        return MockSTTStreamSession()
