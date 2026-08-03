"""Dedup backoff — the fix for the 2026-07-29 overnight alert storm.

WHAT HAPPENED. review_fix refused to edit the wrong branch (correctly). The
refusal exited 1, review_loop read that as a retryable failure and never drained
the queue, the cron retried every 15 minutes, and notify's flat 1-hour window
expired on schedule — so CC got the identical sentence at 10:30, 11:30, 12:30
and 1:30 AM. Three separate defects, one symptom.

This pins the notify half: a repeating condition must decay, and an alert whose
text carries a varying detail must still dedup.

No network — notify() is disabled under pytest by _notify_disabled().
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def nf(tmp_path, monkeypatch):
    """Fresh notify module with an isolated dedup cache and known windows."""
    monkeypatch.setenv("NOTIFY_DEDUP_WINDOW_SEC", "3600")
    monkeypatch.setenv("NOTIFY_DEDUP_BACKOFF", "1")
    monkeypatch.setenv("NOTIFY_DEDUP_MAX_WINDOW_SEC", str(24 * 3600))
    monkeypatch.setenv("NOTIFY_DEDUP_FORGET_SEC", str(72 * 3600))
    import notify as _n
    importlib.reload(_n)
    monkeypatch.setattr(_n, "_DEDUP_PATH", tmp_path / "dedup.json")
    return _n


def at(nf, monkeypatch, seconds: float):
    monkeypatch.setattr(nf.time, "time", lambda: seconds)


# ── the storm, reproduced ────────────────────────────────────────────────────

def test_hourly_repeat_no_longer_fires_hourly(nf, monkeypatch):
    """The exact failure: same message, retried every 15 min, flat 1h window.

    Old behaviour: sends at 0h, 1h, 2h, 3h, 4h... forever.
    New behaviour: 0h, then 1h, then 3h (2h window), then 7h (4h window)...
    """
    msg = ("Review loop errors:\n  CC90210/oasis-command-center#107: local "
           "checkout is on 'fix/inbound-copy-native-brain'")
    sent_at = []
    # Simulate a 15-minute cron across 12 hours.
    for minute in range(0, 12 * 60 + 1, 15):
        at(nf, monkeypatch, minute * 60)
        if nf._dedup_should_send("system", msg):
            sent_at.append(minute / 60)

    assert sent_at[0] == 0
    # Old code sent 13 times in 12h (once an hour). Backoff must be far fewer.
    assert len(sent_at) <= 5, f"still storming: sent at {sent_at}"
    # And the gaps must grow, not stay flat.
    gaps = [round(b - a, 2) for a, b in zip(sent_at, sent_at[1:])]
    assert gaps == sorted(gaps), f"intervals must be non-decreasing, got {gaps}"
    assert gaps[-1] > gaps[0], f"no escalation happened: {gaps}"


def test_first_occurrence_is_always_immediate(nf, monkeypatch):
    """Backoff must never delay the FIRST alert — that is the one CC needs."""
    at(nf, monkeypatch, 1000.0)
    assert nf._dedup_should_send("system", "brand new problem") is True


def test_distinct_messages_are_independent(nf, monkeypatch):
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", "problem A") is True
    assert nf._dedup_should_send("system", "problem B") is True
    assert nf._dedup_should_send("system", "problem A") is False


def test_same_text_different_category_is_independent(nf, monkeypatch):
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", "same text") is True
    assert nf._dedup_should_send("lead", "same text") is True


# ── lane isolation: dedup answers "has THIS audience seen it?" ───────────────
# Codex [P2], 2026-08-02. `notify.py "msg"` then `notify.py --group "msg"`
# suppressed the broadcast the operator explicitly asked for, because the two
# lanes shared one dedup identity. Same shape as the shared-credential lane bug:
# one identity serving two audiences.

def test_group_broadcast_is_not_suppressed_by_a_prior_private_send(nf, monkeypatch):
    """The reported bug, reproduced. The group has NOT seen the private message."""
    msg = "Sprint 1 shipped — portal is live"
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", msg, lane="private") is True
    at(nf, monkeypatch, 60.0)                       # well inside the 1h window
    assert nf._dedup_should_send("system", msg, lane="group") is True, \
        "group broadcast suppressed by a prior private send"


def test_each_lane_still_dedups_within_itself(nf, monkeypatch):
    """Lane scoping must not become a dedup bypass — repeats inside one lane
    are still collapsed, or the storm defence is gone."""
    msg = "same sentence"
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", msg, lane="group") is True
    at(nf, monkeypatch, 60.0)
    assert nf._dedup_should_send("system", msg, lane="group") is False
    at(nf, monkeypatch, 120.0)
    assert nf._dedup_should_send("system", msg, lane="private") is True   # first here
    at(nf, monkeypatch, 180.0)
    assert nf._dedup_should_send("system", msg, lane="private") is False


def test_private_lane_keeps_the_legacy_key_shape(nf, monkeypatch):
    """The default lane must hash exactly as it did before this change, so an
    in-flight backoff ladder is not reset (a stuck alert must not get a free
    re-fire just because the identity moved)."""
    import hashlib
    msg = "legacy identity"
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", msg) is True
    legacy = hashlib.sha256(f"system\x00{msg}".encode("utf-8")).hexdigest()[:32]
    import json
    seen = json.loads(nf._DEDUP_PATH.read_text(encoding="utf-8"))
    assert legacy in seen, f"private key shape changed; cache holds {list(seen)}"


def test_notify_passes_the_lane_through(nf, monkeypatch):
    """Wiring guard: the bug was that notify() never told dedup which lane it
    was routing to. Assert the argument actually arrives."""
    seen = []
    monkeypatch.setattr(nf, "_dedup_should_send",
                        lambda *a, **kw: seen.append(kw.get("lane")) or False)
    monkeypatch.setattr(nf, "_notify_disabled", lambda: False)
    nf.notify("x", category="system", force=True, group=True)
    nf.notify("x", category="system", force=True)
    assert seen == ["group", "private"], seen


# ── dedup_key: the other half of how a storm happens ─────────────────────────

def test_varying_detail_defeats_dedup_without_a_key(nf, monkeypatch):
    """Guard the guard: prove the failure mode dedup_key exists to fix."""
    for i in range(5):
        at(nf, monkeypatch, i * 60.0)          # 1 minute apart
        # A count in the text makes every message hash differently.
        assert nf._dedup_should_send("system", f"3 findings, attempt {i}") is True


def test_dedup_key_holds_the_line_when_the_text_varies(nf, monkeypatch):
    key = "review_loop_blocked:CC90210/oasis-command-center#107"
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", "blocked, attempt 1", dedup_key=key) is True
    for i in range(2, 8):
        at(nf, monkeypatch, i * 60.0)
        assert nf._dedup_should_send("system", f"blocked, attempt {i}", dedup_key=key) is False


# ── bounds and recovery ──────────────────────────────────────────────────────

def test_window_is_capped(nf, monkeypatch):
    """Escalation must not run away to weeks — 24h is the ceiling."""
    msg = "persistent"
    t = 0.0
    at(nf, monkeypatch, t)
    assert nf._dedup_should_send("system", msg) is True
    for _ in range(12):                        # push n high
        t += 25 * 3600
        at(nf, monkeypatch, t)
        nf._dedup_should_send("system", msg)
    # After 24h+ it must be willing to speak again.
    t += 24 * 3600 + 60
    at(nf, monkeypatch, t)
    assert nf._dedup_should_send("system", msg) is True


def test_a_long_silence_resets_the_escalation(nf, monkeypatch):
    """A recurrence a week later is a NEW incident, not a continuation — it must
    not inherit last week's 24-hour backoff."""
    msg = "flaky thing"
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", msg) is True
    at(nf, monkeypatch, 3600.0)
    assert nf._dedup_should_send("system", msg) is True      # n -> 2
    at(nf, monkeypatch, 3600.0 + 80 * 3600)                  # past FORGET
    assert nf._dedup_should_send("system", msg) is True
    # …and the escalation restarted, so 1h later it is quiet again, not 2h.
    at(nf, monkeypatch, 3600.0 + 80 * 3600 + 1800)
    assert nf._dedup_should_send("system", msg) is False


