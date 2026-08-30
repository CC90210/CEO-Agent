"""timeutil — the four copies of "parse a stored timestamp" that had drifted.

pulse_publish and state_sync each grew their own version of the same three lines.
Three attached UTC to a naive parse; `validate()` did not — so a naive timestamp
passed schema validation and then produced a wrong age (or a TypeError on the
aware/naive subtraction) everywhere downstream. The Z-swap is the trivial half;
the tzinfo step is the half that gets dropped on the fourth copy.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.timeutil import age_days, age_hours, parse_iso_utc  # noqa: E402


def test_trailing_z_is_understood():
    got = parse_iso_utc("2026-08-03T12:00:00Z")
    assert got == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_a_naive_timestamp_comes_back_aware():
    """The asymmetry this module exists to kill. A naive parse used to flow into
    an aware subtraction — wrong answer at best, TypeError at worst."""
    got = parse_iso_utc("2026-08-03T12:00:00")
    assert got is not None and got.tzinfo is not None
    assert got == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_an_offset_is_converted_to_utc_not_just_carried():
    """The name promises UTC. Equality would pass either way (aware datetimes
    compare instants), so assert the REPRESENTATION — the first caller that
    formats `.hour` is the one that gets burned."""
    got = parse_iso_utc("2026-08-03T12:00:00+02:00")
    assert got == datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    assert got.tzinfo is timezone.utc
    assert got.hour == 10


def test_an_aware_datetime_is_also_normalized():
    from datetime import timedelta
    berlin = datetime(2026, 8, 3, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    got = parse_iso_utc(berlin)
    assert got.tzinfo is timezone.utc and got.hour == 10


@pytest.mark.parametrize("junk", [None, "", "   ", "not-a-date", 12345, {}, []])
def test_junk_returns_none_and_never_raises(junk):
    """Callers decide whether None is an error (schema check) or information (a
    sibling agent that has never published). Raising would remove that choice."""
    assert parse_iso_utc(junk) is None
    assert age_hours(junk) is None
    assert age_days(junk) is None


def test_datetime_passthrough_normalizes():
    naive = datetime(2026, 8, 3, 12, 0)
    assert parse_iso_utc(naive).tzinfo is timezone.utc
    aware = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert parse_iso_utc(aware) is aware


def test_age_helpers_agree():
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    stamp = (now - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    assert age_hours(stamp, now=now) == pytest.approx(48.0)
    assert age_days(stamp, now=now) == pytest.approx(2.0)


def test_a_naive_stamp_ages_correctly_end_to_end():
    """The concrete downstream bug: a naive `updated_at` must not read as 0d old
    (or explode) when Atlas is deciding whether Bravo's pulse has drifted."""
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert age_days("2026-07-04T12:00:00", now=now) == pytest.approx(30.0)
