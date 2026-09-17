"""The harness eval must not deadlock on its own failure dump.

From 2026-09-13 scheduler.run_script_action calls persist_failure() on every
non-zero exit. That closes a real blind spot — before it, the four failing
script_run jobs in the registry had produced zero bytes of evidence between
them — but it also arms a self-perpetuating red:

    a check goes red -> harness_eval exits 1 -> the scheduler writes a dump
    -> check_no_recent_cron_failure_dumps sees a fresh dump -> red
    -> exits 1 -> dumps again -> forever, with no path back to green.

That is the same shape as the 2026-07-28 deadlock is_self_scored_failure()
exists to break, so the fix reuses that precedent instead of inventing a second
marker that can drift. These tests pin its NARROWNESS: the exemption must cover
the eval's own self-scored dump and nothing else.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import harness_eval as he  # noqa: E402


def _write(d: Path, slug: str, body: str, when: datetime | None = None) -> Path:
    """Write a dump under scheduler.persist_failure's naming contract."""
    when = when or datetime.now(timezone.utc)
    p = d / f"{slug}-{when.strftime('%Y%m%dT%H%M%SZ')}.log"
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture
def dumpdir(tmp_path, monkeypatch):
    monkeypatch.setattr(he, "FAILURE_DUMP_DIR", tmp_path)
    return tmp_path


def test_the_evals_own_self_scored_dump_does_not_hold_it_red(dumpdir):
    """The deadlock itself. A red check makes the eval exit 1, the non-zero
    exit writes this dump; if the dump counted, the check could never go green
    again no matter what was fixed."""
    _write(dumpdir, he._SELF_DUMP_SLUG,
           "job: scripts/harness_eval.py\nexit code: 1\n\n"
           "STDOUT\nHARNESS EVAL - 15/17 checks pass  (run abc123)\n")
    ok, msg = he.check_no_recent_cron_failure_dumps()
    assert ok, msg


def test_a_real_crash_of_the_eval_still_counts(dumpdir):
    """The exemption is keyed on the self-score BANNER, not on the filename.
    An import error or an OS kill writes no banner and must still be reported —
    otherwise the fix blinds this check to the eval's own hard failures, which
    is the exact class of silent death it was built for."""
    _write(dumpdir, he._SELF_DUMP_SLUG,
           "job: scripts/harness_eval.py\nexit code: 3221225480\n\n"
           "STDERR\nTraceback (most recent call last):\n"
           "ModuleNotFoundError: No module named 'yaml'\n")
    ok, msg = he.check_no_recent_cron_failure_dumps()
    assert not ok
    assert he._SELF_DUMP_SLUG in msg


def test_another_jobs_dump_is_never_skipped_even_with_the_marker(dumpdir):
    """A different job whose output happens to carry the banner — a wrapper
    echoing it, an operator piping the eval's text — must not inherit the
    exemption. Only the eval's own slug qualifies."""
    _write(dumpdir, "integrations-email-engine-py",
           "job: integrations/email_engine.py\nexit code: TIMEOUT\n\n"
           "STDOUT\nHARNESS EVAL - 16/17 checks pass\n")
    ok, msg = he.check_no_recent_cron_failure_dumps()
    assert not ok
    assert "integrations-email-engine-py" in msg


def test_the_slug_is_derived_from_this_file_not_hardcoded():
    """persist_failure is called with action_config["script"], never the cron
    row's name, so the slug is the SCRIPT path. Deriving it from __file__ means
    moving harness_eval.py cannot silently un-skip the exemption."""
    assert he._SELF_DUMP_SLUG == "scripts-harness-eval-py"


def test_an_old_dump_is_history_not_news(dumpdir):
    """Unchanged behaviour, re-pinned so the new exemption can never be
    confused with the 24h freshness window."""
    old = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _write(dumpdir, "some-other-job", "exit code: 1\n", when=old)
    ok, _ = he.check_no_recent_cron_failure_dumps()
    assert ok
