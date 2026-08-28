"""The inbound sweep's wall-clock budget.

The sweep is killed by scheduler.py at 300s. It was being killed repeatedly and
undiagnosably — six failures across three days with EMPTY stdout and stderr,
because the captured pipes are lost when a run is killed.

Breadcrumbs to state/email_sweep.log made it findable, and what they showed was
an arithmetic bug: the budget clock was started AFTER the Turso connect, the
IMAP login and the UNSEEN search. Measured on this machine that startup is
~41.6s (process spawn is AV-slowed to seconds and the DB connect dominates), so
a "210s budget" was really 41.6 + 210 + one in-flight message, and the job was
still killed at the wall — start 21:18:57, FAILED (timeout) recorded at
21:22:58, with backfill_done logged at 249.3s on the second clock.

The deadline is now anchored to process start, so the number means the whole run.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations import email_engine as ee  # noqa: E402

# scheduler.py:1116 kills this job here. Not imported, because the point of the
# test is that the two numbers are related and someone changing either must see
# the other.
SCHEDULER_WALL_SEC = 300

# Measured 2026-08-28 from state/email_sweep.log `startup_cost_s`: 38.5s and
# 41.6s on two runs. Rounded up, because it is AV- and network-dependent.
OBSERVED_STARTUP_SEC = 45


def test_budget_leaves_room_for_startup_and_one_in_flight_message():
    """The arithmetic that was wrong.

    budget + one admitted message must land inside the wall. The reserve is what
    the loop requires before STARTING a message, so the worst admitted case is
    budget + reserve.
    """
    worst = ee.SWEEP_BUDGET_SEC + ee.MESSAGE_RESERVE_SEC
    assert worst < SCHEDULER_WALL_SEC, (
        f"budget {ee.SWEEP_BUDGET_SEC}s + reserve {ee.MESSAGE_RESERVE_SEC}s = "
        f"{worst}s, which does not fit the {SCHEDULER_WALL_SEC}s wall")


def test_budget_is_large_enough_to_do_real_work_after_startup():
    """The other direction: a budget so tight that startup eats it would defer
    every message forever and the inbox would never drain."""
    work_window = ee.SWEEP_BUDGET_SEC - OBSERVED_STARTUP_SEC
    assert work_window > ee.MESSAGE_RESERVE_SEC, (
        f"only {work_window}s of work window after {OBSERVED_STARTUP_SEC}s startup, "
        f"which is less than the {ee.MESSAGE_RESERVE_SEC}s needed to admit ONE message")


def test_deadline_is_anchored_to_process_start_not_to_the_loop():
    """The regression itself. Anchoring after the IMAP search excludes the
    startup the budget exists to account for."""
    src = Path(ee.__file__).read_text(encoding="utf-8")
    assert "sweep_deadline = _run_started + SWEEP_BUDGET_SEC" in src, (
        "deadline no longer anchored to process start — startup is excluded again")
    assert "sweep_deadline = sweep_started + SWEEP_BUDGET_SEC" not in src


def test_every_breadcrumb_uses_one_clock():
    """Two clocks is what made a 249.3s backfill look like it started from zero,
    and is why the overrun was not obvious from the log."""
    src = Path(ee.__file__).read_text(encoding="utf-8")
    assert "_log_sweep_progress(\"loop_start\", sweep_started" not in src
    assert "_log_sweep_progress(\"backfill_done\", sweep_started" not in src


def test_startup_cost_is_recorded_so_the_budget_can_be_retuned():
    """A budget you cannot re-derive is a magic number. The run logs what
    startup actually cost, so the next person tuning this has the measurement
    rather than a guess."""
    src = Path(ee.__file__).read_text(encoding="utf-8")
    assert "startup_cost_s" in src


def test_budget_is_env_overridable_for_a_slower_machine():
    """This box's startup is AV-inflated; another machine's will differ. The
    number must be tunable without a code change."""
    src = Path(ee.__file__).read_text(encoding="utf-8")
    assert "EMPIRE_SWEEP_BUDGET_SEC" in src
    assert "EMPIRE_MESSAGE_RESERVE_SEC" in src
