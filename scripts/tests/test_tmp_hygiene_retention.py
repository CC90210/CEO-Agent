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

import json
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


def test_legacy_pm2_logs_age_out_normally(tmp_root):
    """PM2 is retired on Windows, so its old tmp logs are not permanent IPC."""
    legacy = tmp_root / "pm2-telegram-out.log"
    legacy.write_text("retired supervisor output", encoding="utf-8")
    _age(legacy, 31)

    to_delete, kept = tmp_hygiene._scan(30)

    assert legacy in to_delete
    assert legacy not in kept
    assert not tmp_hygiene._is_allowlisted(legacy.name)


def test_agent_inbox_is_never_deleted_as_generic_tmp(tmp_root):
    """Durable cross-agent handoffs are state, not disposable scratch files."""
    inbox = tmp_root / "agent_inbox"
    inbox.mkdir()
    (inbox / "pending.json").write_text("{}", encoding="utf-8")
    _age(inbox, 200)

    to_delete, kept = tmp_hygiene._scan(7)

    assert inbox not in to_delete
    assert inbox in kept


def test_cleanup_quarantine_is_never_scanned_as_disposable_input(tmp_root):
    quarantine = tmp_root / tmp_hygiene.QUARANTINE_DIR_NAME
    quarantine.mkdir()
    _age(quarantine, 30)

    to_delete, kept = tmp_hygiene._scan(7)

    assert quarantine not in to_delete
    assert quarantine in kept


def test_old_directory_with_fresh_descendant_is_kept(tmp_root):
    """A parent directory's stale mtime must not erase fresh work inside it."""
    work = tmp_root / "long_running_render"
    work.mkdir()
    fresh = work / "result.json"
    fresh.write_text("{}", encoding="utf-8")
    _age(work, 30)

    to_delete, kept = tmp_hygiene._scan(7)

    assert work not in to_delete
    assert work in kept
    assert fresh.exists()


def test_apply_quarantines_before_a_later_run_purges(tmp_root, monkeypatch, capsys):
    """The first destructive pass must remain recoverable for a grace period."""
    stale = tmp_root / "old-output.bin"
    stale.write_bytes(b"recoverable payload")
    _age(stale, 30)

    monkeypatch.setattr(
        sys,
        "argv",
        ["tmp_hygiene.py", "--apply", "--json", "--days", "7"],
    )
    assert tmp_hygiene.main() == 0
    first = json.loads(capsys.readouterr().out)

    quarantine = tmp_root / ".hygiene_quarantine"
    held = list(quarantine.iterdir())
    assert not stale.exists()
    assert len(held) == 1
    assert held[0].read_bytes() == b"recoverable payload"
    assert first["quarantined"] == ["old-output.bin"]
    assert first["deleted"] == []

    _age(held[0], tmp_hygiene.QUARANTINE_RETENTION_DAYS + 1)
    assert tmp_hygiene.main() == 0
    second = json.loads(capsys.readouterr().out)
    assert not held[0].exists()
    assert second["deleted"] == [held[0].name]


def test_candidate_that_becomes_fresh_before_quarantine_is_restored(tmp_root):
    """Revalidate at mutation time so scan/action races cannot move fresh work."""
    work = tmp_root / "render-in-progress"
    work.mkdir()
    payload = work / "frame.bin"
    payload.write_bytes(b"old")
    _age(payload, 30)
    _age(work, 30)
    to_delete, _ = tmp_hygiene._scan(7)
    assert work in to_delete

    payload.write_bytes(b"fresh output")
    cutoff = time.time() - 7 * 86400
    result = tmp_hygiene._quarantine(work, stale_cutoff=cutoff)

    assert result is None
    assert work.exists()
    assert payload.read_bytes() == b"fresh output"
    quarantine = tmp_root / ".hygiene_quarantine"
    assert not quarantine.exists() or list(quarantine.iterdir()) == []


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
    held = list((tmp_root / ".hygiene_quarantine").iterdir())
    assert len(held) == 1
    assert held[0].read_text(encoding="utf-8") == "x" * 100


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
