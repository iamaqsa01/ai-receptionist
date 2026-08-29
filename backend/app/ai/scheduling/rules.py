"""Scheduling business rules: overlap/conflict/duplicate detection.

Pure, deterministic logic with no database access and no LLM involvement —
given a proposed time range and the set of already-booked ranges to check
against, it answers "does this overlap?". The actual database queries that
gather those existing bookings live in receptionist_service.py; keeping the
decision logic here makes it directly unit-testable without a database.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ExistingBooking:
    id: object
    start_time: datetime
    end_time: datetime


def as_aware_utc(when: datetime) -> datetime:
    """Normalizes to a timezone-aware UTC datetime.

    Appointment times are extracted timezone-aware (anchored to the
    workspace's own timezone — see nlu/entities.py), but some backends
    (SQLite, used in tests) silently drop tzinfo on round-trip through the
    database while PostgreSQL preserves it. Comparing an aware and a naive
    datetime raises a TypeError, so every datetime is normalized through
    this function before being compared or stored — a naive value is
    assumed to already be UTC (which is what actually comes back from
    SQLite, since that's what was written), not reinterpreted."""
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def ranges_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    a_start, a_end, b_start, b_end = (as_aware_utc(t) for t in (a_start, a_end, b_start, b_end))
    return a_start < b_end and b_start < a_end


def find_overlapping(
    proposed_start: datetime, proposed_end: datetime, existing: list[ExistingBooking]
) -> ExistingBooking | None:
    """Returns the first existing booking that overlaps the proposed range,
    or None if the range is clear. Used for both provider-conflict checks
    (candidates = that provider's other appointments) and duplicate-booking
    checks (candidates = this same patient's other appointments) — the
    overlap rule is identical; only which candidate set is passed in, and
    what the caller does with a hit, differs."""
    for booking in existing:
        if ranges_overlap(proposed_start, proposed_end, booking.start_time, booking.end_time):
            return booking
    return None
