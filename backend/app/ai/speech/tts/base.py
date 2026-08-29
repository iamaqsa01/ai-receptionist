from abc import ABC, abstractmethod


class TextToSpeechProvider(ABC):
    """Every TTS backend (ElevenLabs, mock, ...) implements this same
    interface. The call-session orchestrator only ever talks to this
    abstraction — never a provider SDK directly."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        """Returns audio bytes for the given text."""
