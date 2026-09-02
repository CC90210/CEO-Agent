"""Repeat suppression in the event-bus router's observability tail.

Measured against the live bus 2026-08-29: 104,680 of 118,541 agent_events rows
(88%) were TEXTTORRENT_UNMAPPED_DID, and 2,547 of the 2,560 lines in
state/event_router.log (99.5%) were that one warning. Behind all 104,680 rows
sat exactly 12 distinct (tenant_id, destination_last4) DIDs — an external
producer re-reporting one unmapped number per inbound SMS. A log that is 99.5%
one line answers no question anyone has, so every observability claim resting on
it was untrue.

These tests pin the properties that make the fix safe rather than merely quiet,
because a warning that is silently dropped is a worse defect than the flood:

  - a repeat run costs one line plus a rollup, not N lines
  - the rollup states the withheld COUNT and the DID it belongs to
  - a genuinely new DID logs immediately, however loud its neighbours are
  - an ordinary event type keeps its per-occurrence lines up to a burst ceiling,
    because those occurrences are distinct events rather than one fact restated
  - a flood that STOPS still gets its rollup, on a tick with no rows at all
  - counters survive process restart (PM2 restarts this daemon; `once` is a
    fresh process every run) — otherwise each start re-floods from zero
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from core import event_router as er  # noqa: E402

TENANT = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Never touch the real router log, cursor or counters."""
    monkeypatch.setattr(er, "STATE_DIR", tmp_path)
    monkeypatch.setattr(er, "LOG_PATH", tmp_path / "event_router.log")
    monkeypatch.setattr(er, "CURSOR_PATH", tmp_path / "event_router.cursor")
    monkeypatch.setattr(er, "SUPPRESS_STATE_PATH", tmp_path / "event_router.suppress.json")
    yield


def _event(last4: str, message_id: str, event_type: str = "TEXTTORRENT_UNMAPPED_DID",
           severity: str = "warn") -> dict:
    """The live row shape, verified against agent_events 2026-08-29."""
    return {
        "id": message_id,
        "event_type": event_type,
        "source_agent": "unknown",
        "target_agent": "broadcast",
        "severity": severity,
        "payload": {
            "tenant_id": TENANT,
            "destination_last4": last4,
            # Unique per message — the reason whole-payload keying suppresses
            # nothing and the identity has to be declared.
            "provider_message_id": f"tt-fp:{message_id}",
        },
        "published_at": "2026-08-29T17:30:46.310Z",
        "created_at": "2026-08-29T17:30:46.310Z",
        "status": "pending",
    }


def _lines() -> list[dict]:
    if not er.LOG_PATH.exists():
        return []
    return [json.loads(ln) for ln in er.LOG_PATH.read_text(encoding="utf-8").splitlines() if ln]


def _route(events: list[dict], now: datetime, keys: dict | None = None) -> dict:
    """The row-loop half of tick(), without the Supabase client."""
    keys = _load_or(keys)
    er._sweep_suppress_windows(keys, now)
    for ev in events:
        payload = er._payload_dict(ev)
        projected = er._project(ev, payload)
        if er._admit(keys, er._suppress_key(ev, payload),
                     projected["event_type"], projected["severity"], now):
            er._log_jsonl(projected)
    er._save_suppress_state(keys)
    return keys


def _load_or(keys: dict | None) -> dict:
    return er._load_suppress_state() if keys is None else keys


# --------------------------------------------------------------------------- #
# The flood
# --------------------------------------------------------------------------- #

def test_repeat_run_costs_one_line_not_n():
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    _route([_event("2557", f"m{i}") for i in range(200)], now)

    events = [ln for ln in _lines() if ln["event_type"] == "TEXTTORRENT_UNMAPPED_DID"]
    assert len(events) == 1, f"expected 1 line for 200 repeats, got {len(events)}"


def test_rollup_names_the_did_and_the_withheld_count():
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    _route([_event("2557", f"m{i}") for i in range(200)], now)

    # The window closes; the next tick has no rows at all, which is exactly the
    # case where a naive "roll up when we see it again" would lose the count.
    _route([], now + timedelta(seconds=er.SUPPRESS_WINDOW_SEC + 1))

    rollups = [ln for ln in _lines() if ln["event_type"] == er.ROLLUP_EVENT_TYPE]
    assert len(rollups) == 1, f"expected exactly 1 rollup, got {len(rollups)}"
    assert rollups[0]["suppressed"] == 199, rollups[0]
    assert "destination_last4=2557" in rollups[0]["suppressed_key"]
    assert "199 suppressed" in rollups[0]["preview"]
    assert TENANT in rollups[0]["preview"]


