from app.ai.speech.tts.base import TextToSpeechProvider


class MockTTSProvider(TextToSpeechProvider):
    """Deterministic, offline stand-in for a real TTS engine: "synthesizes"
    by returning the UTF-8 bytes of the text itself, so a test can assert
    exactly what the AI Receptionist said without decoding real audio."""

    name = "mock"

    def is_available(self) -> bool:
        return True

    async def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        return text.encode("utf-8")
