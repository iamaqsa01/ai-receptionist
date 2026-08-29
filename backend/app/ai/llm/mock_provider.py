from app.ai.llm.base import LLMMessage, LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Deterministic, offline stand-in for a real LLM. Used automatically
    whenever no API credentials are configured, so the AI Receptionist and
    its tests run without any external service.

    It is only used by the conversation engine as a last-resort responder
    for open-ended chit-chat (structured flows like booking/cancelling are
    handled by localized templates, not free-form generation) — so its
    replies don't need to be sophisticated, just present and safe.
    """

    name = "mock"

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int = 400,
    ) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(
            content=(
                "I'm not sure how to help with that specific request, but I can help you "
                "book, reschedule, or cancel an appointment, or connect you with our "
                f"front desk staff. (received: {last_user[:120]!r})"
            ),
            raw=None,
        )
