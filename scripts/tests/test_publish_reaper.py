"""The reaper's retry decision — the one where being wrong cannot be undone.

WHY THIS EXISTS
marketing_publish_drain claims an intent (`running`) BEFORE it publishes and
records the outcome AFTER. A process killed between those two — cron timeout,
reboot, OOM — leaves a row that looks identical whether the post went out or not.

The reaper used to put every such row back to `queued`. If the post had already
landed, the retry published it a second time. CMO-Agent's publisher checks
data/content_pool/_posted.jsonl for duplicates, but only schedule_posts WRITES
that ledger — a publish driven from the drain never enters it, so the shared
dedupe guard cannot catch this. An adversarial audit found it; these tests pin it.

THE ASYMMETRY IS THE WHOLE POINT: a false NO republishes something already live
and there is no unsending. A false YES costs one manual requeue. Every ambiguous
input below must therefore answer YES.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "marketing_publish_drain", REPO / "scripts" / "marketing_publish_drain.py"
)
drain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drain)

dispatched = drain.dispatched


# ── safe to retry: nothing ever reached a network ────────────────────────────

def test_no_result_means_we_never_dispatched():
    assert dispatched({"id": "i1"}) is False


def test_empty_result_means_we_never_dispatched():
    assert dispatched({"id": "i1", "result": ""}) is False
    assert dispatched({"id": "i1", "result": "{}"}) is False
    assert dispatched({"id": "i1", "result": {}}) is False


def test_a_failed_run_with_no_post_ids_is_safe_to_retry():
    row = {"result": '{"instagram": {"ok": false, "reason": "rate limited"}}'}
    assert dispatched(row) is False


# ── must NOT retry: something may already be live ────────────────────────────

def test_the_dispatch_marker_blocks_a_retry():
    row = {"result": '{"_dispatch_started_at": "2026-08-14T23:00:00Z", "platforms": ["instagram"]}'}
    assert dispatched(row) is True


def test_a_post_id_anywhere_blocks_a_retry():
    """Even one network that accepted it makes a retry a duplicate."""
    row = {"result": '{"instagram": {"ok": true, "post_id": "p_123"}, '
                     '"tiktok": {"ok": false, "reason": "refused"}}'}
    assert dispatched(row) is True


def test_unparseable_result_blocks_a_retry():
    """Ambiguity resolves toward the recoverable mistake, not the permanent one."""
    assert dispatched({"result": "{not json"}) is True


def test_non_dict_result_blocks_a_retry():
    assert dispatched({"result": "[1, 2, 3]"}) is True
    assert dispatched({"result": '"a string"'}) is True


def test_a_dict_result_is_accepted_without_re_parsing():
    """The compat client may hand back a dict rather than TEXT."""
    assert dispatched({"result": {"_dispatch_started_at": "2026-08-14T23:00:00Z"}}) is True
    assert dispatched({"result": {"instagram": {"ok": True, "post_id": "p1"}}}) is True
    assert dispatched({"result": {"instagram": {"ok": False, "reason": "no"}}}) is False


def test_the_marker_is_actually_written_before_dispatch():
    """A decision function nothing calls at the right moment protects nothing.

    Reads the source: the marker write must appear BEFORE the publish loop, and
    the reaper must consult dispatched() rather than requeueing unconditionally.
    """
    src = (REPO / "scripts" / "marketing_publish_drain.py").read_text(encoding="utf-8")

    marker = src.index("_dispatch_started_at")
    loop = src.index("for group, pro in ((short, False), (longform, True)):")
    assert marker < loop, "the dispatch marker must be written BEFORE the first network call"

    assert "if dispatched(row):" in src, "reap_stale must consult dispatched() before retrying"
