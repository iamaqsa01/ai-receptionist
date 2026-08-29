from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class TranscriptResult:
    text: str
    is_final: bool
    language: str | None = None


class STTStreamSession(ABC):
    """One open streaming speech-to-text session for the life of a call.
    Audio is pushed in as it arrives from the telephony provider; transcript
    results (interim and final) come back out via `transcripts()`."""

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    def transcripts(self) -> AsyncIterator[TranscriptResult]:
        """An async iterator of transcript results, ending when the session
        is closed (via `finish()`) or the underlying connection drops."""

    @abstractmethod
    async def finish(self) -> None:
        """Signals no more audio is coming and releases any resources
        (e.g. closes the provider's websocket)."""


class SpeechToTextProvider(ABC):
    """Every STT backend (Deepgram, mock, ...) implements this same
    interface. The call-session orchestrator only ever talks to this
    abstraction — never a provider SDK directly."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def start_stream(
        self, *, language: str | None = None, sample_rate: int = 8000
    ) -> STTStreamSession: ...
