"""Windows operator surfaces must never wake the retired PM2 daemon."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def _assert_no_pm2_invocation(source: str) -> None:
    assert "Get-Command pm2" not in source
    assert not re.search(r"(?im)^\s*(?:&\s*)?pm2(?:\.cmd)?\s", source)


def test_windows_operator_routes_status_logs_and_restart_through_watchdog():
    source = _source("ai_operator.ps1")

    _assert_no_pm2_invocation(source)
    assert "fleet_watchdog.py" in source
    assert '@("status")' in source
    assert '@("logs"' in source
    assert '@("restart"' in source


def test_windows_doctor_reads_watchdog_status_without_pm2():
    source = _source("ai_workstation_doctor.ps1")

    _assert_no_pm2_invocation(source)
    assert "Get-FleetSnapshot" in source
    assert "fleet_watchdog.py" in source
    assert '"status", "--json"' in source
    assert "Get-Pm2Snapshot" not in source

    duplicate_check = source.index("$_.root_count -gt 1")
    disabled_check = source.index("$_.disabled", duplicate_check)
    running_check = source.index("$_.running", duplicate_check)
    assert duplicate_check < disabled_check < running_check


def test_login_console_cannot_resurrect_pm2():
    tail = _source("bravo_console_tail.cmd")
    launcher = _source("bravo_console_launcher.vbs")

    _assert_no_pm2_invocation(tail)
    assert "fleet_watchdog.py" in tail
    assert "daemon-*.log" in tail
    assert "pm2 logs" not in launcher.lower()
