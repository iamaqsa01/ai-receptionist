from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    raw: Any = None


class LLMNotConfiguredError(RuntimeError):
    """Raised when a provider is selected but has no usable credentials."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(f"LLM provider '{provider_name}' is not configured (missing API key)")
        self.provider_name = provider_name


class LLMProvider(ABC):
    """Every LLM backend (OpenAI, Anthropic, mock, ...) implements this same
    interface. Business logic (conversation engine, NLU) only ever talks to
    this abstraction — it never imports a provider SDK directly."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider is actually usable right now (e.g. has credentials)."""

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int = 400,
    ) -> LLMResponse:
        """Send a chat-style conversation and return the model's reply."""
