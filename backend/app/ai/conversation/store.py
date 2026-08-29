import uuid
from abc import ABC, abstractmethod

from app.ai.conversation.state import ConversationState


class ConversationStore(ABC):
    """Where in-progress conversation sessions live. Abstracted so the
    in-memory implementation used today (single-process, non-durable) can be
    swapped for a shared/durable one (Redis, a DB table) later without
    touching the conversation engine or the API layer."""

    @abstractmethod
    def create(self, workspace_id: uuid.UUID) -> ConversationState: ...

    @abstractmethod
    def get(self, session_id: uuid.UUID) -> ConversationState | None: ...

    @abstractmethod
    def save(self, state: ConversationState) -> None: ...


class InMemoryConversationStore(ConversationStore):
    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, ConversationState] = {}

    def create(self, workspace_id: uuid.UUID) -> ConversationState:
        state = ConversationState(session_id=uuid.uuid4(), workspace_id=workspace_id)
        self._sessions[state.session_id] = state
        return state

    def get(self, session_id: uuid.UUID) -> ConversationState | None:
        return self._sessions.get(session_id)

    def save(self, state: ConversationState) -> None:
        self._sessions[state.session_id] = state


# Process-wide default store. A single clinic's AI Receptionist can run
# many concurrent calls; this holds them all for the life of the process.
default_conversation_store = InMemoryConversationStore()