def test_no_rollup_when_nothing_was_withheld():
    """A quiet key must not manufacture a rollup line — that would just be a
    second flood wearing a summary's clothes."""
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    _route([_event("2557", "m0")], now)
    _route([], now + timedelta(seconds=er.SUPPRESS_WINDOW_SEC + 1))

    assert [ln for ln in _lines() if ln["event_type"] == er.ROLLUP_EVENT_TYPE] == []


# --------------------------------------------------------------------------- #
# The signal that must survive it
# --------------------------------------------------------------------------- #

def test_a_new_did_logs_immediately_mid_flood():
    """The whole point: DID 5490 appearing for the first time is the actionable
    event, and it must not wait behind 2557's backlog."""
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    events = [_event("2557", f"m{i}") for i in range(500)]
    events.append(_event("5490", "new-did"))
    _route(events, now)

    logged = [ln["preview"] for ln in _lines()
              if ln["event_type"] == "TEXTTORRENT_UNMAPPED_DID"]
    assert any("destination_last4=5490" in p for p in logged), logged
    assert len(logged) == 2, logged  # 2557 once, 5490 once


def test_a_different_event_type_is_not_suppressed_by_the_flood():
    """Suppression is per-key. A real business event arriving during the flood is
    the thing the operator came to the log for."""
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    events = [_event("2557", f"m{i}") for i in range(100)]
    events.append(_event("2557", "lead-1", event_type="inbound.classified", severity="info"))
    _route(events, now)

    assert [ln["event_type"] for ln in _lines()].count("inbound.classified") == 1


def test_declared_recurring_and_ordinary_types_get_different_budgets():
    """A declared recurring condition is deduped to one line per identity — the
    second report of an unmapped DID says nothing the first did not. An ordinary
    type is only burst-capped, because its occurrences ARE distinct events: one
    lead opening a mail is not a restatement of the previous lead opening one.
    """
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    _route([_event("2557", f"m{i}") for i in range(50)]
           + [_event("2557", f"e{i}", event_type="BRAVO_EMAIL_OPENED", severity="info")
              for i in range(50)], now)

    kinds = Counter(ln["event_type"] for ln in _lines())
    assert kinds["TEXTTORRENT_UNMAPPED_DID"] == er.SUPPRESS_BUDGET_RECURRING == 1
    assert kinds["BRAVO_EMAIL_OPENED"] == er.SUPPRESS_BUDGET_DEFAULT == 20


def test_critical_is_never_withheld():
    """event_bus.py:166 accepts info/warn/error/critical; a critical is rare by
    construction and its one line is the entire reason it exists."""
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    _route([_event("2557", f"m{i}", severity="critical") for i in range(50)], now)

    assert len(_lines()) == 50


# --------------------------------------------------------------------------- #
# Durability
# --------------------------------------------------------------------------- #

def test_counters_survive_a_restart():
    """PM2 restarts this daemon and `once` is a fresh process per invocation. An
    in-memory-only counter would re-log the flood's first line on every start."""
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    _route([_event("2557", f"m{i}") for i in range(50)], now)
    # keys=None forces a reload from disk — the restart.
    _route([_event("2557", f"n{i}") for i in range(50)], now, keys=None)

    events = [ln for ln in _lines() if ln["event_type"] == "TEXTTORRENT_UNMAPPED_DID"]
    assert len(events) == 1, f"restart re-logged the flood: {len(events)} lines"

    keys = er._load_suppress_state()
    assert sum(e["suppressed"] for e in keys.values()) == 99


def test_corrupt_counter_file_is_loud_and_does_not_stop_routing(capsys):
    """Fail loud, keep the tail alive: a corrupt cache must not take down
    observability, and must never read as 'nothing was suppressed'."""
    er.SUPPRESS_STATE_PATH.write_text("{not json", encoding="utf-8")
    keys = er._load_suppress_state()
    assert keys == {}
    assert "suppression state unreadable" in capsys.readouterr().err


