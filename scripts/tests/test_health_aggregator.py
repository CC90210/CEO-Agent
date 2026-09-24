"""Tests for scripts/state/health_aggregator.py."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from state import health_aggregator as ha


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    backups = state / "backups"
    backups.mkdir()
    monkeypatch.setattr(ha, "STATE_DIR", state)
    monkeypatch.setattr(ha, "BACKUP_DIR", backups)
    monkeypatch.setattr(ha, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(ha, "ENV_FILE", tmp_path / ".env.agents")
    monkeypatch.setattr(ha, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _seed_state_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for table in ha.EXPECTED_STATE_TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()


def _seed_memory_index(path: Path, chunks: int) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, body TEXT)")
        conn.executemany("INSERT INTO chunks (body) VALUES (?)", [(f"b{i}",) for i in range(chunks)])
        conn.commit()
    finally:
        conn.close()


def _seed_env_file(path: Path, keys: dict[str, str]) -> None:
    path.write_text("\n".join(f"{k}={v}" for k, v in keys.items()), encoding="utf-8")


# ── Individual check tests ─────────────────────────────────────────────

def test_state_db_check_missing(sandbox):
    r = ha.check_state_db()
    assert r["status"] == "fail"


def test_state_db_check_ok(sandbox):
    _seed_state_db(sandbox / "state" / "empire_state.db")
    r = ha.check_state_db()
    assert r["status"] == "ok"
    assert "wal" in r["detail"].lower()


def test_memory_index_empty_warns(sandbox):
    path = sandbox / "state" / "memory_index.db"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE chunks (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    r = ha.check_memory_index()
    assert r["status"] == "warn"


def test_memory_index_populated_ok(sandbox):
    _seed_memory_index(sandbox / "state" / "memory_index.db", chunks=100)
    r = ha.check_memory_index()
    assert r["status"] == "ok"
    assert "100" in r["detail"]


def test_backups_no_backups_warns(sandbox):
    r = ha.check_backups()
    assert r["status"] == "warn"


def test_backups_fresh_backup_ok(sandbox):
    # Seed a backup file that's a valid SQLite DB
    bkp = sandbox / "state" / "backups" / "backup_empire_state_20260521_120000.db"
    conn = sqlite3.connect(str(bkp))
    conn.execute("CREATE TABLE x (id INT)")
    conn.close()
    r = ha.check_backups()
    assert r["status"] == "ok"


def test_guard_modes_off_for_secret_fails(sandbox, monkeypatch):
    monkeypatch.setenv("EMPIRE_HOOK_SECRET_GUARD", "off")
    r = ha.check_guard_modes()
    assert r["status"] == "fail"


def test_guard_modes_all_enforce_ok(sandbox, monkeypatch):
    monkeypatch.setenv("EMPIRE_HOOK_SECRET_GUARD", "enforce")
    monkeypatch.setenv("EMPIRE_HOOK_EXEC_GUARD", "enforce")
    monkeypatch.setenv("EMPIRE_HOOK_STATE_GUARD", "enforce")
    r = ha.check_guard_modes()
    assert r["status"] == "ok"


def test_guard_modes_fall_back_to_tracked_runtime_settings(sandbox, monkeypatch):
    for key in (
        "EMPIRE_HOOK_SECRET_GUARD",
        "EMPIRE_HOOK_EXEC_GUARD",
        "EMPIRE_HOOK_STATE_GUARD",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = sandbox / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({
        "env": {
            "EMPIRE_HOOK_SECRET_GUARD": "enforce",
            "EMPIRE_HOOK_EXEC_GUARD": "enforce",
            "EMPIRE_HOOK_STATE_GUARD": "enforce",
        }
    }), encoding="utf-8")

    r = ha.check_guard_modes()

    assert r["status"] == "ok"
    assert "tracked settings" in r["detail"]


def test_credentials_missing_env_fails(sandbox):
    r = ha.check_credentials()
    assert r["status"] == "fail"


def test_credentials_complete_ok(sandbox):
    _seed_env_file(sandbox / ".env.agents", {
        "TURSO_DATABASE_URL": "libsql://example.turso.io",
        "TURSO_AUTH_TOKEN": "deadbeef",
        "EXTRA_KEY": "value",
    })
    r = ha.check_credentials()
    assert r["status"] == "ok"


def test_disk_space_check_returns_ok_or_fail(sandbox):
    (sandbox / "tmp").mkdir()
    r = ha.check_disk_space()
    assert r["status"] in ("ok", "warn", "fail")


def test_disk_space_labels_whole_volume_not_state_directory(sandbox, monkeypatch):
    (sandbox / "tmp").mkdir()
    usage = shutil._ntuple_diskusage(total=100, used=93, free=7)
    monkeypatch.setattr(ha.shutil, "disk_usage", lambda _path: usage)

    result = ha.check_disk_space()

    assert result["status"] == "fail"
    assert "volume" in result["detail"].lower()
    assert "state/" not in result["detail"].lower()


def test_health_aggregator_surfaces_transport_failure(monkeypatch):
    monkeypatch.setattr(
        ha,
        "_telegram_transport_report",
        lambda: {"status": "red", "detail": "polling_conflict", "items": []},
        raising=False,
    )
    result = ha.check_telegram_transport()
    assert result["status"] == "fail"
    assert "polling_conflict" in result["detail"]


def test_windows_daemon_check_uses_watchdog_without_touching_pm2(monkeypatch):
    monkeypatch.setattr(ha.sys, "platform", "win32")
    monkeypatch.setattr(
        ha,
        "_fleet_watchdog_status",
        lambda: [
            {"name": "event-router", "running": True, "disabled": False,
             "unrunnable": ""},
        ],
        raising=False,
    )

    def pm2_is_forbidden(_name):
        pytest.fail("the Windows health check must not query or wake PM2")

    monkeypatch.setattr(ha.shutil, "which", pm2_is_forbidden)

    result = ha.check_daemons()

    assert result["status"] == "ok"
    assert "fleet watchdog" in result["detail"].lower()


def test_windows_daemon_check_warns_on_duplicate_roots(monkeypatch):
    monkeypatch.setattr(ha.sys, "platform", "win32")
    monkeypatch.setattr(
        ha,
        "_fleet_watchdog_status",
        lambda: [{
            "name": "event-router", "running": True, "root_count": 2,
            "root_pids": [10, 20], "disabled": False, "unrunnable": "",
        }],
        raising=False,
    )

    result = ha.check_daemons()

    assert result["status"] == "warn"
    assert "event-router" in result["detail"]
    assert "duplicate" in result["detail"].lower()


def test_linux_daemon_check_keeps_the_pm2_vps_path(monkeypatch):
    monkeypatch.setattr(ha.sys, "platform", "linux")
    monkeypatch.setattr(ha.shutil, "which", lambda name: "/usr/bin/pm2")
    completed = subprocess.CompletedProcess(
        ["pm2", "jlist"], 0,
        stdout=json.dumps([
            {"name": "event-router", "pm2_env": {"status": "online"}},
        ]),
        stderr="",
    )
    monkeypatch.setattr(ha, "safe_run", lambda *a, **k: completed)

    result = ha.check_daemons()

    assert result["status"] == "ok"
    assert "pm2" in result["detail"].lower()


# ── Aggregation tests ──────────────────────────────────────────────────

def test_run_all_returns_structured_report(sandbox):
    report = ha.run_all()
    assert "timestamp" in report
    assert "results" in report
    assert len(report["results"]) == len(ha.CHECKS)
    assert "summary" in report
    assert report["summary"]["overall"] in ("HEALTHY", "HEALTHY_WITH_WARNINGS", "DEGRADED")


def test_render_text_includes_glyphs(sandbox):
    report = ha.run_all()
    text = ha.render_text(report)
    assert "Empire Health Report" in text
    assert any(glyph in text for glyph in ("[ OK ]", "[WARN]", "[FAIL]"))


def test_json_output_is_valid(sandbox, capsys, monkeypatch):
    monkeypatch.setattr(ha, "CHECKS", [("Always OK", lambda: ha._ok("yes"))])
    rc = ha.main(["--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["overall"] == "HEALTHY"
    assert rc == 0


def test_quiet_mode_exit_codes(sandbox, monkeypatch):
    # Healthy: exit 0
    monkeypatch.setattr(ha, "CHECKS", [("Always OK", lambda: ha._ok("yes"))])
    assert ha.main(["--quiet"]) == 0
    # With a fail: exit 1
    monkeypatch.setattr(ha, "CHECKS", [("Always FAIL", lambda: ha._fail("nope"))])
    assert ha.main(["--quiet"]) == 1


def test_check_exception_is_caught_as_fail(sandbox, monkeypatch):
    def boom():
        raise RuntimeError("kaboom")
    monkeypatch.setattr(ha, "CHECKS", [("Exploder", boom)])
    report = ha.run_all()
    assert report["results"][0]["status"] == "fail"
    assert "RuntimeError" in report["results"][0]["detail"]
