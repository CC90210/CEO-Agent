"""A queued email that got old must never quietly leave.

WHY THIS EXISTS
---------------
dashboard_email_consumer is a DRAIN, and a drain flushes whatever accumulated
while it was stopped. On 2026-09-02 the queue held 10 rows aged 13 days to 2.5
months (oldest 2026-06-16), banked up while the consumer sat IS_LINUX-gated on
a VPS that had stopped reporting on 08-25. Starting it would have sent all ten
at real leads, quoting context from June, in the first ten seconds.

The daemon being down was the visible problem. Sending its backlog on restart
was the expensive one, and nothing in the code prevented it.

Run: python -m pytest scripts/tests/test_dashboard_email_staleness.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard_email_consumer import (  # noqa: E402
    MAX_QUEUED_AGE_HOURS,
    _queued_age_hours,
)


def _row(hours_ago: float | None, raw: str | None = None) -> dict:
    if raw is not None:
        return {"created_at": raw}
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {"created_at": ts.isoformat().replace("+00:00", "Z")}


def test_a_fresh_row_is_young():
    assert _queued_age_hours(_row(1)) < 2


def test_the_real_backlog_reads_as_ancient():
    """The oldest row actually found in the live queue."""
    age = _queued_age_hours({"created_at": "2026-06-16T18:49:07.875582+00:00"})
    assert age is not None and age > MAX_QUEUED_AGE_HOURS, age


def test_the_cap_is_measured_in_days_not_minutes():
    """A cap so tight that an overnight outage drops real mail is its own
    failure. 48h must survive a weekend."""
    assert 24 <= MAX_QUEUED_AGE_HOURS <= 168


def test_a_naive_timestamp_is_read_as_utc_not_crashed_on():
    """Some rows store '+00:00', some store 'Z', some store neither. A
    TypeError comparing naive and aware datetimes would take the whole drain
    down."""
    naive = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)
    age = _queued_age_hours({"created_at": naive.isoformat()})
    assert age is not None and 2 < age < 4, age


def test_an_unreadable_timestamp_is_not_guessed():
    """None means 'do not judge'. Reading it as fresh silently sends an ancient
    mail; reading it as ancient silently drops a live one. Both are worse than
    declining to decide."""
    assert _queued_age_hours({"created_at": "not-a-date"}) is None
    assert _queued_age_hours({"created_at": ""}) is None
    assert _queued_age_hours({}) is None


def test_the_gate_is_wired_into_the_send_path():
    """The predicate existing is not the same as the sender calling it. This is
    the difference between a guard and a decoration."""
    src = (Path(__file__).resolve().parent.parent / "dashboard_email_consumer.py").read_text(
        encoding="utf-8"
    )
    send_one = src[src.index("def _send_one("):]
    body = send_one[: send_one.index("\ndef ", 1)] if "\ndef " in send_one[1:] else send_one
    assert "_queued_age_hours(" in body, "_send_one never measures the row's age"
    assert "MAX_QUEUED_AGE_HOURS" in body, "_send_one never compares against the cap"
    assert '"stale"' in body, "_send_one has no terminal state for an over-age row"
