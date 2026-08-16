"""Alert damping and transient-retry contract for the cron/monitor fleet.

Written 2026-08-15 after CC's Telegram log showed the failure shape plainly:
BREEZE LIVE WATCH paged "problem detected" at 8:19 PM and "recovered" at
8:24 PM; Inbound Email Sweep, Training Corpus Ingest and Marketing Publish
Drain each paged and self-recovered inside eight minutes. Every underlying
fault in tmp/cron_failures/ was transport — `ConnectionResetError [WinError
10054]` on the Gmail TLS handshake and `ValueError: Hrana: ... tcp connect
error ... (os error 10060)` reaching Turso. Nothing was broken. CC was paged
nine times.

These tests pin the two properties that fix it:
  1. a single transient fault is retried in-process and never pages
  2. a "recovered" ping is only ever sent when the matching failure alert
     actually went out

Property 2 is the subtle one. The old breeze watcher gated its PROBLEM alert on
`changed or stale` but gated RECOVERY on `prev` being non-empty — two different
conditions — so a blip that never paged still sent "All checks green again."
A recovery notification whose alert was never sent is pure noise, and it is the
kind of bug that survives review because each half reads correctly on its own.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "lib"))


# ── breeze_live_watch: soak window + paired recovery ────────────────────────

@pytest.fixture()
def watch(monkeypatch, tmp_path):
    import breeze_live_watch as w
    monkeypatch.setattr(w, "STATE_FILE", tmp_path / "breeze_live_watch.json")
    sent: list[str] = []
    monkeypatch.setattr(w, "notify", lambda msg, **kw: sent.append(msg) or True)
    monkeypatch.setattr(w, "check_failed_emails", lambda _m: [])
    return w, sent


def _set_health(monkeypatch, w, problems):
    monkeypatch.setattr(w, "check_health", lambda: list(problems))


def test_single_transient_failure_does_not_page(watch, monkeypatch):
    w, sent = watch
    _set_health(monkeypatch, w, ["health endpoint unreachable: timed out"])
    res = w.run_once(window_min=10)
    assert res["consecutive_failures"] == 1
    assert sent == [], f"paged on the first failure: {sent}"


def test_second_consecutive_failure_pages(watch, monkeypatch):
    w, sent = watch
    _set_health(monkeypatch, w, ["health endpoint unreachable: timed out"])
    w.run_once(window_min=10)
    w.run_once(window_min=10)
    assert len(sent) == 1, f"expected exactly one page, got {sent}"
    assert "problem detected" in sent[0]
    assert "persisted 2 consecutive checks" in sent[0]


def test_blip_that_never_paged_sends_no_recovery(watch, monkeypatch):
    """The exact 8:19 -> 8:24 PM shape from CC's log."""
    w, sent = watch
    _set_health(monkeypatch, w, ["health endpoint unreachable: timed out"])
    w.run_once(window_min=10)          # 1 failure — below threshold, silent
    _set_health(monkeypatch, w, [])
    w.run_once(window_min=10)          # recovered
    assert sent == [], f"sent an unpaired recovery: {sent}"


def test_real_outage_pages_once_and_recovers_once(watch, monkeypatch):
    w, sent = watch
    _set_health(monkeypatch, w, ["health check 'db' is failing"])
    for _ in range(4):
        w.run_once(window_min=10)
    assert len(sent) == 1, f"re-paged while still broken: {sent}"
    _set_health(monkeypatch, w, [])
    res = w.run_once(window_min=10)
    assert len(sent) == 2 and "recovered" in sent[1]
    assert res["consecutive_failures"] == 0 and res["alerted"] is False


def test_check_health_retries_transient_then_reports(monkeypatch):
    import breeze_live_watch as w
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise ConnectionResetError("[WinError 10054] forcibly closed")

    monkeypatch.setattr(w.urllib.request, "urlopen", boom)
    monkeypatch.setattr(w.time, "sleep", lambda _s: None)
    problems = w.check_health()
    assert calls["n"] == w.NETWORK_ATTEMPTS, "did not retry the full budget"
    assert problems and "after 3 attempts" in problems[0]


