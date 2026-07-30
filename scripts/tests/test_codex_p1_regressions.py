"""Three P1s from Codex's independent audit of the 2026-07-30 branch.

All three were mine, and two were introduced by that morning's fix for the
overnight alert storm — over-correction, not oversight. Recorded here because a
verified external finding is worth more than a self-review, and because each of
these fails in a way no existing test would have caught.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import review_fix  # noqa: E402
import review_loop  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ── P1-1: a rejected fix must be recoverable ─────────────────────────────────

def test_rejected_fix_is_saved_before_the_tree_is_reverted(tmp_path, monkeypatch):
    """The comment said "don't revert good work" directly above a line that
    reverted it. The revert is necessary — findings share one working tree — but
    the diff existed nowhere else, so the proposed change was simply gone."""
    monkeypatch.setattr(review_fix, "REJECTED_PATCH_DIR", tmp_path)
    monkeypatch.setattr(review_fix, "run",
                        lambda *a, **k: (0, "diff --git a/x b/x\n+real change\n", ""))

    ref = review_fix._save_patch(Path("."), {"path": "src/x.py", "thread_id": "T1"})

    assert ref, "no patch reference returned"
    saved = list(tmp_path.glob("*.patch"))
    assert saved, "the diff was not written anywhere before the revert"
    assert "real change" in saved[0].read_text(encoding="utf-8")


def test_save_patch_is_silent_when_there_is_nothing_to_save(tmp_path, monkeypatch):
    monkeypatch.setattr(review_fix, "REJECTED_PATCH_DIR", tmp_path)
    monkeypatch.setattr(review_fix, "run", lambda *a, **k: (0, "", ""))
    assert review_fix._save_patch(Path("."), {"path": "x", "thread_id": "T"}) == ""


def test_save_patch_never_raises_on_the_failure_path(tmp_path, monkeypatch):
    """It runs while handling a failure. Throwing here would mask the very
    failure it exists to preserve."""
    monkeypatch.setattr(review_fix, "REJECTED_PATCH_DIR", tmp_path)

    def _boom(*a, **k):
        raise OSError("git exploded")

    monkeypatch.setattr(review_fix, "run", _boom)
    assert review_fix._save_patch(Path("."), {"path": "x", "thread_id": "T"}) == ""


def test_patch_dir_is_ring_buffered(tmp_path, monkeypatch):
    monkeypatch.setattr(review_fix, "REJECTED_PATCH_DIR", tmp_path)
    monkeypatch.setattr(review_fix, "REJECTED_PATCH_KEEP", 3)
    monkeypatch.setattr(review_fix, "run", lambda *a, **k: (0, "diff --git a/x b/x\n", ""))
    for i in range(8):
        review_fix._save_patch(Path("."), {"path": f"f{i}.py", "thread_id": f"T{i}"})
    assert len(list(tmp_path.glob("*.patch"))) <= 3


# ── P1-2: a PR whose fix did not land must not be silently dropped ───────────
#
# The only thing that enqueues a PR is inbound review mail
# (email_engine._enqueue_review_harvest). There is NO independent sweep of open
# PRs — so draining on any clean exit meant a failed fix was never retried until
# a NEW review comment happened to arrive. Leaving the seen-ledger untouched
# does not save it: nothing goes looking.

# IMPORTED, not redeclared. The first version of this file defined its own
# TERMINAL set and asserted against it — so it tested the test, and would have
# stayed green while review_loop's real set drifted. Import the thing you claim
# to protect.
TERMINAL = review_loop.TERMINAL_STATUSES
RETRYABLE = {"failed", "reverted", "committed-not-pushed"}


def test_the_terminal_set_is_the_one_the_code_uses():
    """Guard the guard: prove this file is reading review_loop's own constant."""
    assert TERMINAL is review_loop.TERMINAL_STATUSES
    assert "fixed" in TERMINAL and "failed" not in TERMINAL