def test_legacy_float_cache_rows_do_not_crash(nf, monkeypatch, tmp_path):
    """The on-disk format changed from {key: timestamp} to {key: {last, n}}.
    An in-flight cache from the old build must not take alerting down."""
    import json
    (tmp_path / "dedup.json").write_text(json.dumps({"deadbeef": 12345.0}),
                                         encoding="utf-8")
    at(nf, monkeypatch, 99999.0)
    assert nf._dedup_should_send("system", "anything") is True


def test_corrupt_cache_fails_open(nf, monkeypatch, tmp_path):
    """Dedup must never swallow a real alert. A broken cache means SEND."""
    (tmp_path / "dedup.json").write_text("{not json", encoding="utf-8")
    at(nf, monkeypatch, 500.0)
    assert nf._dedup_should_send("system", "important") is True


def test_backoff_can_be_switched_off(tmp_path, monkeypatch):
    """Escape hatch: NOTIFY_DEDUP_BACKOFF=0 restores the flat window.

    Builds its own module instance rather than reloading the fixture's. An
    earlier draft called importlib.reload() on the fixture module, which reset
    _DEDUP_PATH back to the REAL tmp/notify_dedup.json — so the test was quietly
    writing into production alert state. Reload first, repoint second.
    """
    monkeypatch.setenv("NOTIFY_DEDUP_WINDOW_SEC", "3600")
    monkeypatch.setenv("NOTIFY_DEDUP_BACKOFF", "0")
    monkeypatch.setenv("NOTIFY_DEDUP_FORGET_SEC", str(72 * 3600))
    import notify as flat
    importlib.reload(flat)
    monkeypatch.setattr(flat, "_DEDUP_PATH", tmp_path / "flat.json")
    assert flat.DEDUP_BACKOFF is False

    monkeypatch.setattr(flat.time, "time", lambda: 0.0)
    assert flat._dedup_should_send("system", "x") is True
    monkeypatch.setattr(flat.time, "time", lambda: 1800.0)
    assert flat._dedup_should_send("system", "x") is False   # inside the flat window
    monkeypatch.setattr(flat.time, "time", lambda: 3601.0)
    assert flat._dedup_should_send("system", "x") is True    # flat: no doubling
    monkeypatch.setattr(flat.time, "time", lambda: 7202.0)
    assert flat._dedup_should_send("system", "x") is True    # still flat, not 2h


