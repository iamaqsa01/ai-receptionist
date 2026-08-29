import uuid
from datetime import datetime

from app.ai.scheduling.rules import ranges_overlap
from app.integrations.calendar.base import CalendarEvent, CalendarProvider
from app.integrations.calendar.exceptions import CalendarAPIError


class MockCalendarProvider(CalendarProvider):
    """Deterministic, offline stand-in for a real calendar: an in-memory
    dict keyed by calendar_id, used automatically when no Google credentials
    are configured. Mirrors real Google Calendar semantics honestly —
    `create_event` does NOT itself check for conflicts (neither does
    Google's API); callers are expected to call `check_availability` first,
    exactly as CalendarSyncService does."""

    name = "mock"

    def __init__(self) -> None:
        self._events: dict[str, dict[str, CalendarEvent]] = {}

    def is_available(self) -> bool:
        return True

    def check_availability(self, calendar_id: str, start: datetime, end: datetime) -> bool:
        for event in self._events.get(calendar_id, {}).values():
            if ranges_overlap(start, end, event.start, event.end):
                return False
        return True

    def create_event(
        self, calendar_id: str, *, summary: str, description: str, start: datetime, end: datetime
    ) -> CalendarEvent:
        event = CalendarEvent(external_event_id=uuid.uuid4().hex, summary=summary, start=start, end=end)
        self._events.setdefault(calendar_id, {})[event.external_event_id] = event
        return event

    def update_event(
        self,
        calendar_id: str,
        external_event_id: str,
        *,
        start: datetime,
        end: datetime,
        summary: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        calendar = self._events.get(calendar_id, {})
        existing = calendar.get(external_event_id)
        if existing is None:
            raise CalendarAPIError(f"Event {external_event_id} not found", status_code=404)
        updated = CalendarEvent(
            external_event_id=external_event_id,
            summary=summary or existing.summary,
            start=start,
            end=end,
        )
        calendar[external_event_id] = updated
        return updated

    def cancel_event(self, calendar_id: str, external_event_id: str) -> None:
        calendar = self._events.get(calendar_id, {})
        # Idempotent, same as Google's API: cancelling an already-gone event
        # is not an error — it's already in the desired end state.
        calendar.pop(external_event_id, None)


# Process-wide default: a real calendar is one shared resource, so the mock
# must behave the same way — every booking across every request needs to
# see the same in-memory calendar, not a fresh empty one each time
# (mirrors app.ai.conversation.store.default_conversation_store).
default_mock_calendar_provider = MockCalendarProvider()
