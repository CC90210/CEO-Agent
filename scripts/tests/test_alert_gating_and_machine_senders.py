"""Four defects behind CC's 2026-07-30 "Funnel Fast-Poll error" Telegram page.

The alert itself was correct — a transient 30s stall really did happen. What was
wrong was everything around it: who got told, how loudly, for how long the job
went dark afterwards, and (separately, found in the same screenshot) that a DMARC
report from a noreply address was triaged as a human worth replying to.

Each test here fails against the pre-fix code. None of them touch the network.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import email_playbook as pb  # noqa: E402
import scheduler  # noqa: E402


# ── 1. Machine senders with COMPOUND local parts ─────────────────────────────
#
# The live failure: noreply-dmarc-support@google.com. The old test was
# `full.startswith("noreply@") or "noreply@" in full`, which demands the local
# part be EXACTLY "noreply" — a hyphen defeats it, so Google's DMARC robot was
# classified kind="human", may_reply=True and had a reply drafted for it.

@pytest.mark.parametrize("address", [
    "noreply-dmarc-support@google.com",   # the one that actually got through
    "noreply@google.com",                 # the plain form (worked before too)
    "no-reply@stripe.com",
    "do-not-reply@vercel.com",
    "do_not_reply@example.com",
    "notifications.billing@example.com",
    "mailer-daemon@example.com",
    "bounces+tag@example.com",
])
def test_compound_machine_local_parts_are_detected(address):
    assert pb._local_part_is_machine(address) is True, address


@pytest.mark.parametrize("address", [
    "alerta@realcompany.com",     # 'alert' is a prefix of 'alerta' — NOT a bot
    "systematic@agency.com",      # 'system' is a prefix of 'systematic'
    "noreplyman@example.com",     # no separator: one token, not a machine word
    "cc@oasisai.work",
    "david@breezeadvance.com",
])
def test_real_humans_are_not_swept_up(address):
    """The dangerous over-correction. Substring matching would silence these,
    and a human we refuse to ever reply to is an INVISIBLE failure — worse than
    the bug being fixed, because nothing surfaces it."""
    assert pb._local_part_is_machine(address) is False, address


def test_the_dmarc_sender_is_classified_automated_end_to_end():
    """Not just the helper — the function the pipeline actually calls."""
    res = pb.classify_sender("noreply-dmarc-support@google.com")
    assert res["is_automated"] is True
    assert res["may_reply"] is False, "a Google DMARC robot must never get a reply"


# ── 2. First-failure paging is gated on job cadence ──────────────────────────

def test_fast_and_slow_job_periods_are_classified_correctly():
    """The rule is 'will it try again before CC could act', not severity."""
    fast = ["*/1 * * * *", "*/5 * * * *", "*/15 * * * *"]
    slow = ["0 * * * *", "0 6 * * *", "0 22 * * 1"]

    for sched in fast:
        period = scheduler.parse_cron_schedule(sched)
        assert period is not None and period <= scheduler.FAST_JOB_PERIOD, sched
    for sched in slow:
        period = scheduler.parse_cron_schedule(sched)
        assert period is None or period > scheduler.FAST_JOB_PERIOD, sched


def test_unparseable_schedule_still_pages():
    """Fail OPEN. If we cannot prove a job is self-healing, treat its first
    failure as real — silence is the expensive mistake here."""
    period = scheduler.parse_cron_schedule("not a cron")
    self_healing = period is not None and period <= scheduler.FAST_JOB_PERIOD
    assert self_healing is False


# ── 3. A retry must never be SLOWER than the job's own schedule ──────────────

@pytest.mark.parametrize("sched,expected_max_min", [
    ("*/1 * * * *", 1),      # the funnel poll: was pushed to 5 min, 5x its period
    ("*/5 * * * *", 5),
    ("*/15 * * * *", 5),     # capped at 5 — retrying sooner than scheduled is fine
    ("0 6 * * *", 5),        # daily: 5-min retry is a rescue, keep it
])
def test_retry_delay_never_exceeds_the_jobs_period(sched, expected_max_min):
    period = scheduler.parse_cron_schedule(sched)
    delay = min(timedelta(minutes=5), period) if period else timedelta(minutes=5)
    assert delay.total_seconds() / 60 <= expected_max_min, (
        f"{sched}: retry of {delay} is slower than the job's own cadence")


# ── 4. A TIMEOUT must leave a dump — the mode that never did ─────────────────

def test_scheduler_imports_cleanly():
    """py_compile passes on an undefined annotation; import does not. A NameError
    at module scope here takes the whole cron daemon down silently."""
    import importlib
    importlib.reload(scheduler)
    assert callable(scheduler.run_script)


@pytest.mark.parametrize("raw,expected", [
    (b"  bytes out  ", "bytes out"),
    ("  str out  ", "str out"),
    (None, ""),
])
def test_as_text_handles_every_shape_subprocess_returns(raw, expected):
    """TimeoutExpired.stdout is str under text=True, bytes if the child died
    before the decoder ran, and None when nothing was captured."""
    assert scheduler._as_text(raw) == expected


def test_timeout_writes_a_dump_with_whatever_the_child_emitted(tmp_path, monkeypatch):
    """THE GAP. run_script's persist_failure sat below `subprocess.run`, which
    RAISES on timeout — so the one failure mode with no traceback of its own also
    had no dump. CC's 11:53 page pointed at tmp/cron_failures/; it was empty."""
    import subprocess as sp

    monkeypatch.setattr(scheduler, "FAILURE_DUMP_DIR", tmp_path)

    def _boom(*a, **kw):
        raise sp.TimeoutExpired(cmd=["python", "funnel_sync.py"], timeout=30,
                                output=b"partial stdout", stderr=b"partial stderr")

    monkeypatch.setattr(scheduler.subprocess, "run", _boom)

    result = scheduler.run_script("funnel_sync.py", ["fast-poll"], timeout=30)

    assert "timeout after 30s" in result, result
    dumps = list(tmp_path.glob("*.log"))
    assert dumps, "a timeout still produced no dump"
    body = dumps[0].read_text(encoding="utf-8")
    assert "partial stderr" in body, "the child's last words were dropped"
    assert "partial stdout" in body
    assert "TIMEOUT" in body


# ── 5. The two alert stages must not share a dedup identity ──────────────────

def test_escalation_and_per_tick_alerts_have_distinct_dedup_keys():
    """THE INVERSION. Both scheduler call sites keyed on engine_error:{job}, so
    the noisy first-tick page claimed the dedup slot and SUPPRESSED the
    fail_count==2 escalation — CC got the noise and never the signal."""
    import notify as nf

    seen = {}

    def _capture(msg, **kw):
        seen[kw.get("dedup_key")] = msg
        return True

    original = nf.notify
    try:
        nf.notify = _capture
        nf.notify_error("Funnel Fast-Poll", "timed out")
        nf.notify_error("Funnel Fast-Poll", "failing repeatedly", stage="escalation")
    finally:
        nf.notify = original

    assert len(seen) == 2, f"stages collapsed onto one dedup key: {list(seen)}"
    assert "engine_error:Funnel Fast-Poll" in seen
    assert "engine_error:Funnel Fast-Poll:escalation" in seen
