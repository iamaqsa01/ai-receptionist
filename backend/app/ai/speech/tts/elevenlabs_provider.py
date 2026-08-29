import logging

import httpx

from app.ai.speech.tts.base import TextToSpeechProvider

logger = logging.getLogger(__name__)

_ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class ElevenLabsTTSProvider(TextToSpeechProvider):
    """Written against ElevenLabs' documented REST TTS endpoint, requesting
    `ulaw_8000` output (their telephony-ready format, directly compatible
    with Twilio Media Streams' expected audio encoding) and the
    multilingual model so replies in any supported language are voiced
    correctly. Not exercised against a live ElevenLabs account in this
    environment (no API key available) — MockTTSProvider is what the test
    suite actually runs against.
    """

    name = "elevenlabs"

    def __init__(self, api_key: str, voice_id: str) -> None:
        self._api_key = api_key
        self._voice_id = voice_id

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        if not self._api_key:
            raise RuntimeError("ElevenLabs TTS provider is not configured (missing API key)")

        url = _ELEVENLABS_TTS_URL.format(voice_id=self._voice_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                params={"output_format": "ulaw_8000"},
                headers={"xi-api-key": self._api_key, "Accept": "audio/basic"},
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                },
            )
            response.raise_for_status()
            return response.content
