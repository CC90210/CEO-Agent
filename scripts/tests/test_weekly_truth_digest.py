from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import weekly_truth_digest as digest  # noqa: E402
from core import cron_engine  # noqa: E402


def test_compose_digest_reports_every_gate_and_overall_failure():
    results = [
        digest.GateResult("Self-audit", 0, "MANDATORY GATES: PASS", "", False),
        digest.GateResult("Fleet health", 0, "bravo FRESH", "", False),
        digest.GateResult("Pytest", 1, "1639 passed, 1 failed", "", False),
    ]

    text = digest.compose_digest(results)

    assert "Weekly full-truth health digest" in text
    assert "✅ Self-audit" in text
    assert "❌ Pytest" in text
    assert "OVERALL: RED" in text


def test_run_gate_marks_timeout_and_never_hides_it(monkeypatch):
    def _timeout(*_a, **_k):
        raise digest.subprocess.TimeoutExpired(["python", "slow.py"], 10)

    monkeypatch.setattr(digest.subprocess, "run", _timeout)

    result = digest.run_gate("Slow gate", ["python", "slow.py"], timeout=10)

    assert result.timed_out is True
    assert result.returncode != 0
    assert "timed out" in result.stderr.lower()


def test_main_notifies_even_when_all_gates_pass(monkeypatch):
    calls = []
    green = [
        digest.GateResult("Self-audit", 0, "pass", "", False),
        digest.GateResult("Fleet health", 0, "pass", "", False),
        digest.GateResult("Pytest", 0, "1640 passed", "", False),
    ]
    monkeypatch.setattr(digest, "collect_results", lambda: green)
    monkeypatch.setattr(digest, "send_notification", lambda text: calls.append(text) or True)

    assert digest.main([]) == 0
    assert len(calls) == 1
    assert "OVERALL: GREEN" in calls[0]


def test_self_audit_warning_band_renders_warn_not_red():
    """The first live run (2026-08-23) drew ❌ on '99/100; mandatory PASS'
    because self_audit exits 1 for anything under 100. That is self_audit's
    WARNING band and must render ⚠️ with OVERALL: WARN, not a failure."""
    audit_json = '{"health_score": 99, "mandatory_gate_passed": true}'
    results = [
        digest.GateResult("Self-audit", 1, audit_json, "", False),
        digest.GateResult("Fleet health", 0, "{}", "", False),
        digest.GateResult("Pytest", 0, "1640 passed", "", False),
    ]

    assert digest.gate_verdict(results[0]) == "warn"
    text = digest.compose_digest(results)
    assert "⚠️ Self-audit" in text
    assert "OVERALL: WARN" in text


def test_mandatory_failure_is_still_red():
    audit_json = '{"health_score": 99, "mandatory_gate_passed": false}'
    result = digest.GateResult("Self-audit", 1, audit_json, "", False)
    assert digest.gate_verdict(result) == "red"


def test_fleet_findings_are_warn_but_fleet_crash_is_red():
    findings = digest.GateResult("Fleet health", 1, '{"pulses": []}',
                                 "bravo pulse aging", False)
    crash = digest.GateResult("Fleet health", 1, "Traceback ...", "boom", False)
    assert digest.gate_verdict(findings) == "warn"
    assert digest.gate_verdict(crash) == "red"


def test_red_findings_exit_zero_when_report_delivered(monkeypatch):
    """Exit contract: findings are the report's CONTENT. The cron fails only
    when the digest could not report — otherwise the watchdog double-pages CC
    about facts the digest already delivered (the 2026-08-23 page)."""
    red = [
        digest.GateResult("Self-audit", 2, "{}", "", False),
        digest.GateResult("Fleet health", 0, "{}", "", False),
        digest.GateResult("Pytest", 1, "1 failed", "", False),
    ]
    monkeypatch.setattr(digest, "collect_results", lambda: red)
    monkeypatch.setattr(digest, "send_notification", lambda text: True)

    assert digest.main([]) == 0


def test_delivery_failure_exits_nonzero_even_when_all_green(monkeypatch):
    green = [
        digest.GateResult("Self-audit", 0, "pass", "", False),
        digest.GateResult("Fleet health", 0, "{}", "", False),
        digest.GateResult("Pytest", 0, "1640 passed", "", False),
    ]
    monkeypatch.setattr(digest, "collect_results", lambda: green)
    monkeypatch.setattr(digest, "send_notification", lambda text: False)

    assert digest.main([]) == 1


def test_weekly_digest_seed_is_active_and_has_scheduler_headroom():
    job = next(
        job for job in cron_engine.SEED_JOBS
        if job["name"] == "Weekly Full-Truth Health Digest"
    )

    assert job["is_active"] is True
    assert job["schedule"] == "0 7 * * SUN"
    assert job["action_type"] == "script_run"
    assert job["action_config"]["script"] == "scripts/weekly_truth_digest.py"
    assert job["action_config"]["timeout"] > digest.PYTEST_TIMEOUT_SEC


def test_seed_only_inserts_the_selected_definition():
    inserted = []

    class Result:
        def __init__(self, data):
            self.data = data

    class Table:
        def select(self, *_args):
            return self

        def insert(self, payload):
            inserted.append(payload)
            return self

        def execute(self):
            if inserted:
                return Result([{**inserted[-1], "id": "new-id"}])
            return Result([])

    class Client:
        def table(self, name):
            assert name == "cron_jobs"
            return Table()

    args = Namespace(only="Weekly Full-Truth Health Digest")
    cron_engine.cmd_seed(Client(), args, output_json=True)

    assert [row["name"] for row in inserted] == ["Weekly Full-Truth Health Digest"]
