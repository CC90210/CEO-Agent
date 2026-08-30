from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import harness_eval as he  # noqa: E402
import ceo_dashboard as cd  # noqa: E402
import client_health as ch  # noqa: E402
import daily_brief as db  # noqa: E402
from snapshots import briefing_snapshot as bs  # noqa: E402


@pytest.mark.parametrize("marker", ["timed out", "broken", "needs a fix", "unavailable"])
def test_brief_check_rejects_degraded_markers(monkeypatch, marker):
    monkeypatch.setattr(
        he,
        "_run",
        lambda *_a, **_k: (0, f"Pipeline: 3\nDashboard {marker}", ""),
    )

    ok, detail = he.check_brief_renders()

    assert ok is False
    assert marker in detail.lower()


def test_brief_timeout_layers_have_ordered_headroom():
    assert 45 <= cd.SUBENGINE_TIMEOUT_SEC < bs.TIMEOUT_SEC
    assert bs.TIMEOUT_SEC < db.SNAPSHOT_REGEN_TIMEOUT_SEC
    assert (
        db.SNAPSHOT_REGEN_TIMEOUT_SEC + db.CLI_NARRATION_TIMEOUT_SEC
        <= db.SCHEDULER_JOB_TIMEOUT_SEC - 10
    )


def test_self_audit_gate_accepts_advisory_warning_when_mandatory_gates_pass(monkeypatch):
    payload = {"mandatory_gate_passed": True, "mandatory_gate_failures": [], "health_score": 99}
    monkeypatch.setattr(he, "_run", lambda *_a, **_k: (1, json.dumps(payload), ""))

    assert he.check_self_audit_mandatory_gates() == (
        True,
        "self-audit mandatory gates pass (health 99/100)",
    )


def test_self_audit_gate_fails_on_mandatory_drift(monkeypatch):
    payload = {
        "mandatory_gate_passed": False,
        "mandatory_gate_failures": ["scripts missing graph nodes"],
        "health_score": 84,
    }
    monkeypatch.setattr(he, "_run", lambda *_a, **_k: (1, json.dumps(payload), ""))

    ok, detail = he.check_self_audit_mandatory_gates()

    assert ok is False
    assert "scripts missing graph nodes" in detail


def test_migration_doc_gate_fails_on_unclassified_tier_1_or_2(monkeypatch):
    payload = {"unannotated_tier_counts": {"1": 1, "2": 2}}
    monkeypatch.setattr(he, "_run", lambda *_a, **_k: (1, json.dumps(payload), ""))

    ok, detail = he.check_migration_docs_classified()

    assert ok is False
    assert "1 Tier-1" in detail and "2 Tier-2" in detail


def test_session_log_gate_rejects_repeated_frontmatter(tmp_path, monkeypatch):
    log = tmp_path / "SESSION_LOG.md"
    block = "---\ntags: [daily]\n---\n"
    log.write_text(block + block + "\n### 2026-08-20 — entry\n", encoding="utf-8")
    monkeypatch.setattr(he, "SESSION_LOG_PATH", log)

    ok, detail = he.check_session_log_integrity()

    assert ok is False
    assert "2 frontmatter" in detail


def test_client_health_query_failure_never_returns_demo_clients():
    class BrokenTable:
        def select(self, *_args):
            raise ConnectionError("Turso unavailable")

    class BrokenClient:
        def table(self, _name):
            return BrokenTable()

    with pytest.raises(RuntimeError, match="Turso client data query failed"):
        ch.fetch_clients(BrokenClient())


def test_scheduler_timeout_mirror_matches_reality():
    """daily_brief.SCHEDULER_JOB_TIMEOUT_SEC is a COPY of the timeout
    scheduler.run_daily_brief actually passes to run_script. Two definitions of
    one number drift, and this one did: raising the scheduler to 200s on
    2026-08-28 left the mirror at 150s.

    The ordering test above could not have caught that alone — a stale mirror
    that still satisfies `regen + narration <= mirror - 10` looks perfectly
    healthy while the real outer cap is somewhere else entirely. It only
    surfaced because the raised inner budgets happened to break the ordering
    too. This asserts correspondence, not just internal consistency.
    """
    import re
    from pathlib import Path

    import daily_brief as db

    src = (Path(db.__file__).resolve().parent / "scheduler.py").read_text(encoding="utf-8")
    m = re.search(r'run_script\(\s*"daily_brief\.py"\s*,\s*\[\]\s*,\s*timeout\s*=\s*(\d+)', src)
    assert m, "could not find run_daily_brief's run_script timeout in scheduler.py"
    actual = int(m.group(1))
    assert db.SCHEDULER_JOB_TIMEOUT_SEC == actual, (
        f"daily_brief mirrors the scheduler timeout as {db.SCHEDULER_JOB_TIMEOUT_SEC}s "
        f"but scheduler.run_daily_brief actually uses {actual}s")