def test_malformed_entry_is_dropped_not_raised(capsys):
    er.SUPPRESS_STATE_PATH.write_text(
        json.dumps({"version": 1, "keys": {"good|src=x": {"logged": 1, "suppressed": 0,
                                                          "window_started_at": "2026-08-29T17:00:00+00:00",
                                                          "last_seen_at": "2026-08-29T17:00:00+00:00"},
                                           "bad|src=x": "not-a-dict"}}),
        encoding="utf-8")
    keys = er._load_suppress_state()
    assert list(keys) == ["good|src=x"]
    assert "dropped 1 malformed" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The wiring, not just the mechanism
# --------------------------------------------------------------------------- #

class _FakeTable:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def gt(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return type("Res", (), {"data": self._rows})()


class _FakeClient:
    """Only the row source is faked. Projection, suppression, rollup, cursor and
    log writes are all the shipping code."""
    def __init__(self, rows): self._rows = rows

    def table(self, name):
        assert name == "agent_events", name
        return _FakeTable(self._rows)


def _clock_at(offset_sec: int):
    """A datetime stand-in whose now() is shifted, so a window can be aged
    without sleeping through it."""
    class Shifted(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=offset_sec)
    return Shifted


def test_tick_itself_suppresses_and_rolls_up(monkeypatch):
    """M5 of the mutation run passed against the helper-level tests because they
    called the sweep directly — a mechanism nothing invokes is worth nothing, so
    this drives the real tick() end to end.
    """
    rows = [_event("2557", f"m{i}") for i in range(300)]
    monkeypatch.setattr(er, "_client", lambda: _FakeClient(rows))
    assert er.tick() == 300  # every row still routed, cursor still advances

    assert len(_lines()) == 1, _lines()

    # The flood stops. The window closes on a tick with NO rows at all, which is
    # where a rollup that only fired on re-sighting would lose the count.
    monkeypatch.setattr(er, "_client", lambda: _FakeClient([]))
    monkeypatch.setattr(er, "datetime", _clock_at(er.SUPPRESS_WINDOW_SEC + 1))
    er.tick()

    rollups = [ln for ln in _lines() if ln["event_type"] == er.ROLLUP_EVENT_TYPE]
    assert len(rollups) == 1, _lines()
    assert rollups[0]["suppressed"] == 299
    assert "destination_last4=2557" in rollups[0]["suppressed_key"]


def test_tick_advances_the_cursor_past_suppressed_rows(monkeypatch):
    """Suppression governs the tail, never the read model. A withheld line whose
    row was not passed would re-deliver forever."""
    rows = [_event("2557", f"m{i}") for i in range(50)]
    rows[-1]["created_at"] = "2026-08-29T18:00:00.000Z"
    monkeypatch.setattr(er, "_client", lambda: _FakeClient(rows))

    # Seed the cursor. Without it this test rots with the calendar: the fixture
    # rows are stamped 2026-08-29, _read_cursor's cold start returns
    # `now - 1 hour`, and tick() only advances `latest` past rows NEWER than the
    # cursor it started from. So from 2026-08-29T18:00 onward every row was
    # already behind the cold-start cursor, `latest` stayed at "an hour ago",
    # and the assertion compared today's clock against a fixed string. It had
    # been failing for four days and would have failed every day after.
    er.CURSOR_PATH.write_text("2026-08-29T00:00:00.000Z", encoding="utf-8")

    er.tick()

    assert er.CURSOR_PATH.read_text(encoding="utf-8") == "2026-08-29T18:00:00.000Z"


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #

def test_identity_ignores_the_per_message_fingerprint():
    """provider_message_id is unique on every row. If it leaked into the key,
    every event would be 'new' and suppression would be a no-op that looks like
    it works."""
    a = _event("2557", "aaa")
    b = _event("2557", "bbb")
    assert er._suppress_key(a, er._payload_dict(a)) == er._suppress_key(b, er._payload_dict(b))


def test_unknown_event_type_falls_back_to_type_and_source():
    ev = {"event_type": "SOME_FUTURE_FLOOD", "source_agent": "apex", "payload": {}}
    assert er._suppress_key(ev, {}) == "SOME_FUTURE_FLOOD|src=apex"
