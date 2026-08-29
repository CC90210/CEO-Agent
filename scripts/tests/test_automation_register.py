"""brain/AUTOMATIONS.md — the register of what actually runs.

Nothing answered "what is running?" in one place. INVENTORY.md carried counts
and drifted (it read 37 cron jobs while the live registry held 41),
fleet_health.py covered agent pulses, and the rest was spread across
cron_engine.SEED_JOBS, a PM2 manifest, a hooks config and Task Scheduler.

The property that matters most here is NOT completeness — it is that an
incomplete register says so. A register that quietly omits the cron table
because Turso blinked is worse than no register at all: it reads as "these are
all my automations" while hiding a third of them, and an operator would act on
it. Most of these tests are about that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from core import generate_automations as ga  # noqa: E402


def _data(**over):
    base = {"crons": [], "daemons": [], "hooks": {}, "os_tasks": [],
            "errors": {"cron_jobs": None, "fleet": None, "hooks": None, "os_tasks": None}}
    base.update(over)
    return base


# --- failing loud is the whole point -----------------------------------------

def test_an_unreadable_source_is_announced_not_omitted():
    out = ga.render(_data(errors={"cron_jobs": "TimeoutError: turso", "fleet": None,
                                  "hooks": None, "os_tasks": None}))
    assert "INCOMPLETE" in out
    assert "cron_jobs" in out
    assert "do not treat the sections below as complete" in out


def test_an_unreadable_source_exits_non_zero(monkeypatch, capsys):
    """The cron job must page, not silently write a partial register."""
    monkeypatch.setattr(ga, "build", lambda: _data(
        errors={"cron_jobs": "boom", "fleet": None, "hooks": None, "os_tasks": None}))
    monkeypatch.setattr(sys, "argv", ["generate_automations.py", "--dry-run"])
    assert ga.main() == 1
    assert "ERROR" in capsys.readouterr().err


def test_a_clean_run_exits_zero(monkeypatch):
    monkeypatch.setattr(ga, "build", lambda: _data())
    monkeypatch.setattr(sys, "argv", ["generate_automations.py", "--dry-run"])
    assert ga.main() == 0


def test_a_complete_register_carries_no_incomplete_banner():
    assert "INCOMPLETE" not in ga.render(_data())


# --- the content an operator actually reads ----------------------------------

def test_failing_jobs_are_surfaced_above_the_table():
    """A failure buried in row 27 of a 32-row table is a failure nobody sees."""
    out = ga.render(_data(crons=[
        {"name": "Broken Job", "active": True, "schedule": "0 * * * *", "does": "x",
         "runs": "s.py", "last_run": "2026-08-29T01:00", "failing": True, "declared": True},
    ]))
    assert "currently failing" in out
    assert out.index("Failing now") < out.index("| Job | Schedule")


def test_inactive_jobs_are_kept_but_collapsed():
    """Present, because "why isn't X running" is a real question — but not
    competing for attention with what IS running."""
    out = ga.render(_data(crons=[
        {"name": "Retired", "active": False, "schedule": "0 1 * * *", "does": "",
         "runs": "", "last_run": "", "failing": False, "declared": True},
    ]))
    assert "Retired" in out and "<details>" in out


def test_a_pipe_in_a_description_cannot_break_the_table():
    """Descriptions are free text from SEED_JOBS; one `|` would silently mangle
    a markdown row and hide a column."""
    out = ga.render(_data(crons=[
        {"name": "J", "active": True, "schedule": "* * * * *",
         "does": "does a | b | c", "runs": "s.py", "last_run": "", "failing": False,
         "declared": True}]))
    row = next(l for l in out.splitlines() if l.startswith("| J |"))
    assert row.count("|") == 5, f"description leaked a pipe into the row: {row}"


def test_daemon_states_are_visually_distinct():
    out = ga.render(_data(daemons=[
        {"name": "a", "state": "running", "ident": "a.py", "note": ""},
        {"name": "b", "state": "down", "ident": "b.py", "note": ""},
        {"name": "c", "state": "disabled", "ident": "c.py", "note": ""},
        {"name": "d", "state": "unrunnable", "ident": "d", "note": "no script"},
    ]))
    for token in ("✅", "🔴", "⏸️", "⚠️"):
        assert token in out


def test_generated_header_warns_against_hand_editing():
    out = ga.render(_data())
    assert "do not hand-edit" in out
    assert "generate_automations.py" in out


# --- staleness ---------------------------------------------------------------

def test_check_flags_a_missing_register(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ga, "OUT_PATH", tmp_path / "nope.md")
    monkeypatch.setattr(sys, "argv", ["generate_automations.py", "--check"])
    assert ga.main() == 1
    assert "missing" in capsys.readouterr().out


def test_check_passes_on_a_fresh_register(monkeypatch, tmp_path):
    p = tmp_path / "AUTOMATIONS.md"
    p.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ga, "OUT_PATH", p)
    monkeypatch.setattr(sys, "argv", ["generate_automations.py", "--check"])
    assert ga.main() == 0


def test_check_flags_a_stale_register(monkeypatch, tmp_path, capsys):
    """A register a week old is the drift it was written to remove."""
    import os
    import time
    p = tmp_path / "AUTOMATIONS.md"
    p.write_text("x", encoding="utf-8")
    old = time.time() - (ga.STALE_DAYS + 2) * 86400
    os.utime(p, (old, old))
    monkeypatch.setattr(ga, "OUT_PATH", p)
    monkeypatch.setattr(sys, "argv", ["generate_automations.py", "--check"])
    assert ga.main() == 1
    assert "old" in capsys.readouterr().out


# --- the live register --------------------------------------------------------

def test_the_committed_register_exists_and_is_non_trivial():
    p = REPO / "brain" / "AUTOMATIONS.md"
    assert p.is_file(), "brain/AUTOMATIONS.md has not been generated"
    text = p.read_text(encoding="utf-8", errors="replace")
    assert "Scheduled jobs" in text and "Daemons" in text
    assert "INCOMPLETE" not in text, (
        "the committed register was generated while a source was unreadable")
