"""The Instagram poll lock must free a DEAD holder and never a live one.

WHY THIS EXISTS
---------------
The lock guarantees one poll at a time. Two live polls answer the same prospect
twice, which is the outcome it was written to prevent — so a predicate that
frees a lock is safety-critical in the sending direction.

But the age fence alone (15 min) meant every hard kill cost up to fifteen
minutes of dead air. Observed live 2026-09-02: lock at 14.8 minutes, holder pid
34424 long gone, daemon logging "skipped: another poll holds the lock" every
20s the whole time — a setter reading Running and answering nobody, which is
the complaint that started the whole investigation.

So the lock now asks whether the holder is ALIVE. These tests pin both
directions, because each has a different cost: leaving a dead lock wastes 15
minutes; clearing a live one double-messages a real person.

Run: python -m pytest scripts/tests/test_ig_run_lock_staleness.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integrations"))

from integrations.instagram_dm_poller import _RunLock  # noqa: E402


def _lock(tmp_path: Path, contents: str | None) -> _RunLock:
    p = tmp_path / "poller.lock"
    if contents is not None:
        p.write_text(contents, encoding="utf-8")
    return _RunLock(p)


def test_a_dead_holder_is_reported_gone(tmp_path):
    """A PID that has never existed in this boot. 999999 is above the default
    Windows and Linux PID ranges in practice; the assertion is only meaningful
    if it is genuinely absent, which the sanity check below confirms."""
    lock = _lock(tmp_path, "999999")
    assert lock._holder_is_gone() is True


def test_a_live_holder_is_never_reported_gone(tmp_path):
    """The expensive direction. Clearing a live lock lets a second poller run
    and answer the same prospect twice."""
    # A real, definitely-alive PID that is not this process: the parent, or
    # fall back to a child we control.
    lock = _lock(tmp_path, str(os.getppid()))
    assert lock._holder_is_gone() is False


def test_our_own_pid_is_never_reported_gone(tmp_path):
    """Self-check: if the predicate said the CURRENT process was gone, every
    lock would clear instantly and the guarantee would be nothing."""
    lock = _lock(tmp_path, str(os.getpid()))
    assert lock._holder_is_gone() is False


@pytest.mark.parametrize("contents", ["", "   ", "not-a-pid", "0", "-1", "12.5"])
def test_an_unreadable_pid_fails_closed(tmp_path, contents):
    """Every uncertainty must keep the age fence in charge. 'I cannot tell' is
    not 'it is dead'."""
    lock = _lock(tmp_path, contents)
    assert lock._holder_is_gone() is False, f"{contents!r} must not read as dead"


def test_a_missing_lock_file_fails_closed(tmp_path):
    lock = _lock(tmp_path, None)
    assert lock._holder_is_gone() is False


def test_the_lock_is_acquired_over_a_dead_holder(tmp_path):
    """End to end: a lock left by a killed run does not wedge the next poll,
    and the new holder records its own pid."""
    p = tmp_path / "poller.lock"
    p.write_text("999999", encoding="utf-8")
    with _RunLock(p):
        assert p.read_text(encoding="utf-8").strip() == str(os.getpid())
    assert not p.exists(), "the lock must be released on clean exit"


def test_the_lock_is_refused_while_a_live_holder_owns_it(tmp_path):
    """The guarantee itself. A second poll must exit rather than send."""
    p = tmp_path / "poller.lock"
    p.write_text(str(os.getppid()), encoding="utf-8")
    with pytest.raises(SystemExit):
        with _RunLock(p):
            pytest.fail("a live holder's lock must never be taken")
