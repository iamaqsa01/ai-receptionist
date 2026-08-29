import pytest

from app.ai.llm.anthropic_provider import AnthropicLLMProvider
from app.ai.llm.base import LLMMessage, LLMNotConfiguredError
from app.ai.llm.openai_provider import OpenAILLMProvider


def test_openai_provider_unavailable_without_api_key():
    provider = OpenAILLMProvider(api_key="", model="gpt-4o-mini")
    assert provider.is_available() is False
    with pytest.raises(LLMNotConfiguredError):
        provider.complete([LLMMessage(role="user", content="hi")])


def test_anthropic_provider_unavailable_without_api_key():
    provider = AnthropicLLMProvider(api_key="", model="claude-3-5-haiku-latest")
    assert provider.is_available() is False
    with pytest.raises(LLMNotConfiguredError):
        provider.complete([LLMMessage(role="user", content="hi")])


def test_openai_provider_available_once_key_is_set():
    provider = OpenAILLMProvider(api_key="sk-fake-key-for-construction-only", model="gpt-4o-mini")
    assert provider.is_available() is True


def test_anthropic_provider_available_once_key_is_set():
    provider = AnthropicLLMProvider(api_key="sk-ant-fake-key-for-construction-only", model="claude-3-5-haiku-latest")
    assert provider.is_available() is True
