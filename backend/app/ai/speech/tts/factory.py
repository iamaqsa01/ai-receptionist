import logging

from app.ai.speech.tts.base import TextToSpeechProvider
from app.ai.speech.tts.mock_provider import MockTTSProvider
from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


def get_tts_provider(cfg: Settings | None = None) -> TextToSpeechProvider:
    cfg = cfg or default_settings
    provider_name = cfg.tts_provider.lower().strip()

    if provider_name == "elevenlabs":
        from app.ai.speech.tts.elevenlabs_provider import ElevenLabsTTSProvider

        provider = ElevenLabsTTSProvider(cfg.elevenlabs_api_key, cfg.elevenlabs_voice_id)
        if provider.is_available():
            return provider
        logger.warning(
            "TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is missing; falling back to mock TTS"
        )
        return MockTTSProvider()

    return MockTTSProvider()
