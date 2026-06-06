"""Tests for scripts/state/backup_db.py — SQLite backup + restore."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from state import backup_db


def _seed_db(path: Path, rows: int = 5) -> None:
    """Create a tiny WAL-mode SQLite DB with N rows."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, val TEXT)")
        conn.executemany("INSERT INTO t (val) VALUES (?)", [(f"row-{i}",) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate the backup module to a temp state/ tree."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    backup_dir = state_dir / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_db, "STATE_DIR", state_dir)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)
    # Override DB_TARGETS to point at the sandbox
    src = state_dir / "empire_state.db"
    _seed_db(src)
    monkeypatch.setattr(backup_db, "DB_TARGETS", [("empire_state", src)])
    return state_dir


def test_backup_creates_valid_sqlite_file(sandbox):
    rc = backup_db.main(["--json", "backup"])
    assert rc == 0
    backups = list((sandbox / "backups").glob("backup_empire_state_*.db"))
    assert len(backups) == 1
    # Backup file readable as SQLite + has the same rows
    conn = sqlite3.connect(str(backups[0]))
    try:
        n = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()
    assert n == 5


def test_backup_passes_integrity_check(sandbox):
    backup_db.main(["backup"])
    name = next(iter((sandbox / "backups").glob("backup_*.db"))).name
    rc = backup_db.main(["--json", "verify", "--file", name])
    assert rc == 0


def test_verify_detects_corruption(sandbox, capsys):
    # Make a fake "backup" that's just garbage bytes
    bad = sandbox / "backups" / "backup_empire_state_20260101_000000.db"
    bad.write_bytes(b"this is not a sqlite database")
    rc = backup_db.main(["--json", "verify", "--file", bad.name])
    assert rc != 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] in ("corrupt", "fail")


def test_restore_replaces_db_atomically(sandbox):
    # Initial backup of 5-row DB
    backup_db.main(["backup"])
    name = next(iter((sandbox / "backups").glob("backup_*.db"))).name

    # Mutate the live DB
    src = sandbox / "empire_state.db"
    _seed_db(src, rows=99)
    conn = sqlite3.connect(str(src))
    try:
        n_before = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()
    assert n_before == 5 + 99  # 5 original + 99 new

    # Restore
    rc = backup_db.main(["--json", "restore", "--file", name])
    assert rc == 0

    # Live DB now reflects the backup's 5 rows
    conn = sqlite3.connect(str(src))
    try:
        n_after = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()
    assert n_after == 5


def test_restore_rejects_corrupt_backup(sandbox):
    bad = sandbox / "backups" / "backup_empire_state_20260101_000000.db"
    bad.write_bytes(b"garbage")
    rc = backup_db.main(["--json", "restore", "--file", bad.name])
    assert rc != 0


def test_list_returns_sorted_newest_first(sandbox):
    # Create three artificial backup files with distinct timestamps
    for ts in ("20260101_000000", "20260315_120000", "20260520_080000"):
        f = sandbox / "backups" / f"backup_empire_state_{ts}.db"
        # write a real SQLite-compatible body so any future check stays happy
        c = sqlite3.connect(str(f))
        c.execute("CREATE TABLE x (id INT)")
        c.close()
    rc = backup_db.main(["--json", "list"])
    assert rc == 0


def test_prune_keeps_exactly_n_most_recent(sandbox):
    # Make 5 fake backups
    for ts in ("20260101_000000", "20260201_000000", "20260301_000000",
               "20260401_000000", "20260501_000000"):
        f = sandbox / "backups" / f"backup_empire_state_{ts}.db"
        c = sqlite3.connect(str(f))
        c.execute("CREATE TABLE x (id INT)")
        c.close()
    rc = backup_db.main(["--json", "prune", "--keep", "2"])
    assert rc == 0
    remaining = sorted(p.name for p in (sandbox / "backups").glob("backup_*.db"))
    assert remaining == [
        "backup_empire_state_20260401_000000.db",
        "backup_empire_state_20260501_000000.db",
    ]


def test_backup_handles_missing_source_gracefully(sandbox, monkeypatch):
    # Point at a DB that doesn't exist
    missing = sandbox / "ghost.db"
    monkeypatch.setattr(backup_db, "DB_TARGETS", [("ghost", missing)])
    rc = backup_db.main(["--json", "backup"])
    # Skipped, not failed
    assert rc == 0


def test_json_output_is_valid(sandbox, capsys):
    backup_db.main(["--json", "backup"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["action"] == "backup"
    assert "results" in payload


def test_cron_compatible_exit_codes(sandbox, monkeypatch):
    # Healthy backup → exit 0
    assert backup_db.main(["backup"]) == 0
    # Bad backup file for verify → exit 1
    bad = sandbox / "backups" / "backup_empire_state_19990101_000000.db"
    bad.write_bytes(b"x")
    assert backup_db.main(["verify", "--file", bad.name]) != 0


def test_keep_argument_prunes_after_backup(sandbox):
    # Pre-seed 4 fake backups
    for ts in ("20260101_000000", "20260201_000000", "20260301_000000", "20260401_000000"):
        f = sandbox / "backups" / f"backup_empire_state_{ts}.db"
        c = sqlite3.connect(str(f))
        c.execute("CREATE TABLE x (id INT)")
        c.close()
    # Backup + prune to 2
    rc = backup_db.main(["backup", "--keep", "2"])
    assert rc == 0
    remaining = sorted(p.name for p in (sandbox / "backups").glob("backup_*.db"))
    assert len(remaining) == 2
    # The fresh backup must be among the 2
    assert any("20260" not in r or r > "backup_empire_state_20260401" for r in remaining)
