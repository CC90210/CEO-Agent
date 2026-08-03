"""cron_health_check — the watchdog that paged CC three times for one condition.

2026-08-03: 08:35, 09:00, 10:01, same unchanged failure. The watchdog runs hourly
and built its alert identity from the rendered text — which embeds a 120-char
`last_result` snippet carrying counts and traceback fragments. Any drift in that
snippet minted a fresh identity, so notify's 1h→2h→4h→8h→24h ladder never engaged.

FLEET_ALERT_DISCIPLINE, dedup property #2: key on the CONDITION, not the text.
Here the condition is *which jobs are failing*.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

import cron_health_check as chc  # noqa: E402


def _capture(monkeypatch):
    seen = {}
    import notify as nf
    monkeypatch.setattr(nf, "notify", lambda text, **kw: seen.update(kw, text=text) or True)
    return seen


def test_same_failing_jobs_same_key_even_when_the_snippet_moves(monkeypatch):
    """The exact bug: one condition, three pages, because the traceback text
    shifted between ticks."""
    keys = []
    for snippet in ("ERROR: script_run exit 1: {reds: 1, yellows: 2}",
                    "ERROR: script_run exit 1: {reds: 1, yellows: 3}",
                    "ERROR: script_run exit 1: {\"reds\": 1, \"checks\": [...]}"):
        seen = _capture(monkeypatch)
        chc.telegram_alert([{"name": "Loud Failures Weekly Probe",
                             "last_result": snippet, "last_run_at": "2026-08-03T08:35:00Z"}])
        keys.append(seen["dedup_key"])

    assert len(set(keys)) == 1, f"snippet drift minted new identities: {keys}"
    assert keys[0] == "cron_failing:Loud Failures Weekly Probe"


def test_a_new_failing_job_is_a_new_condition(monkeypatch):
    """Decay must not swallow news. A second job breaking is a different
    condition and has to page immediately, not wait out the first job's window."""
    seen_a = _capture(monkeypatch)
    chc.telegram_alert([{"name": "Job A", "last_result": "ERROR: x", "last_run_at": None}])

    seen_b = _capture(monkeypatch)
    chc.telegram_alert([{"name": "Job A", "last_result": "ERROR: x", "last_run_at": None},
                        {"name": "Job B", "last_result": "ERROR: y", "last_run_at": None}])

    assert seen_a["dedup_key"] != seen_b["dedup_key"]


def test_key_is_order_independent(monkeypatch):
    """The DB can hand back rows in any order; the same failure set must not
    alternate between two identities and defeat suppression by ping-ponging."""
    seen_1 = _capture(monkeypatch)
    chc.telegram_alert([{"name": "B", "last_result": "ERROR", "last_run_at": None},
                        {"name": "A", "last_result": "ERROR", "last_run_at": None}])
    seen_2 = _capture(monkeypatch)
    chc.telegram_alert([{"name": "A", "last_result": "ERROR", "last_run_at": None},
                        {"name": "B", "last_result": "ERROR", "last_run_at": None}])

    assert seen_1["dedup_key"] == seen_2["dedup_key"] == "cron_failing:A|B"


def test_alert_still_carries_the_detail(monkeypatch):
    """Keying on the condition must not strip the diagnosis out of the message —
    CC needs the snippet to know what broke, even though it isn't the identity."""
    seen = _capture(monkeypatch)
    chc.telegram_alert([{"name": "Inbound Email Sweep",
                         "last_result": "ERROR: SSLCertVerificationError",
                         "last_run_at": "2026-08-03T08:35:00Z"}])
    assert "Inbound Email Sweep" in seen["text"]
    assert "SSLCertVerificationError" in seen["text"]