def test_daemon_crash_loop_does_not_storm(nf, monkeypatch):
    """notify_daemon_crash embeds tick_id, which changes every tick — so before
    the dedup_key fix a crash-looping PM2 daemon hashed differently every time
    and dedup never fired once, despite the docstring claiming it did.

    Asserts the KEY, not delivery: notify() is disabled under pytest.
    """
    seen_keys = []
    monkeypatch.setattr(nf, "notify",
                        lambda *a, **kw: seen_keys.append(kw.get("dedup_key")) or True)
    for tick in range(5):
        nf.notify_daemon_crash("event-router", f"boom at {tick}", tick_id=f"t{tick}")

    assert all(k == "daemon_crash:event-router" for k in seen_keys), seen_keys
    assert len(set(seen_keys)) == 1, "tick_id leaked into the dedup identity"


def test_notify_error_dedups_on_the_engine_not_the_message(nf, monkeypatch):
    """Same shape: a cron whose error text carries a changing count would
    otherwise defeat dedup on every tick."""
    seen_keys = []
    monkeypatch.setattr(nf, "notify",
                        lambda *a, **kw: seen_keys.append(kw.get("dedup_key")) or True)
    nf.notify_error("Inbound Email Sweep", "FAILED: 3 of 7")
    nf.notify_error("Inbound Email Sweep", "FAILED: 4 of 9")
    assert seen_keys == ["engine_error:Inbound Email Sweep"] * 2


# ── suppressed is not the same as delivered ──────────────────────────────────
# Codex [P2], 2026-08-03. _dedup_should_send writes its record BEFORE the send,
# because it has to decide first. So a window can exist for a message that never
# landed. Health monitors read "suppressed" as "CC already knows" — which would
# buy silence for the whole backoff window during the exact alerting outage they
# exist to surface.

def test_a_window_opened_by_a_failed_send_does_not_count_as_delivered(nf, monkeypatch):
    at(nf, monkeypatch, 0.0)
    assert nf._dedup_should_send("system", "boom", dedup_key="k") is True   # window opens
    # …send fails, so nothing marks it delivered.
    assert nf._dedup_was_delivered("system", "boom", dedup_key="k") is False


def test_a_landed_send_marks_the_window_delivered(nf, monkeypatch):
    at(nf, monkeypatch, 0.0)
    nf._dedup_should_send("system", "boom", dedup_key="k")
    nf._dedup_mark_delivered("system", "boom", dedup_key="k")
    assert nf._dedup_was_delivered("system", "boom", dedup_key="k") is True


def test_delivery_state_is_per_lane(nf, monkeypatch):
    at(nf, monkeypatch, 0.0)
    nf._dedup_should_send("system", "m", dedup_key="k", lane="private")
    nf._dedup_mark_delivered("system", "m", dedup_key="k", lane="private")
    nf._dedup_should_send("system", "m", dedup_key="k", lane="group")
    assert nf._dedup_was_delivered("system", "m", dedup_key="k", lane="private") is True
    assert nf._dedup_was_delivered("system", "m", dedup_key="k", lane="group") is False


def test_legacy_records_without_the_flag_read_as_delivered(nf, monkeypatch, tmp_path):
    """Windows opened by the pre-fix build have no `d` key. Assuming failure
    would re-page CC for every one of them on the next tick."""
    import json
    key = nf._dedup_identity("system", "old", None, "private")
    (tmp_path / "dedup.json").write_text(json.dumps({key: {"last": 100.0, "n": 1}}),
                                         encoding="utf-8")
    assert nf._dedup_was_delivered("system", "old") is True


def test_an_unknown_condition_is_not_delivered(nf):
    assert nf._dedup_was_delivered("system", "never seen") is False


def test_tests_never_touch_the_real_dedup_cache(nf):
    """Meta-guard. Every test here must run against tmp_path — a test that
    writes the live cache can silence a genuine production alert."""
    assert "pytest" in str(nf._DEDUP_PATH).lower() or "tmp" in str(nf._DEDUP_PATH).lower()
    assert nf._DEDUP_PATH != Path(__file__).resolve().parent.parent.parent / "tmp" / "notify_dedup.json"
