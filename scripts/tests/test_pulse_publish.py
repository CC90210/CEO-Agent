"""ceo_pulse — automating the parts a machine can honestly author, and no more.

2026-08-03: Atlas paged CC that Bravo's pulse was 15 days old. It was, because no
cron had ever written it. The obvious fix — schedule `pulse_publish refresh`
nightly — is a trap: cmd_refresh() merges over the existing file and stamps
updated_at=now, so it would have presented 15-day-old strategy, directives and
blockers as current. Atlas goes quiet; the data gets worse. A true signal turned
into a false all-clear.

`autorefresh` writes only what a machine can KNOW and never moves `updated_at`.
Every test here defends that boundary, because the moment it slips the alert that
would have told anyone becomes the alert that lies.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pulse_publish as pp  # noqa: E402


JUDGMENT_TS = "2026-07-18T21:20:43.273437Z"


def _seed(tmp_path, monkeypatch) -> Path:
    """A pulse that looks exactly like the stale one CC was paged about."""
    path = tmp_path / "ceo_pulse.json"
    path.write_text(json.dumps({
        "agent": "Bravo (CEO)",
        "version": pp.SCHEMA_VERSION,
        "updated_at": JUDGMENT_TS,
        "status": "ACTIVE",
        "revenue": {"net_mrr_usd": 6371.0, "target_mrr_usd": 10000,
                    "gap_usd": 3629.0, "active_clients": 1,
                    "source": "atlas cfo_pulse"},
        "strategy": {"current_focus": "CONCENTRATION RISK: land a 2nd client",
                     "top_priority_this_week": "SunBiz salary"},
        "directives_to_cfo": ["hold the line on tax reserve"],
        "recent_shipped": ["hand-authored prose that must survive"],
        "open_blockers_waiting_on_cc": [{"item": "Meta App Review", "owner": "meta"}],
        "agent_system_state": {"architecture": "4-agent operating model",
                               "atlas_last_known_pulse_age_hours": 3},
    }, indent=2), encoding="utf-8")
    monkeypatch.setattr(pp, "PULSE_PATH", path)
    return path


class Args:
    def __init__(self, **kw):
        self.dry_run = False
        self.__dict__.update(kw)


# ── the boundary ─────────────────────────────────────────────────────────────

def test_autorefresh_never_moves_updated_at(tmp_path, monkeypatch):
    """THE test. updated_at is what Atlas reads to decide whether Bravo's
    judgment is current. A mechanical job moving it is the whole failure."""
    path = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: ["abc123 did a thing"])

    assert pp.cmd_autorefresh(Args()) == 0
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["updated_at"] == JUDGMENT_TS


def test_autorefresh_leaves_every_judgment_field_untouched(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    before = json.loads(path.read_text(encoding="utf-8"))
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: ["abc123 x"])

    pp.cmd_autorefresh(Args())
    after = json.loads(path.read_text(encoding="utf-8"))

    for key in ("revenue", "strategy", "directives_to_cfo", "recent_shipped",
                "open_blockers_waiting_on_cc", "status"):
        assert after[key] == before[key], f"{key} was rewritten by a machine"


def test_revenue_is_never_authored_here(tmp_path, monkeypatch):
    """Atlas owns revenue (CLAUDE.md). Bravo asserting an MRR figure — even by
    copying one forward — is a boundary violation, not a rounding error."""
    path = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: [])
    pp.cmd_autorefresh(Args())
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["revenue"]["net_mrr_usd"] == 6371.0
    assert after["revenue"]["source"] == "atlas cfo_pulse"


def test_autorefresh_stamps_its_own_freshness(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: [])
    pp.cmd_autorefresh(Args())
    after = json.loads(path.read_text(encoding="utf-8"))
    assert "mechanical_as_of" in after
    assert after["mechanical_as_of"] != after["updated_at"]


def test_commits_land_in_their_own_key_not_recent_shipped(tmp_path, monkeypatch):
    """A commit subject is not a shipped feature. Overwriting hand-authored prose
    with machine output is the same lie in a smaller box."""
    path = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: ["abc123 wip"])
    pp.cmd_autorefresh(Args())
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["recent_shipped"] == ["hand-authored prose that must survive"]
    assert after["recent_commits"] == ["abc123 wip"]


# ── fail closed ──────────────────────────────────────────────────────────────

def test_a_dead_git_source_writes_nothing(tmp_path, monkeypatch):
    """Fail closed. A mechanical refresh that silently skips its own source is
    how a stale pulse starts looking maintained."""
    path = _seed(tmp_path, monkeypatch)
    before = path.read_text(encoding="utf-8")

    def boom(*_a, **_k):
        raise RuntimeError("git log failed (exit 128): not a git repository")
    monkeypatch.setattr(pp, "_recent_commits", boom)

    assert pp.cmd_autorefresh(Args()) == 1
    assert path.read_text(encoding="utf-8") == before


def test_autorefresh_refuses_to_seed_a_missing_pulse(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "PULSE_PATH", tmp_path / "nothing.json")
    assert pp.cmd_autorefresh(Args()) == 2
    assert not (tmp_path / "nothing.json").exists()


def test_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    path = _seed(tmp_path, monkeypatch)
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: [])
    assert pp.cmd_autorefresh(Args(dry_run=True)) == 0
    capsys.readouterr()
    assert path.read_text(encoding="utf-8") == before


# ── sibling ages ─────────────────────────────────────────────────────────────

def test_sibling_age_is_computed_from_the_siblings_own_timestamp(tmp_path):
    sib = tmp_path / "cfo_pulse.json"
    then = datetime.now(timezone.utc) - timedelta(hours=5)
    sib.write_text(json.dumps({"updated_at": then.isoformat().replace("+00:00", "Z")}),
                   encoding="utf-8")
    assert pp._pulse_age_hours(sib) == pytest.approx(5.0, abs=0.2)


def test_a_dark_sibling_is_data_not_a_crash(tmp_path):
    """A sibling being offline is exactly what a CEO pulse should record. It must
    not take the refresh down with it."""
    assert pp._pulse_age_hours(tmp_path / "never_existed.json") is None
    bad = tmp_path / "corrupt.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pp._pulse_age_hours(bad) is None


def test_stale_sibling_ages_are_replaced_not_preserved(tmp_path, monkeypatch):
    """The seeded file claims Atlas is 3h old — a figure frozen since July. The
    refresh must overwrite it with a measured value, or it is decoration."""
    path = _seed(tmp_path, monkeypatch)
    sib = tmp_path / "cfo.json"
    then = datetime.now(timezone.utc) - timedelta(hours=9)
    sib.write_text(json.dumps({"updated_at": then.isoformat().replace("+00:00", "Z")}),
                   encoding="utf-8")
    monkeypatch.setitem(pp.SIBLING_PULSES, "atlas", sib)
    monkeypatch.setattr(pp, "_recent_commits", lambda *_a, **_k: [])

    pp.cmd_autorefresh(Args())
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["agent_system_state"]["atlas_last_known_pulse_age_hours"] == pytest.approx(9.0, abs=0.2)
    assert after["agent_system_state"]["architecture"] == "4-agent operating model"


# ── the session-end path ─────────────────────────────────────────────────────

def test_state_sync_measures_judgment_age_not_mechanical(tmp_path):
    """The whole split collapses if the staleness warning reads the field the
    cron touches. Give it a pulse whose mechanical stamp is minutes old and whose
    judgment is 30 days old: the answer must be 30, not 0.

    An earlier version of this test asserted on the LIVE pulse file and passed
    only because that file happened to be stale — it flipped the moment a real
    judgment write landed. A test whose verdict depends on production state is
    not a test.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "state"))
    import state_sync as ss

    judged = datetime.now(timezone.utc) - timedelta(days=30)
    pulse = tmp_path / "ceo_pulse.json"
    pulse.write_text(json.dumps({
        "updated_at": judged.isoformat().replace("+00:00", "Z"),
        "mechanical_as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }), encoding="utf-8")

    assert ss._pulse_judgment_age_days(pulse) == pytest.approx(30.0, abs=0.1)


def test_state_sync_warns_only_past_the_threshold(tmp_path, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "state"))
    import state_sync as ss

    def _pulse(days: float) -> Path:
        p = tmp_path / f"pulse_{days}.json"
        ts = datetime.now(timezone.utc) - timedelta(days=days)
        p.write_text(json.dumps({"updated_at": ts.isoformat().replace("+00:00", "Z")}),
                     encoding="utf-8")
        return p

    assert ss._pulse_judgment_age_days(_pulse(1)) < ss.PULSE_STALE_DAYS
    assert ss._pulse_judgment_age_days(_pulse(9)) > ss.PULSE_STALE_DAYS
    assert ss._pulse_judgment_age_days(tmp_path / "absent.json") is None
