#!/usr/bin/env python3
"""Contract suite for the scheduler's cadence maths.

Both defects here were found by driving the LIVE cron row for the Instagram DM
Closer, whose schedule is the bare form `* * * * *`:

  * parse_cron_schedule('* * * * *') returned ONE DAY. The '*/N' branch requires
    the literal '*/' prefix, so a bare '*' minute fell through to the daily
    fallback. Two consequences, both on the error path: the retry-delay cap
    `min(timedelta(minutes=5), job_period)` evaluated to 5 MINUTES — the exact
    punishment the cap exists to prevent for a */1 job — and `job_is_fast` was
    False, so the first failing tick paged CC instead of being treated as
    transient.

  * The loop slept a FLAT CHECK_INTERVAL_SECONDS after running every due job, so
    the real interval was (sum of all job runtimes) + 60s. Measured live over 12
    minutes the IG poller fired at 291s, 255s and 166s intervals against a
    schedule that reads "every minute".

Nothing here touches the database, the network or PM2: every function under test
is pure arithmetic.

Run:
    python -m pytest tests/test_scheduler_cadence.py -q
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for _p in (str(REPO_ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import scheduler  # noqa: E402


# ── the bare-star minute ────────────────────────────────────────────────────

@pytest.mark.parametrize("schedule,expected", [
    ("* * * * *", timedelta(minutes=1)),
    ("*/1 * * * *", timedelta(minutes=1)),
    ("*/5 * * * *", timedelta(minutes=5)),
    ("*/15 * * * *", timedelta(minutes=15)),
])
def test_an_every_minute_schedule_parses_as_one_minute(schedule, expected):
    assert scheduler.parse_cron_schedule(schedule) == expected


def test_the_live_ig_closer_schedule_counts_as_a_fast_job():
    """job_is_fast drives BOTH the retry-delay cap and the escalation threshold.
    Read as a daily job, one transient Zernio 502 pushed the automation serving
    two live prospects five minutes into the dark AND paged CC on attempt 1."""
    period = scheduler.parse_cron_schedule("* * * * *")

    assert period is not None
    assert period <= scheduler.FAST_JOB_PERIOD
    assert scheduler.escalation_threshold(period) == scheduler.ESCALATE_AFTER_FAST
    assert min(timedelta(minutes=5), period) == timedelta(minutes=1), (
        "the retry delay is capped at the job's own period; a 5-minute stall on "
        "a one-minute job is a punishment, not a rescue"
    )


@pytest.mark.parametrize("schedule,expected", [
    ("0 8 * * *", timedelta(hours=24)),
    ("* 8 * * *", timedelta(hours=24)),        # bare star, but hour is pinned
    ("30 6 * * MON-FRI", timedelta(hours=24)),
    ("0 9 1 * *", timedelta(days=30)),
])
def test_the_other_schedules_are_unchanged(schedule, expected):
    """The fix must be surgical: only a schedule that really means "every
    minute" may change meaning."""
    assert scheduler.parse_cron_schedule(schedule) == expected


# ── the sleep is a period, not an extra ─────────────────────────────────────

def test_the_loop_sleeps_the_remainder_of_the_interval_not_a_flat_minute():
    """A flat post-cycle sleep makes the interval additive: a cycle that spends
    47s running the IG poller and the email sweep then slept another 60s, so the
    "every minute" job ran every 107 seconds at best."""
    assert scheduler.remaining_sleep_seconds(0.0) == pytest.approx(
        scheduler.CHECK_INTERVAL_SECONDS)
    assert scheduler.remaining_sleep_seconds(47.0) == pytest.approx(
        scheduler.CHECK_INTERVAL_SECONDS - 47.0)


def test_a_cycle_that_overran_does_not_sleep_negatively_or_spin():
    """An overrun must go straight round again — but the floor keeps a
    pathological cycle from busy-spinning on the cron_jobs query."""
    assert scheduler.remaining_sleep_seconds(600.0) >= 0
    assert scheduler.remaining_sleep_seconds(600.0) <= scheduler.MIN_SLEEP_SECONDS
    assert scheduler.MIN_SLEEP_SECONDS > 0
