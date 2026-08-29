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


# --- duration: the question nothing could answer -----------------------------
# Added 2026-08-29. Nothing measured how long an automation takes, so "which
# one is eating the machine" was unanswerable on a box where every subprocess
# pays AV-inflated spawn cost. The first record written after the fix caught
# the inbound sweep at 301.6s against its 300s kill.

def _timings(tmp_path, monkeypatch, rows):
    import json as _json
    d = tmp_path / "state"
    d.mkdir(parents=True, exist_ok=True)
    (d / "cron_timings.jsonl").write_text(
        "\n".join(_json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(ga, "PROJECT_ROOT", tmp_path)


def test_duration_uses_the_median_not_the_mean(tmp_path, monkeypatch):
    """One 300s timeout must not make an ordinarily-fast job look permanently
    slow. Mean of these is 65s; median is 5s, and 5s is the truth about the
    typical run."""
    _timings(tmp_path, monkeypatch, [
        {"job": "Inbound Email Sweep", "seconds": s, "ok": s < 300}
        for s in (4, 5, 5, 6, 302)
    ])
    rows, err = ga.collect_timings()
    assert err is None
    row = next(r for r in rows if r["job"] == "Inbound Email Sweep")
    assert row["median"] == 5
    assert row["worst"] == 302, "the outlier must still be visible, just not as the headline"
    assert row["failures"] == 1
    assert row["runs"] == 5


def test_the_slowest_job_leads(tmp_path, monkeypatch):
    _timings(tmp_path, monkeypatch, [
        {"job": "fast", "seconds": 2, "ok": True},
        {"job": "slow", "seconds": 120, "ok": True},
    ])
    rows, _ = ga.collect_timings()
    assert [r["job"] for r in rows] == ["slow", "fast"]


def test_no_timings_yet_is_not_an_error(tmp_path, monkeypatch):
    """The scheduler may not have dispatched since timing was added. Saying so
    beats an empty section, and it must not turn the register INCOMPLETE."""
    monkeypatch.setattr(ga, "PROJECT_ROOT", tmp_path)
    rows, err = ga.collect_timings()
    assert rows == [] and err is None


def test_a_corrupt_line_does_not_lose_the_rest(tmp_path, monkeypatch):
    """This file is appended to by a live daemon; a torn write at the tail must
    not discard every measurement before it."""
    d = tmp_path / "state"
    d.mkdir(parents=True)
    (d / "cron_timings.jsonl").write_text(
        '{"job": "a", "seconds": 3, "ok": true}\n{"job": "b", "sec\n',
        encoding="utf-8")
    monkeypatch.setattr(ga, "PROJECT_ROOT", tmp_path)
    rows, err = ga.collect_timings()
    assert err is None
    assert [r["job"] for r in rows] == ["a"]


def test_the_cost_table_is_rendered_when_there_is_data(tmp_path, monkeypatch):
    _timings(tmp_path, monkeypatch, [{"job": "Slow Job", "seconds": 121, "ok": True}])
    timings, err = ga.collect_timings()
    assert err is None
    out = ga.render(_data(timings=timings))
    assert "What it costs" in out
    assert "Slow Job" in out and "121s" in out
