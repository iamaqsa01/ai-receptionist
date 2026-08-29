import uuid
from datetime import datetime, timedelta, timezone

from app.ai.scheduling.rules import ExistingBooking, as_aware_utc, find_overlapping, ranges_overlap


def dt(hour: int, minute: int = 0, tz: timezone | None = timezone.utc) -> datetime:
    return datetime(2026, 1, 1, hour, minute, tzinfo=tz)


def test_ranges_overlap_true_for_intersecting_ranges():
    assert ranges_overlap(dt(9), dt(10), dt(9, 30), dt(11)) is True


def test_ranges_overlap_false_for_adjacent_ranges():
    # 9-10 and 10-11 touch but don't overlap.
    assert ranges_overlap(dt(9), dt(10), dt(10), dt(11)) is False


def test_ranges_overlap_false_for_disjoint_ranges():
    assert ranges_overlap(dt(9), dt(10), dt(14), dt(15)) is False


def test_ranges_overlap_handles_naive_and_aware_mix_without_raising():
    naive = datetime(2026, 1, 1, 9, 30)
    aware = dt(9)
    # Must not raise TypeError comparing naive vs aware.
    assert ranges_overlap(naive, naive + timedelta(hours=1), aware, aware + timedelta(hours=1)) is True


def test_as_aware_utc_treats_naive_as_already_utc():
    naive = datetime(2026, 1, 1, 12, 0)
    result = as_aware_utc(naive)
    assert result.tzinfo is not None
    assert result.hour == 12


def test_as_aware_utc_converts_other_timezones_to_utc():
    eastern = datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
    result = as_aware_utc(eastern)
    assert result.hour == 17  # 12:00 -05:00 == 17:00 UTC


def test_find_overlapping_returns_the_matching_booking():
    existing = [
        ExistingBooking(id=1, start_time=dt(9), end_time=dt(10)),
        ExistingBooking(id=2, start_time=dt(14), end_time=dt(15)),
    ]
    match = find_overlapping(dt(14, 30), dt(15, 30), existing)
    assert match is not None
    assert match.id == 2


def test_find_overlapping_returns_none_when_clear():
    existing = [ExistingBooking(id=1, start_time=dt(9), end_time=dt(10))]
    assert find_overlapping(dt(11), dt(12), existing) is None


def test_find_overlapping_with_empty_existing_list():
    assert find_overlapping(dt(9), dt(10), []) is None
