"""Tests for event_bus.drain_offline_queue — the bounded offline replay.

THE BUG THIS PINS (2026-09-01): the drain read every queued line, inserted one
at a time, and rewrote the queue file ONLY after the loop finished. Its cron row
is a `script_run`, which scheduler.py caps at 300s and kills hard. So a backlog
large enough to exceed the cap was UNRECOVERABLE — the process died mid-loop,
the rewrite never ran, and the next tick re-read the identical backlog and died
identically. One Turso outage could arm a permanent failure loop.

The fix is not "make it faster". It is: take a bounded bite, and persist
progress whether or not the run finishes. These tests assert the second half,
because that is the part a future refactor is most likely to drop.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "core"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import core.event_bus as eb  # noqa: E402


class _Exec:
    def __init__(self, sink, row):
        self._sink = sink
        self._row = row

    def execute(self):
        self._sink.append(self._row)
        return {"ok": True}


class _Table:
    def __init__(self, sink, fail_on=None):
        self._sink = sink
        self._fail_on = fail_on or set()

    def insert(self, row):
        if row.get("id") in self._fail_on:
            raise RuntimeError(f"insert refused for {row.get('id')}")
        return _Exec(self._sink, row)


class _DB:
    def __init__(self, sink, fail_on=None):
        self._sink = sink
        self._fail_on = fail_on

    def table(self, _name):
        return _Table(self._sink, self._fail_on)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    """Point the module at a temp queue file. Never the real one."""
    path = tmp_path / "events_offline.jsonl"
    monkeypatch.setattr(eb, "OFFLINE_QUEUE_PATH", path)
    return path


@pytest.fixture
def inserted(monkeypatch):
    sink: list = []
    monkeypatch.setattr(eb, "_get_database", lambda: _DB(sink))
    return sink


def _write(path, n, start=0):
    path.write_text(
        "\n".join(json.dumps({"id": i, "event_type": "t"}) for i in range(start, start + n)) + "\n",
        encoding="utf-8",
    )


def _remaining(path):
    if not path.exists():
        return []
    return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# --- the bound itself ------------------------------------------------------

def test_row_cap_stops_and_persists_the_remainder(queue, inserted):
    _write(queue, 1000)
    out = eb.drain_offline_queue(max_rows=500, budget_seconds=999)
    assert out["replayed"] == 500
    assert out["remaining"] == 500
    assert len(_remaining(queue)) == 500, "the untouched half must stay on disk"
    assert len(inserted) == 500


def test_successive_runs_resume_and_finish(queue, inserted):
    _write(queue, 1000)
    eb.drain_offline_queue(max_rows=500, budget_seconds=999)
    second = eb.drain_offline_queue(max_rows=500, budget_seconds=999)
    assert second["replayed"] == 500 and second["remaining"] == 0
    assert _remaining(queue) == []
    ids = sorted(r["id"] for r in inserted)
    assert ids == list(range(1000)), "every event must be replayed exactly once"


def test_time_budget_defers_without_dropping(queue, inserted):
    _write(queue, 50)
    out = eb.drain_offline_queue(max_rows=500, budget_seconds=0)
    assert out["replayed"] == 0
    assert len(_remaining(queue)) == 50, "a spent budget must not consume the queue"
    assert inserted == []


def test_nothing_is_lost_across_the_bound(queue, inserted):
    """The regression that mattered: the old code rewrote only after the loop,
    so a kill mid-loop lost the accounting entirely."""
    _write(queue, 30)
    eb.drain_offline_queue(max_rows=10, budget_seconds=999)
    eb.drain_offline_queue(max_rows=10, budget_seconds=999)
    eb.drain_offline_queue(max_rows=10, budget_seconds=999)
    assert sorted(r["id"] for r in inserted) == list(range(30))
    assert _remaining(queue) == []


# --- failure handling ------------------------------------------------------

def test_a_poison_row_is_kept_but_does_not_starve_fresh_work(queue, monkeypatch):
    sink: list = []
    monkeypatch.setattr(eb, "_get_database", lambda: _DB(sink, fail_on={3}))
    _write(queue, 6)
    out = eb.drain_offline_queue(max_rows=100, budget_seconds=999)
    assert out["replayed"] == 5
    assert out["failed"] == 1
    left = _remaining(queue)
    assert len(left) == 1 and json.loads(left[0])["id"] == 3
    # Failed rows are written AFTER deferred ones so a permanently-bad row
    # cannot sit at the head of the queue consuming every future budget.
    assert sorted(r["id"] for r in sink) == [0, 1, 2, 4, 5]


def test_failed_and_deferred_both_survive_one_run(queue, monkeypatch):
    sink: list = []
    monkeypatch.setattr(eb, "_get_database", lambda: _DB(sink, fail_on={0}))
    _write(queue, 10)
    out = eb.drain_offline_queue(max_rows=3, budget_seconds=999)
    # id 0 fails (not counted toward max_rows), 1..3 replay, 4..9 deferred.
    assert out["failed"] == 1
    assert out["remaining"] == len(_remaining(queue))
    ids_left = {json.loads(l)["id"] for l in _remaining(queue)}
    assert 0 in ids_left, "the failed row must be retained, not silently dropped"
    assert {4, 5, 6, 7, 8, 9} <= ids_left


# --- degenerate inputs -----------------------------------------------------

def test_missing_file_is_a_noop(queue, inserted):
    assert not queue.exists()
    assert eb.drain_offline_queue() == {"replayed": 0, "failed": 0, "remaining": 0}


def test_empty_file_is_a_noop(queue, inserted):
    queue.write_text("", encoding="utf-8")
    out = eb.drain_offline_queue()
    assert out == {"replayed": 0, "failed": 0, "remaining": 0}
    assert inserted == []


def test_blank_lines_are_not_counted_as_work(queue, inserted):
    queue.write_text('\n\n{"id": 1}\n\n', encoding="utf-8")
    out = eb.drain_offline_queue()
    assert out["replayed"] == 1 and out["remaining"] == 0


# --- the cap must leave room for teardown ----------------------------------

def test_budget_is_well_under_the_script_run_cap():
    """scheduler.py kills script_run at 300s. The budget bounds only ADMISSION;
    the last insert plus the file rewrite still have to finish after it. If
    these ever converge, the fix silently reverts to the original bug."""
    assert eb.DRAIN_BUDGET_SECONDS <= 240, "leave teardown reserve under the 300s cap"
    assert eb.DRAIN_MAX_ROWS >= 100, "too small a bite cannot clear a real backlog"
