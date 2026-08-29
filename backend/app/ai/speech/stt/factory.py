import logging

from app.ai.speech.stt.base import SpeechToTextProvider
from app.ai.speech.stt.mock_provider import MockSTTProvider
from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


def get_stt_provider(cfg: Settings | None = None) -> SpeechToTextProvider:
    cfg = cfg or default_settings
    provider_name = cfg.stt_provider.lower().strip()

    if provider_name == "deepgram":
        from app.ai.speech.stt.deepgram_provider import DeepgramSTTProvider

        provider = DeepgramSTTProvider(cfg.deepgram_api_key, cfg.deepgram_model)
        if provider.is_available():
            return provider
        logger.warning("STT_PROVIDER=deepgram but DEEPGRAM_API_KEY is missing; falling back to mock STT")
        return MockSTTProvider()

    return MockSTTProvider()
