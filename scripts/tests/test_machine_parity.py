"""Tests for the two machine_parity checks that were built on PM2.

PM2 stopped being this fleet's supervisor on 2026-08-28 (e7d0a50f replaced it
with scripts/ops/fleet_watchdog.py; 0e88aa21 disabled both "PM2 Resurrect"
tasks because their S4U principal ran them in Windows Session 0). Neither check
was updated, and they failed in opposite directions:

  * `tls-keylog` refused to query pm2 without a live daemon — correctly, since
    each such call leaks an orphan — and there is deliberately no live daemon.
    So it returned "no pm2 daemon is running" forever. A permanently-red check
    trains its operator to ignore the whole report.

  * `pm2-persistence` read the DISABLED "PM2 Resurrect" task, parsed its
    triggers, never once read its state, and reported GREEN: "boot trigger +
    battery-safe". It certified an unattended-recovery path that had been
    switched off on purpose.

Both are pinned here because neither had a test, which is why both could drift
into lying without anything noticing.

Run: python -m pytest scripts/tests/test_machine_parity.py -v
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import machine_parity as mp  # noqa: E402
from ops import fleet_watchdog as fw  # noqa: E402

WINDOWS_ONLY = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="the scheduled-task supervisor is a Windows concern; the check returns early elsewhere",
)

# A schtasks /v LIST record for a healthy watchdog task: one block per trigger,
# which is why every field has to be read as a SET of values.
WATCHDOG_OK = """
TaskName:                             \\Bravo Fleet Watchdog
Status:                               Ready
Logon Mode:                           Interactive only
Scheduled Task State:                 Enabled
Repeat: Every:                        0 Hour(s), 5 Minute(s)
TaskName:                             \\Bravo Fleet Watchdog
Logon Mode:                           Interactive only
Scheduled Task State:                 Enabled
Repeat: Every:                        N/A
"""
PM2_RETIRED = """
TaskName:                             \\PM2 Resurrect
Logon Mode:                           Interactive/Background
Scheduled Task State:                 Disabled
Repeat: Every:                        N/A
"""
ROWS_UP = [
    {"name": "bravo-scheduler", "running": True, "disabled": False, "unrunnable": ""},
    {"name": "event-router", "running": True, "disabled": False, "unrunnable": ""},
]


@pytest.fixture
def fleet(monkeypatch):
    """A healthy machine, with every external answer stubbed. Each test breaks
    exactly one of them, so a green result can only come from the thing under
    test actually holding."""
    tasks = {"Bravo Fleet Watchdog": (WATCHDOG_OK, ""),
             "PM2 Resurrect": (PM2_RETIRED, ""),
             "PM2 Resurrect on Login": (PM2_RETIRED, "")}
    rows = list(ROWS_UP)
    monkeypatch.setattr(mp, "_schtasks_query", lambda name: tasks.get(name, (None, "")))
    monkeypatch.setattr(mp, "_has_battery", lambda: False)
    monkeypatch.setattr(fw, "status", lambda: rows)
    return {"tasks": tasks, "rows": rows}


def _check(fleet):
    _name, ok, detail, _hint = mp.check_fleet_persistence()
    return ok, detail


# ----------------------------------------------------------- control ---

@WINDOWS_ONLY
def test_a_healthy_fleet_is_green(fleet):
    """Break the test before trusting it: if this cannot go green, every
    assertion below is vacuous."""
    ok, detail = _check(fleet)
    assert ok, detail
    assert "enabled, interactive" in detail
    # schtasks labels contain their own colons ("Repeat: Every:"), so a
    # split(":", 1) leaves half the label in the value and the report reads
    # "repeats every Every: 0 Hour(s), 5 Minute(s)".
    assert "repeats every 0 Hour(s), 5 Minute(s)" in detail


# ------------------------------------------- the supervisor must exist ---

@WINDOWS_ONLY
def test_a_missing_watchdog_task_is_a_failure(fleet):
    fleet["tasks"]["Bravo Fleet Watchdog"] = (None, "")
    ok, detail = _check(fleet)
    assert not ok and "no 'Bravo Fleet Watchdog' scheduled task" in detail


@WINDOWS_ONLY
def test_a_disabled_watchdog_task_is_a_failure(fleet):
    """THE regression. The old check read a task's triggers and never its state,
    so a deliberately disabled supervisor reported as 'boot trigger +
    battery-safe'. Reading triggers without reading state is how a switched-off
    recovery path gets certified as working."""
    fleet["tasks"]["Bravo Fleet Watchdog"] = (WATCHDOG_OK.replace("Enabled", "Disabled"), "")
    ok, detail = _check(fleet)
    assert not ok and "is DISABLED" in detail


@WINDOWS_ONLY
def test_an_s4u_principal_is_a_failure(fleet):
    """'Interactive/Background' means the task can run with nobody logged on,
    i.e. in Session 0 — where a supervisor cannot read a session-1 command line,
    concludes the whole fleet is absent, and starts a second invisible copy of
    every daemon. That is the documented cause of four concurrent
    bravo-schedulers on 2026-08-28."""
    fleet["tasks"]["Bravo Fleet Watchdog"] = (
        WATCHDOG_OK.replace("Interactive only", "Interactive/Background"), "")
    ok, detail = _check(fleet)
    assert not ok and "Session 0" in detail


@WINDOWS_ONLY
def test_a_non_repeating_watchdog_task_is_a_failure(fleet):
    """Recovery within minutes is the whole point of the 5-minute trigger. With
    only a logon trigger, a daemon that dies at 09:00 stays dead until the next
    logon."""
    fleet["tasks"]["Bravo Fleet Watchdog"] = (
        WATCHDOG_OK.replace("0 Hour(s), 5 Minute(s)", "N/A"), "")
    ok, detail = _check(fleet)
    assert not ok and "no repeating trigger" in detail


# ------------------------------------------------------------ battery ---

_ON_BATTERY = WATCHDOG_OK + "Power Management:  Stop On Battery Mode, No Start On Batteries\n"


@WINDOWS_ONLY
def test_no_start_on_batteries_fails_on_a_laptop(fleet, monkeypatch):
    monkeypatch.setattr(mp, "_has_battery", lambda: True)
    fleet["tasks"]["Bravo Fleet Watchdog"] = (_ON_BATTERY, "")
    ok, detail = _check(fleet)
    assert not ok and "will not start on battery" in detail


@WINDOWS_ONLY
def test_no_start_on_batteries_is_ignored_on_a_desktop(fleet):
    """It is the schtasks DEFAULT, and a desktop can never be on battery. Firing
    on it here would be permanent noise, and noise is how the laptop case above
    gets ignored."""
    fleet["tasks"]["Bravo Fleet Watchdog"] = (_ON_BATTERY, "")
    ok, detail = _check(fleet)
    assert ok, detail


# ------------------------------------------- exactly ONE supervisor ---

@pytest.mark.parametrize("retired", ["PM2 Resurrect", "PM2 Resurrect on Login"])
@WINDOWS_ONLY
def test_a_re_enabled_pm2_resurrect_task_is_a_failure(fleet, retired):
    """Two supervisors, neither able to see the other's daemons, IS the
    2026-08-28 incident. Re-enabling either task recreates it."""
    fleet["tasks"][retired] = (PM2_RETIRED.replace("Disabled", "Enabled"), "")
    ok, detail = _check(fleet)
    assert not ok and "is ENABLED again" in detail


# -------------------------------------------------------- liveness ---

@WINDOWS_ONLY
def test_an_empty_manifest_is_a_failure(fleet, monkeypatch):
    """A watchdog with nothing in its manifest supervises nothing, and every
    'is anything down?' question then answers no. Silent, and indistinguishable
    from health unless the emptiness itself is checked."""
    monkeypatch.setattr(fw, "status", list)
    ok, detail = _check(fleet)
    assert not ok and "manifest is EMPTY" in detail


@WINDOWS_ONLY
def test_a_down_daemon_is_a_failure(fleet):
    fleet["rows"].append({"name": "bravo-coord", "running": False,
                          "disabled": False, "unrunnable": ""})
    ok, detail = _check(fleet)
    assert not ok and "NOT RUNNING: bravo-coord" in detail


@WINDOWS_ONLY
def test_an_operator_stop_is_not_an_outage(fleet):
    """Paging about a deliberate `fleet_watchdog disable` is how a gate teaches
    people to ignore it. The distinction lives in fleet_watchdog.classify(), and
    this check must ask it rather than re-deriving 'down' by hand."""
    fleet["rows"].append({"name": "bravo-ig-dm", "running": False,
                          "disabled": True, "unrunnable": ""})
    ok, detail = _check(fleet)
    assert ok, detail
    assert "1 disabled" in detail


@WINDOWS_ONLY
def test_an_unreadable_process_table_is_a_failure(fleet, monkeypatch):
    """'I could not look' must never be reported as 'nothing is wrong'."""
    def _raise():
        raise fw.ProcessTableUnreadable("wmic returned nothing usable")
    monkeypatch.setattr(fw, "status", _raise)
    ok, detail = _check(fleet)
    assert not ok and "could not verify fleet liveness" in detail


@WINDOWS_ONLY
def test_a_stale_manifest_file_is_not_a_failure(fleet, monkeypatch, tmp_path):
    """The old check failed dump.pm2 at 7 days old. Nothing rewrites it any
    more — `pm2 save` needs the daemon that is blocked — so that rule was days
    from being permanently red with no possible remedy. What matters is that the
    manifest YIELDS entries, not when it was last written."""
    ancient = tmp_path / "dump.pm2"
    ancient.write_text("[]", encoding="utf-8")
    import os
    os.utime(ancient, (0, 0))
    monkeypatch.setattr(fw, "DUMP", ancient)
    ok, detail = _check(fleet)
    assert ok, detail


# ------------------------------------------ "I could not look" is not OK ---

@WINDOWS_ONLY
def test_a_broken_schtasks_is_a_failure_not_a_pass(fleet):
    """The old code did `except Exception: out = ""` and then read the empty
    string as a definite answer about the task."""
    fleet["tasks"]["Bravo Fleet Watchdog"] = (None, "schtasks errored: access denied")
    ok, detail = _check(fleet)
    assert not ok and "schtasks errored" in detail


@WINDOWS_ONLY
def test_an_unreadable_task_state_field_is_a_failure(fleet):
    """A localised or reformatted schtasks means the state field is absent. An
    absent field is unknown, and unknown is not Enabled."""
    fleet["tasks"]["Bravo Fleet Watchdog"] = (
        WATCHDOG_OK.replace("Scheduled Task State", "Zustand"), "")
    ok, detail = _check(fleet)
    assert not ok and "could not read the state" in detail


@WINDOWS_ONLY
def test_a_missing_supervisor_module_is_reported_loudly(monkeypatch):
    """If ops.fleet_watchdog cannot be imported there is no supervisor at all —
    the loudest possible finding, and the one most easily swallowed into an
    exception handler."""
    import builtins
    real_import = builtins.__import__

    def boom(name, *a, **k):
        if name == "ops" or name.startswith("ops."):
            raise ImportError("no module named ops")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "ops.fleet_watchdog", raising=False)
    monkeypatch.delitem(sys.modules, "ops", raising=False)
    monkeypatch.setattr(builtins, "__import__", boom)
    _name, ok, detail, hint = mp.check_fleet_persistence()
    assert not ok
    assert "there is no supervisor" in detail
    assert "install-task" in hint


# --------------------------------------------------------- tls-keylog ---

def test_the_keylog_probe_goes_green_when_the_guard_works():
    """Control for the mutation below."""
    _name, ok, detail, _hint = mp.check_tls_keylog()
    assert ok, detail
    assert "survive a poisoned handle" in detail


def test_the_keylog_probe_detects_a_defeated_guard(monkeypatch):
    """MUTATION. EMPIRE_ALLOW_SSLKEYLOG=1 makes neutralize_keylog() a no-op, so
    the poisoned handle reaches ssl.create_default_context() — reproducing the
    2026-07-29 outage exactly (PermissionError [Errno 13] from inside context
    construction, before a byte is sent; 31 of 145 inbox sweeps died that way).

    Without this, the probe could be passing because it never really poisons
    anything, which is the whole failure mode of the check it replaced."""
    monkeypatch.setenv("EMPIRE_ALLOW_SSLKEYLOG", "1")
    _name, ok, detail, hint = mp.check_tls_keylog()
    assert not ok, "the probe passed with the guard switched off — it proves nothing"
    assert "would die" in detail
    assert "EMPIRE_ALLOW_SSLKEYLOG" in hint


def test_no_parity_check_shells_out_to_the_pm2_cli():
    """Invoking pm2 while its named pipe is blocked SPAWNS an orphan daemon; 23
    accumulated that way, several of them from health checks. Nothing in the
    repo calls pm2 any more, and this file must not be the exception that
    reintroduces it."""
    src = (REPO_ROOT / "scripts" / "machine_parity.py").read_text(encoding="utf-8")
    for forbidden in ('"pm2", "jlist"', '["pm2"', "'pm2',", 'subprocess.run(["pm2'):
        assert forbidden not in src, f"machine_parity invokes the pm2 CLI: {forbidden}"