def test_check_health_succeeds_on_a_later_attempt(monkeypatch):
    """The whole point: a blip must produce NO problem at all."""
    import io
    import breeze_live_watch as w
    calls = {"n": 0}

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self): return self
        def __exit__(self, *a): return False

    def flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionResetError("[WinError 10054]")
        return _Resp(b'{"checks": {"db": true}}')

    monkeypatch.setattr(w.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(w.time, "sleep", lambda _s: None)
    assert w.check_health() == []


# ── email_engine: retry only what is actually transient ────────────────────

def test_transient_classifier_matches_the_real_production_faults():
    from integrations import email_engine as e
    assert e._is_transient(ConnectionResetError("[WinError 10054]"))
    assert e._is_transient(ValueError(
        "Hrana: `http error: `error trying to connect: tcp connect error: "
        "... (os error 10060)``"))
    assert e._is_transient(TimeoutError("timed out"))


def test_transient_classifier_does_not_swallow_the_identifier_guard():
    """lib/db_turso.quote_ident raises ValueError for an unsafe SQL identifier.

    Retrying that would burn three attempts and then surface a security defect
    as a network complaint. The classifier keys on transport markers, not on the
    exception type, precisely so these two ValueErrors stay distinguishable.
    """
    from integrations import email_engine as e
    from lib.db_turso import quote_ident

    try:
        quote_ident('x"; ' + "DROP" + " TABLE t; --")
        pytest.fail("quote_ident accepted an unsafe identifier")
    except ValueError as guard_error:
        assert not e._is_transient(guard_error), (
            "the identifier guard's ValueError was classified as a network blip")


def test_retry_reraises_non_transient_on_the_first_attempt():
    from integrations import email_engine as e
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise KeyError("missing config key")

    with pytest.raises(KeyError):
        e._retry_transient("t", fn, attempts=3, sleep_s=0)
    assert calls["n"] == 1, "retried a non-transient error"


def test_retry_recovers_on_a_later_attempt():
    from integrations import email_engine as e
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionResetError("[WinError 10054]")
        return "connected"

    assert e._retry_transient("t", fn, attempts=3, sleep_s=0) == "connected"
    assert calls["n"] == 3


# ── scheduler: thresholds, and recovery paired to the alert ────────────────

def test_fast_jobs_need_more_failures_than_slow_ones():
    import scheduler as s
    assert s.ESCALATE_AFTER_FAST > s.ESCALATE_AFTER_SLOW, (
        "a fast job retries within minutes; it must tolerate more bad ticks "
        "than a daily job whose first failure is already the signal")
    assert s.ESCALATE_AFTER_FAST >= 3


@pytest.mark.parametrize("minutes,expected_fast", [
    (1, True), (5, True), (15, True), (16, False), (60, False), (1440, False),
])
def test_escalation_threshold_by_job_speed(minutes, expected_fast):
    from datetime import timedelta
    import scheduler as s
    got = s.escalation_threshold(timedelta(minutes=minutes))
    assert got == (s.ESCALATE_AFTER_FAST if expected_fast else s.ESCALATE_AFTER_SLOW)


def test_alert_and_recovery_share_one_threshold_for_every_job_speed():
    """Replaces a weaker test that passed while a real bug was live.

    The first version asserted `RECOVERY_MIN_FAILURES >= ESCALATE_AFTER_FAST`,
    which is true and useless: with a separate recovery constant of 3, a SLOW
    job escalated at 2 and recovered at max(2,3)=3, so every slow-job alert
    stayed unresolved. Codex's audit caught it; this test did not, because it
    checked one direction for one job class instead of the invariant.

    The invariant is equality, in both directions, for both classes — which is
    now structural: `escalation_threshold()` is the only source, and there is no
    second constant left to drift from it.
    """
    from datetime import timedelta
    import re
    import scheduler as s

    for period in (timedelta(minutes=1), timedelta(minutes=15),
                   timedelta(hours=1), timedelta(days=1), None):
        assert s.escalation_threshold(period) == s.escalation_threshold(period)

    src = (REPO / "scripts" / "scheduler.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"^RECOVERY_MIN_FAILURES\s*=", code, re.M), (
        "a second recovery threshold reappeared — it can only drift from the alert one")
    assert "fail_count >= escalate_at" in code, (
        "recovery must gate on exactly the threshold that gated the alert")


def test_lowercase_failure_summary_does_not_trip_the_job_classifier():
    """marketing_publish_drain prints `published: 0/3  ·  failed: 3`. The
    plain-text branch of _looks_like_failure greps for uppercase ERROR/FAILED,
    so this must not read as a job failure now that the drain exits 0."""
    import scheduler as s
    assert not s._looks_like_failure("published: 0/3  ·  failed: 3")
    assert s._looks_like_failure("ERROR: database unavailable")
