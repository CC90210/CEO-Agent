"""Retention sweep for never-consumed agent_events rows.

Measured 2026-08-28: every one of the first 5,000 agent_events rows was
status='pending'. Nothing in the fleet moves an event to a terminal state, so
the queue is append-only in practice — 9,533 rows older than 30 days were still
waiting for a consumer that was never coming.

agent_events is also the Bravo<->APEX coordination channel and a shared audit
trail, so these tests pin the safety properties as hard as the behaviour: dry
run by default, never delete, never touch anything inside the live window, and
never guess at a row whose timestamp cannot be parsed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from core import event_retention as er  # noqa: E402


class FakeQuery:
    """Minimal supabase-py shape.

    Writes are recorded at EXECUTE time, not at .update() time: the real call is
    `.update(patch).eq("id", …).eq("status", "pending").execute()`, so the
    filters are chained AFTER the verb. Recording at .update() captured an empty
    filter set and made a correct guard look missing.
    """

    def __init__(self, rows, recorder):
        self._rows, self._rec = rows, recorder
        self._eq = {}
        self._pending_write = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def limit(self, _n):
        return self

    def update(self, patch):
        self._pending_write = ("update", patch)
        return self

    def delete(self):
        self._pending_write = ("delete", None)
        return self

    def execute(self):
        if self._pending_write:
            verb, patch = self._pending_write
            self._rec.append((verb, patch, dict(self._eq)))
            return type("R", (), {"data": []})()
        rows = [r for r in self._rows
                if all(r.get(k) == v for k, v in self._eq.items()
                       if k in ("status", "event_type"))]
        return type("R", (), {"data": rows})()


class FakeDB:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, _name):
        return FakeQuery(self.rows, self.calls)


def _row(days_old: float, etype="X", rid="1"):
    ts = datetime.now(timezone.utc) - timedelta(days=days_old)
    return {"id": rid, "event_type": etype, "status": "pending",
            "published_at": ts.isoformat(), "created_at": None}


@pytest.fixture
def db(monkeypatch):
    holder = {}

    def make(rows):
        d = FakeDB(rows)
        holder["db"] = d
        monkeypatch.setattr(er, "_client", lambda: d)
        return d
    return make


# --- safety -------------------------------------------------------------------

def test_dry_run_is_the_default_and_writes_nothing(db):
    d = db([_row(90)])
    res = er.sweep(days=30, apply=False)
    assert res["stale_found"] == 1
    assert res["marked"] == 0
    assert d.calls == [], "dry run must issue no writes"


def test_it_marks_and_never_deletes(db):
    """agent_events is a shared audit trail and the APEX coordination channel —
    deleting rows out of it is not a unilateral call."""
    d = db([_row(90)])
    er.sweep(days=30, apply=True)
    kinds = {c[0] for c in d.calls}
    assert kinds == {"update"}, f"expected only updates, got {kinds}"
    patch = d.calls[0][1]
    assert patch["status"] == er.TERMINAL == "dead"


def test_terminal_status_is_schema_valid():
    """015_v6_event_bus_extensions.sql constrains status to
    ('pending','processing','done','failed','dead')."""
    assert er.TERMINAL in {"pending", "processing", "done", "failed", "dead"}


def test_update_is_guarded_on_still_being_pending(db):
    """A consumer may claim the row between the read and the write; the update
    must not stomp a row that has since moved on."""
    d = db([_row(90)])
    er.sweep(days=30, apply=True)
    _, _, where = d.calls[0]
    assert where.get("status") == "pending"


# --- window correctness -------------------------------------------------------

def test_rows_inside_the_live_window_are_untouched(db):
    db([_row(2), _row(29.9)])
    assert er.sweep(days=30, apply=True)["stale_found"] == 0


def test_only_rows_older_than_the_cutoff_are_selected(db):
    db([_row(2, rid="new"), _row(90, rid="old")])
    res = er.sweep(days=30, apply=False)
    assert res["stale_found"] == 1


def test_undateable_rows_are_left_alone(db):
    """Never guess that a row with no usable timestamp is old."""
    db([{"id": "x", "event_type": "X", "status": "pending",
         "published_at": None, "created_at": None}])
    assert er.sweep(days=30, apply=True)["stale_found"] == 0


def test_created_at_is_used_when_published_at_is_missing(db):
    """Producers populate these inconsistently — an external producer may set
    only one, and ignoring created_at would make those rows immortal."""
    ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    db([{"id": "x", "event_type": "X", "status": "pending",
         "published_at": None, "created_at": ts}])
    assert er.sweep(days=30, apply=False)["stale_found"] == 1


def test_type_filter_restricts_the_sweep(db):
    db([_row(90, "KEEP", "1"), _row(90, "SWEEP", "2")])
    res = er.sweep(days=30, event_type="SWEEP", apply=False)
    assert res["stale_found"] == 1
    assert list(res["by_type"]) == ["SWEEP"]


@pytest.mark.parametrize("raw", [
    "2026-08-28T04:07:44+00:00",
    "2026-08-28T04:07:44Z",
    "2026-08-28 04:07:44",
])
def test_timestamp_formats_in_play_all_parse(raw):
    assert er._as_dt(raw) is not None


def test_naive_timestamps_are_treated_as_utc():
    """A naive timestamp compared against an aware cutoff raises TypeError and
    would take the whole sweep down."""
    dt = er._as_dt("2026-08-28 04:07:44")
    assert dt.tzinfo is not None
