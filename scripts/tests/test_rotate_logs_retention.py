"""Retention contract for state logs and the active bridge logs."""

from __future__ import annotations

import gzip
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hooks import rotate_logs  # noqa: E402


@pytest.fixture
def log_roots(tmp_path, monkeypatch):
    state = tmp_path / "state"
    memory = tmp_path / "memory"
    state.mkdir()
    memory.mkdir()
    monkeypatch.setattr(rotate_logs, "STATE_DIR", state)
    monkeypatch.setattr(rotate_logs, "MEMORY_DIR", memory)
    monkeypatch.setattr(rotate_logs, "STAMP_PATH", state / ".rotate_logs.stamp")
    monkeypatch.setattr(rotate_logs, "MAX_BYTES", 4)
    return state, memory


def _run_main(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["rotate_logs.py", *args])
    return rotate_logs.main()


@pytest.mark.parametrize(
    "filename",
    ["telegram_bridge.log", "coordination_bridge.log"],
)
def test_active_memory_bridge_logs_rotate_with_bounded_backups(
    log_roots, monkeypatch, filename
):
    state, memory = log_roots
    active = memory / filename
    active.write_bytes(b"active bridge output")

    # More than the retention limit already exists. A successful rotation must
    # leave the newest five only, not preserve an unbounded historical tail.
    stem = active.stem
    for index in range(7):
        old = memory / f"{stem}.2024010{index + 1}T000000Z.log.gz"
        with gzip.open(old, "wb") as handle:
            handle.write(f"old-{index}".encode())

    assert _run_main(monkeypatch, "--force") == 0
    assert active.read_bytes() == b""
    assert len(list(memory.glob(f"{stem}.*.log.gz"))) == rotate_logs.KEEP_BACKUPS
    assert (state / ".rotate_logs.stamp").exists()


def test_unrelated_memory_logs_are_not_swept(log_roots, monkeypatch):
    _, memory = log_roots
    unrelated = memory / "manual_investigation.log"
    unrelated.write_bytes(b"leave this operator evidence alone")

    assert _run_main(monkeypatch, "--force") == 0
    assert unrelated.read_bytes() == b"leave this operator evidence alone"
    assert list(memory.glob("manual_investigation.*.log.gz")) == []


def test_rotation_failure_exits_nonzero_and_does_not_write_success_stamp(
    log_roots, monkeypatch, capsys
):
    state, _ = log_roots
    failing = state / "cannot_rotate.log"
    failing.write_bytes(b"large enough")

    def fail_rotation(path: Path, dry_run: bool):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(rotate_logs, "_rotate", fail_rotation)

    assert _run_main(monkeypatch, "--force") == 1
    assert not (state / ".rotate_logs.stamp").exists()
    assert "cannot_rotate.log" in capsys.readouterr().err


def test_append_after_atomic_detach_survives_in_new_active_log(
    log_roots, monkeypatch
):
    """A bridge write during compression must never be truncated away."""
    _, memory = log_roots
    active = memory / "telegram_bridge.log"
    original_payload = b"old bridge output"
    new_payload = b"arrived after detach\n"
    active.write_bytes(original_payload)
    original_compress = rotate_logs._compress_detached

    def compress_while_bridge_writes(detached: Path, backup: Path) -> None:
        # The live path must already be a fresh file before slow gzip work.
        assert detached != active
        active.write_bytes(new_payload)
        original_compress(detached, backup)

    monkeypatch.setattr(rotate_logs, "_compress_detached", compress_while_bridge_writes)
    assert _run_main(monkeypatch, "--force") == 0

    assert active.read_bytes() == new_payload
    archive = next(memory.glob("telegram_bridge.*.log.gz"))
    with gzip.open(archive, "rb") as handle:
        assert handle.read() == original_payload


def test_orphaned_rotation_is_recovered_to_gzip_and_raw_file_removed(
    log_roots, monkeypatch
):
    """A crash-left raw rotation must be retried, not ignored forever."""
    _, memory = log_roots
    payload = b"sensitive bridge evidence"
    orphan = memory / ".telegram_bridge.log.20260923T000000000000Z.123.rotating"
    orphan.write_bytes(payload)
    old = time.time() - 3600
    os.utime(orphan, (old, old))
    monkeypatch.setattr(rotate_logs, "ORPHAN_MIN_AGE_SEC", 0)

    assert _run_main(monkeypatch, "--force") == 0

    assert not orphan.exists()
    archive = memory / "telegram_bridge.20260923T000000000000Z.log.gz"
    assert archive.exists()
    with gzip.open(archive, "rb") as handle:
        assert handle.read() == payload


def test_orphan_recovery_failure_is_loud_and_remains_retryable(
    log_roots, monkeypatch, capsys
):
    """Raw evidence may remain for recovery, but never behind a success stamp."""
    state, _ = log_roots
    orphan = state / ".secret_access.log.20260923T000000000000Z.123.rotating"
    orphan.write_bytes(b"audit evidence")
    old = time.time() - 3600
    os.utime(orphan, (old, old))
    monkeypatch.setattr(rotate_logs, "ORPHAN_MIN_AGE_SEC", 0)

    def fail_compression(_source: Path, _backup: Path) -> None:
        raise OSError("synthetic recovery failure")

    monkeypatch.setattr(rotate_logs, "_compress_detached", fail_compression)

    assert _run_main(monkeypatch, "--force") == 1
    assert orphan.exists()
    assert not (state / ".rotate_logs.stamp").exists()
    assert "orphan" in capsys.readouterr().err.lower()


def test_dry_run_reports_orphan_without_mutating_it(log_roots, monkeypatch):
    _, memory = log_roots
    orphan = memory / ".telegram_bridge.log.20260923T000000000000Z.123.rotating"
    orphan.write_bytes(b"keep raw during rehearsal")
    old = time.time() - 3600
    os.utime(orphan, (old, old))
    monkeypatch.setattr(rotate_logs, "ORPHAN_MIN_AGE_SEC", 0)

    assert _run_main(monkeypatch, "--dry-run") == 0

    assert orphan.exists()
    assert list(memory.glob("telegram_bridge.*.log.gz")) == []
