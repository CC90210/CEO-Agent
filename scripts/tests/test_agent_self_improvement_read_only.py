"""The nightly self-improvement cron proposes changes; it does not edit repos."""
from __future__ import annotations

import json

from core import agent_self_improvement as asi


def test_scheduled_sweep_uses_only_observation_modes(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    for rel in (
        "scripts/core/auto_heal.py",
        "scripts/core/memory_aging.py",
        "scripts/core/self_audit.py",
        "scripts/drift_autofix.py",
        "scripts/build_capability_graph.py",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# probe\n", encoding="utf-8")

    monkeypatch.setattr(asi, "AGENT_ROOTS", {"bravo": root})
    monkeypatch.setattr(
        asi,
        "audit_agent",
        lambda name, _root: asi.AgentReport(name=name, health_score=84),
    )
    monkeypatch.setattr(asi, "collect_recent_mistakes", lambda *_a, **_k: [])
    monkeypatch.setattr(asi, "detect_mistake_repeats", lambda *_a, **_k: [])
    calls = []

    def fake_run(cmd, cwd, timeout=90):
        calls.append(cmd)
        if "memory_aging.py" in " ".join(cmd) and "stale" in cmd:
            return 0, json.dumps({"count": 0}), ""
        if "memory_aging.py" in " ".join(cmd):
            return 0, json.dumps({"actions": []}), ""
        if "auto_heal.py" in " ".join(cmd):
            return 0, json.dumps({"health_after": 84, "actions_taken": []}), ""
        if "drift_autofix.py" in " ".join(cmd):
            return 0, json.dumps({"skill_fixes": [], "script_fixes": []}), ""
        return 0, "", ""

    monkeypatch.setattr(asi, "_run", fake_run)
    asi.run_sweep(["bravo"])

    joined = [" ".join(c) for c in calls]
    assert any("auto_heal.py --check --json" in c for c in joined)
    assert any("drift_autofix.py scan --json" in c for c in joined)
    assert any("memory_aging.py archive --dry-run --json" in c for c in joined)
    assert any("build_capability_graph.py --check" in c for c in joined)
    assert not any("drift_autofix.py apply" in c for c in joined)


def test_recent_mistakes_are_observations_not_claimed_fixes(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    monkeypatch.setattr(asi, "AGENT_ROOTS", {"bravo": root})
    monkeypatch.setattr(
        asi,
        "audit_agent",
        lambda name, _root: asi.AgentReport(name=name, health_score=84),
    )
    monkeypatch.setattr(asi, "collect_recent_mistakes", lambda *_a, **_k: ["missed gate"])
    monkeypatch.setattr(asi, "detect_mistake_repeats", lambda *_a, **_k: [])
    monkeypatch.setattr(asi, "scan_memory_staleness", lambda *_a, **_k: (0, None))
    monkeypatch.setattr(asi, "autofix_drift", lambda *_a, **_k: None)
    monkeypatch.setattr(asi, "archive_stale_memory", lambda *_a, **_k: None)
    monkeypatch.setattr(asi, "rebuild_capability_graph", lambda *_a, **_k: None)

    report = asi.run_sweep(["bravo"])["bravo"]

    assert report["fixes_applied"] == []
    assert "recent mistakes: 1" in report["warnings"]
    assert "✓ recent mistakes" not in asi.format_digest({"bravo": report})


def test_capability_graph_drift_keeps_stdout_evidence(tmp_path, monkeypatch):
    builder = tmp_path / "scripts" / "build_capability_graph.py"
    builder.parent.mkdir(parents=True)
    builder.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        asi,
        "_run",
        lambda *_a, **_k: (1, "DRIFT: 3 graph edges changed", ""),
    )

    message = asi.rebuild_capability_graph(tmp_path)

    assert message is not None
    assert "DRIFT: 3 graph edges changed" in message
