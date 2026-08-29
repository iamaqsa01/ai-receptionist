import logging

from app.ai.llm.base import LLMProvider
from app.ai.llm.mock_provider import MockLLMProvider
from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


def get_llm_provider(cfg: Settings | None = None) -> LLMProvider:
    """Chooses the configured LLM provider. Falls back to the deterministic
    mock provider whenever the selected provider has no usable credentials,
    so the AI Receptionist always runs — with or without API keys."""

    cfg = cfg or default_settings
    provider_name = cfg.llm_provider.lower().strip()

    if provider_name == "openai":
        from app.ai.llm.openai_provider import OpenAILLMProvider

        provider = OpenAILLMProvider(cfg.openai_api_key, cfg.openai_model)
        if provider.is_available():
            return provider
        logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY is missing; falling back to mock LLM")
        return MockLLMProvider()

    if provider_name == "anthropic":
        from app.ai.llm.anthropic_provider import AnthropicLLMProvider

        provider = AnthropicLLMProvider(cfg.anthropic_api_key, cfg.anthropic_model)
        if provider.is_available():
            return provider
        logger.warning(
            "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is missing; falling back to mock LLM"
        )
        return MockLLMProvider()

    return MockLLMProvider()
