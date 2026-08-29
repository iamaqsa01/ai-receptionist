from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CalendarEvent:
    external_event_id: str
    summary: str
    start: datetime
    end: datetime


class CalendarProvider(ABC):
    """Every calendar backend (Google, mock) implements this same
    interface. CalendarSyncService (and, through it, ReceptionistService)
    only ever depends on this abstraction — never a provider SDK directly.
    Every method may raise one of the app.integrations.calendar.exceptions
    types; callers are expected to catch and handle each category
    distinctly rather than a bare `except Exception`."""

    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def check_availability(self, calendar_id: str, start: datetime, end: datetime) -> bool:
        """Returns True if the calendar is free for the whole [start, end) window."""

    @abstractmethod
    def create_event(
        self,
        calendar_id: str,
        *,
        summary: str,
        description: str,
        start: datetime,
        end: datetime,
    ) -> CalendarEvent: ...

    @abstractmethod
    def update_event(
        self,
        calendar_id: str,
        external_event_id: str,
        *,
        start: datetime,
        end: datetime,
        summary: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent: ...

    @abstractmethod
    def cancel_event(self, calendar_id: str, external_event_id: str) -> None: ...