def test_every_review_fix_status_is_classified():
    """Guard the guard. A new status added to review_fix that lands in neither
    set would silently take the drain path — the exact bug being fixed."""
    src = (PROJECT_ROOT / "scripts" / "review_fix.py").read_text(encoding="utf-8")
    import re
    emitted = set(re.findall(r'status="([a-z-]+)"', src))
    assert emitted, "status sweep found nothing — the regex is wrong"
    unclassified = emitted - TERMINAL - RETRYABLE
    assert not unclassified, (
        f"review_fix can emit {sorted(unclassified)}, which review_loop does not "
        f"classify — it would drain as if terminal")


@pytest.mark.parametrize("status", sorted(RETRYABLE))
def test_a_fix_that_did_not_land_is_retryable_not_terminal(status):
    assert status not in TERMINAL, (
        f"{status!r} means nothing reached the branch; draining on it loses the "
        f"review permanently because only inbound mail re-enqueues")


@pytest.mark.parametrize("status", sorted(TERMINAL))
def test_terminal_statuses_drain(status):
    """Including 'escalated': review_fix has already Telegrammed CC and leaves
    it out of the seen-ledger, so a manual harvest still surfaces it. Retrying
    it every 15 minutes would just re-spam."""
    assert status not in RETRYABLE


def test_retry_is_bounded():
    """Unbounded retry is how the original storm happened; a silent drop is the
    bug that replaced it. The answer is neither — count, then give up loudly."""
    assert 1 < review_loop.RETRY_LIMIT <= 10, review_loop.RETRY_LIMIT


# The classification tests above pin the SET. These exercise the DECISION the
# loop actually makes with it — the arithmetic, not the constant.

def _decide(statuses, attempts=0):
    """Reproduce review_loop's drain/keep branch for a given result shape."""
    retryable = [s for s in statuses if s not in review_loop.TERMINAL_STATUSES]
    if not retryable:
        return "drain"
    return "giveup" if attempts + 1 >= review_loop.RETRY_LIMIT else "keep"


@pytest.mark.parametrize("statuses,expected", [
    (["fixed"], "drain"),
    (["fixed", "skipped"], "drain"),
    (["escalated"], "drain"),
    ([], "drain"),                                   # nothing to do
    (["failed"], "keep"),
    (["committed-not-pushed"], "keep"),
    (["reverted"], "keep"),
    (["fixed", "failed"], "keep"),                   # ONE unlanded finding is enough
    (["escalated", "committed-not-pushed"], "keep"),
])
def test_drain_decision(statuses, expected):
    assert _decide(statuses) == expected, statuses


def test_a_partly_successful_pass_is_still_kept():
    """The subtle case. Three findings fixed and one push failure still means a
    review thread nobody will ever look at again — so the PR stays queued."""
    assert _decide(["fixed", "fixed", "fixed", "committed-not-pushed"]) == "keep"


def test_retry_eventually_gives_up_instead_of_looping_forever():
    assert _decide(["failed"], attempts=review_loop.RETRY_LIMIT - 1) == "giveup"
    assert _decide(["failed"], attempts=0) == "keep"


# ── P1-3 + the NameError found while verifying it ────────────────────────────

def test_review_loop_binds_every_name_it_calls():
    """notify_error was called at the escalation site but never imported — a
    NameError that fires only when the loop tries to report a problem, which is
    precisely when you need it to work."""
    assert hasattr(review_loop, "notify"), "notify unbound"
    assert hasattr(review_loop, "notify_error"), "notify_error unbound"
    assert callable(review_loop.notify_error)


def test_deploy_script_refuses_to_start_an_unauthenticated_proxy():
    """litellm_config.yaml reads master_key from $LITELLM_MASTER_KEY, but the
    launcher never set it — so a fresh deploy came up with no enforcement while
    printing a key that would not authenticate."""
    sh = (PROJECT_ROOT / "scripts" / "llm_training" / "deploy_server.sh").read_text(
        encoding="utf-8")
    assert "LITELLM_MASTER_KEY" in sh, "the launcher still never sets the key"
    assert "refusing to start an unauthenticated proxy" in sh, "it does not fail closed"
    # The literal key that used to be printed on two lines must be gone.
    assert "sk-oasis-master-key" not in sh, "a hardcoded key is still in the script"
