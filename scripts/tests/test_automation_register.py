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
    assert out.index("Failing now") < out.index("| Job | Owner | Schedule")


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
    assert row.count("|") == 6, f"description leaked a pipe into the row: {row}"


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


def _fake_cron_db(empire_rows, tenant_rows=()):
    """Minimal stand-in for the Turso client collect_cron() talks to."""
    from types import SimpleNamespace

    class FakeQ:
        def __init__(self, rows): self._r = list(rows)
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return SimpleNamespace(data=self._r)

    class FakeDb:
        def table(self, name):
            return FakeQ(empire_rows if name == "cron_jobs" else tenant_rows)

    return FakeDb()


def _seed_row(seed, **over):
    row = {
        "id": seed["name"], "name": seed["name"], "is_active": 1,
        "schedule": seed["schedule"], "action_type": seed["action_type"],
        "action_config": seed["action_config"],
        "owner_agent_key": seed.get("owner_agent_key") or "bravo",
        "last_result": "ok", "last_run_at": "2026-09-16T00:00:00Z", "fail_count": 0,
    }
    row.update(over)
    return row


def test_live_collector_gates_on_the_seed_inventory_contract(monkeypatch):
    """The daily register must not bless a plausible partial cron list.

    This was four `in source` string assertions, which pass against a guard that
    has been gutted — put `audit_live_inventory(rows)` behind `if False:`, or
    discard `contract_error` at the return, and the register happily writes
    "4 active jobs" and exits 0 while every substring is still in the file.
    Exercise the collector instead.
    """
    sys.path.insert(0, str(REPO / "scripts" / "core"))
    import cron_engine

    seeds = cron_engine.SEED_JOBS
    monkeypatch.setattr(
        ga, "is_self_scored_failure", lambda _r: False, raising=False,
    )

    # Complete registry -> no contract error.
    full = _fake_cron_db([_seed_row(s) for s in seeds])
    monkeypatch.setattr("integrations.supabase_tool.get_client", lambda _e: full)
    monkeypatch.setattr("lib.secret_loader.load_env", lambda *a, **k: {})
    rows, err = ga.collect_cron()
    assert err is None, f"a complete registry must not report a contract error: {err}"
    assert len(rows) == len(seeds)

    # The outage: all but one declared job vanishes -> contract error, loudly.
    thin = _fake_cron_db([_seed_row(seeds[0])])
    monkeypatch.setattr("integrations.supabase_tool.get_client", lambda _e: thin)
    rows, err = ga.collect_cron()
    assert err and err.startswith("inventory contract failed"), (
        "collect_cron blessed a registry missing every declared job but one — "
        f"the inventory gate is not wired into the return value (got {err!r})"
    )

    # A repairable field drift must NOT claim the source was unreadable. It is
    # marked per-row instead; see the comment in collect_cron.
    drifted = _fake_cron_db(
        [_seed_row(s, schedule="59 23 31 2 *") if i == 0 else _seed_row(s)
         for i, s in enumerate(seeds)]
    )
    monkeypatch.setattr("integrations.supabase_tool.get_client", lambda _e: drifted)
    rows, err = ga.collect_cron()
    assert err is None, (
        "a schedule drift turned the daily register red and stamped a false "
        f"'source was unreadable' banner into a committed brain doc: {err!r}"
    )
    assert any(r.get("drifted") for r in rows), (
        "the drifted row was neither blocked nor marked — it is now invisible"
    )


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
