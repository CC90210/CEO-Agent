"""Retention behaviour for tmp/cron_failures/.

Two separate bugs, both from the same cause: _scan() iterates TMP_DIR only, so
it can see a directory but never its contents.

1. cron_failures/ was NOT allowlisted, so it was judged by its own mtime — which
   only moves when a job FAILS. A quiet 90-day stretch (the outcome we are
   working toward) would have deleted the entire failure archive in one pass.
   The allowlist's own comment on `snapshots` documents this exact trap one
   directory over: "a backup a cron deletes is worse than none".

2. The documented "keep ~90 days" policy for those logs was never implemented,
   because top-level iteration cannot express it.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utilities import tmp_hygiene  # noqa: E402


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tmp_hygiene, "TMP_DIR", tmp_path)
    (tmp_path / "cron_failures").mkdir()
    return tmp_path


def _age(path: Path, days: float) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_cron_failures_directory_is_never_deleted_wholesale(tmp_root):
    """The archive must survive a long quiet stretch with no failures."""
    d = tmp_root / "cron_failures"
    (d / "old.log").write_text("x", encoding="utf-8")
    _age(d / "old.log", 200)
    _age(d, 200)  # directory itself looks ancient: no job has failed in ages

    to_delete, kept = tmp_hygiene._scan(30)
    assert d not in to_delete, (
        "the whole failure archive was queued for deletion during a quiet "
        "stretch — the evidence of what breaks is gone exactly when it recurs")
    assert d in kept


def test_stale_failure_logs_inside_are_pruned(tmp_root):
    d = tmp_root / "cron_failures"
    (d / "ancient.log").write_text("x" * 100, encoding="utf-8")
    (d / "recent.log").write_text("y" * 100, encoding="utf-8")
    _age(d / "ancient.log", 200)

    removed, freed = tmp_hygiene._prune_cron_failures(90, apply=True)
    assert removed == ["ancient.log"]
    assert freed == 100
    assert not (d / "ancient.log").exists()
    assert (d / "recent.log").exists(), "a recent failure log must be kept"


def test_prune_is_dry_run_by_default(tmp_root):
    """apply=False must report without deleting — the same contract as _scan."""
    d = tmp_root / "cron_failures"
    (d / "ancient.log").write_text("x", encoding="utf-8")
    _age(d / "ancient.log", 200)

    removed, _ = tmp_hygiene._prune_cron_failures(90, apply=False)
    assert removed == ["ancient.log"]
    assert (d / "ancient.log").exists(), "dry run must not delete"


def test_prune_tolerates_a_missing_directory(tmp_root):
    """A machine that has never had a cron failure must not error."""
    (tmp_root / "cron_failures").rmdir()
    assert tmp_hygiene._prune_cron_failures(90, apply=True) == ([], 0)


def test_prune_ignores_subdirectories(tmp_root):
    """Only files are aged; a nested directory is left for a human to judge."""
    nested = tmp_root / "cron_failures" / "archive"
    nested.mkdir()
    _age(nested, 200)
    removed, _ = tmp_hygiene._prune_cron_failures(90, apply=True)
    assert removed == []
    assert nested.exists()
