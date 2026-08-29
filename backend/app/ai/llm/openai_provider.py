from app.ai.llm.base import LLMMessage, LLMNotConfiguredError, LLMProvider, LLMResponse


class OpenAILLMProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = None
        if api_key:
            from openai import OpenAI  # imported lazily so mock mode never needs this package importable

            self._client = OpenAI(api_key=api_key)

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

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        return LLMResponse(content=content, raw=response)
