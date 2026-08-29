from app.ai.llm.base import LLMMessage, LLMNotConfiguredError, LLMProvider, LLMResponse


class AnthropicLLMProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = None
        if api_key:
            import anthropic  # imported lazily so mock mode never needs this package importable

            self._client = anthropic.Anthropic(api_key=api_key)

    def is_available(self) -> bool:
        return self._client is not None

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int = 400,
    ) -> LLMResponse:
        if self._client is None:
            raise LLMNotConfiguredError(self.name)

        # Claude takes the system prompt as a separate top-level parameter,
        # not as a message in the conversation list.
        system_text = "\n".join(m.content for m in messages if m.role == "system") or None
        conversation = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        response = self._client.messages.create(
            model=self._model,
            system=system_text,
            messages=conversation,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return LLMResponse(content=content, raw=response)
