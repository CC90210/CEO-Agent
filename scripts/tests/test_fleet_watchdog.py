"""Tests for the fleet watchdog and the parity check that reports on it.

Every assertion here corresponds to something that actually went wrong on
2026-08-28, when the coordination bridge was found dead for two days while
`machine_parity` reported GREEN — at parity.

None of these behaviours had a test. The health check that is supposed to be the
fleet's early warning was itself unpinned, which is why it could drift into
lying without anything noticing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ops import fleet_watchdog as fw  # noqa: E402


# ---------------------------------------------------------------- identity ---

def test_identity_never_resolves_to_a_bare_interpreter():
    """`pythonw.exe` appears in dozens of unrelated command lines. Matching on it
    reports every daemon as UP — the naive check did exactly that and produced
    four false UPs while those daemons were dead."""
    app = {"name": "x", "script": r"C:\repo\.venv\Scripts\pythonw.exe",
           "args": ["-m", "bravo_cli.bridge_chat_server"], "interp": ""}
    ident = fw._identity(app)
    assert ident == "bravo_cli.bridge_chat_server"
    assert "pythonw" not in ident


def test_identity_uses_the_script_when_there_is_one():
    app = {"name": "bravo-scheduler", "script": "scripts/scheduler.py",
           "args": [], "interp": "pythonw.exe"}
    assert fw._identity(app) == "scheduler.py"


# ------------------------------------------------------------- unrunnable ---

def test_entry_without_a_target_is_flagged_not_launched(monkeypatch, tmp_path):
    """breeze-live-watch records args ['loop','--interval','300'] and NO script,
    so a naive build runs `pythonw.exe loop --interval 300` — executing a file
    called `loop`. Skipping it silently would be worse: the operator would
    believe it was supervised."""
    dump = tmp_path / "dump.pm2"
    dump.write_text(json.dumps([{
        "name": "breeze-live-watch", "script": None,
        "args": ["loop", "--interval", "300"],
        "exec_interpreter": "pythonw.exe", "cwd": str(REPO_ROOT),
    }]), encoding="utf-8")
    monkeypatch.setattr(fw, "DUMP", dump)
    monkeypatch.setattr(fw, "_ecosystem_apps", lambda: {})
    entries = fw.manifest()
    assert len(entries) == 1
    assert entries[0]["unrunnable"], "must be flagged, not silently dropped"
    ok, detail = fw.start(entries[0], dry=True)
    assert ok is False, "an unrunnable entry must never be launched"
    assert "no script" in detail


def test_committed_spec_beats_machine_state(monkeypatch, tmp_path):
    """dump.pm2 says WHAT ran; ecosystem.config.js says HOW to run it and is more
    complete — it recovered bravo-ig-dm, which the dump stored with no script."""
    dump = tmp_path / "dump.pm2"
    dump.write_text(json.dumps([{
        "name": "bravo-ig-dm", "script": None, "args": None,
        "exec_interpreter": "pythonw.exe", "cwd": str(REPO_ROOT),
    }]), encoding="utf-8")
    monkeypatch.setattr(fw, "DUMP", dump)
    monkeypatch.setattr(fw, "_ecosystem_apps", lambda: {
        "bravo-ig-dm": {"name": "bravo-ig-dm",
                        "script": "scripts/integrations/ig_dm_daemon.py",
                        "args": None, "interp": "pythonw.exe"}})
    entries = fw.manifest()
    assert entries[0]["script"].endswith("ig_dm_daemon.py")
    assert not entries[0]["unrunnable"]


# --------------------------------------------------------------- disabled ---

def test_an_operator_stop_must_stick(monkeypatch, tmp_path):
    """A `disable` that silently reverses within five minutes is worse than a
    daemon being down, because it is invisible. bravo-ig-dm sends Instagram DMs;
    an unwanted restart is an outward effect."""
    disabled = tmp_path / "fleet_disabled.json"
    disabled.write_text(json.dumps(["bravo-ig-dm"]), encoding="utf-8")
    monkeypatch.setattr(fw, "DISABLED", disabled)
    assert "bravo-ig-dm" in fw.disabled_names()


# -------------------------------------------------- parity check behaviour ---

def _parity():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import machine_parity
    return machine_parity


def test_parity_does_not_invoke_pm2_when_no_daemon_is_alive(monkeypatch):
    """Calling pm2 against a blocked pipe SPAWNS an orphan daemon; 23 accumulated
    that way, several from health checks. A health check that worsens what it
    measures is not a health check."""
    mp = _parity()
    calls: list[list[str]] = []
    real_run = mp.subprocess.run

    def spy(cmd, *a, **k):
        if isinstance(cmd, list) and cmd and cmd[0] == "pm2":
            calls.append(cmd)
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(mp, "_pm2_daemon_alive", lambda: False)
    monkeypatch.setattr(mp.subprocess, "run", spy)
    mp.check_tls_keylog()
    assert calls == [], f"pm2 was invoked with no daemon alive: {calls}"


def test_daemon_detector_does_not_match_its_own_invocation(monkeypatch):
    """The first version substring-searched the whole process table, so any
    command that merely MENTIONED the daemon path — a grep, a filter, the
    diagnostic asking the question — matched. It returned True with zero daemons
    running, the guard fell through, and it leaked the daemon it existed to
    prevent. A detector that matches its own invocation is measuring itself."""
    mp = _parity()
    fake_table = (
        "commandline\n"
        r'wmic process where "commandline like \'%pm2\lib\daemon.js%\'" get name' "\n"
        "powershell -command get-process | where { $_.commandline -like '*pm2\\lib\\daemon.js*' }\n"
    )

    class R:
        stdout = fake_table
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    assert mp._pm2_daemon_alive() is False, (
        "matched a QUERY about the daemon rather than the daemon itself")


def test_daemon_detector_still_finds_a_real_daemon(monkeypatch):
    """Break the test before trusting it: the exclusion must not suppress a
    genuine daemon line."""
    mp = _parity()

    class R:
        stdout = ("commandline\n"
                  r'"c:\program files\nodejs\node.exe" c:\users\user\appdata\roaming\npm\node_modules\pm2\lib\daemon.js'
                  "\n")
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    assert mp._pm2_daemon_alive() is True


def test_parity_liveness_has_exactly_one_definition():
    """machine_parity must ASK fleet_watchdog rather than carry a second copy.

    They agreed on the day they were written, which is how this class hides —
    the fifth instance in this subsystem after two claim mechanisms, two
    coverage implementations, two ownership maps and two identity lists. The
    latent divergence was real: the watchdog honours an operator `disable` and
    the private copy did not, so a deliberate stop would have read as a parity
    FAILURE and trained the operator to ignore the check.
    """
    src = (REPO_ROOT / "scripts" / "machine_parity.py").read_text(encoding="utf-8")
    assert "from ops import fleet_watchdog" in src
    assert "fleet_watchdog.status()" in src


# ------------------------------------------------- unreadable process table ---
# Added 2026-08-28 after the SECOND incident that day. `_process_table()`
# returned "" on any failure, and `status()` tested `ident in table`, which is
# False for every daemon against an empty string. An unreadable table therefore
# read as "the entire fleet is dead" — and this watchdog's response to a dead
# fleet is to start the fleet, every five minutes from Task Scheduler.
#
# Found running side by side: four bravo-scheduler instances (started 21:26,
# 23:56, 00:01, 00:10) and duplicate event-routers, so every cron in the empire
# executed up to 4x — four concurrent inbound-email sweeps racing one mailbox,
# eight email_engine processes live at once, each classifying the same mail and
# each marking it \Seen. It also self-amplifies: duplicates raise load, load
# slows the table read, a slow read times out, and a timeout starts more
# duplicates.


@pytest.fixture
def restore_table():
    original = fw._process_table
    yield
    fw._process_table = original


def test_unreadable_table_raises_rather_than_reporting_down(restore_table):
    """If we cannot prove a daemon is down, we must not start one."""
    fw._process_table = lambda: None
    with pytest.raises(fw.ProcessTableUnreadable):
        fw.status()


def test_empty_table_raises_too(restore_table):
    """The original bug's exact shape. `table is None` alone lets "" through,
    so the guard has to be falsy-based, not None-based."""
    fw._process_table = lambda: ""
    with pytest.raises(fw.ProcessTableUnreadable):
        fw.status()


def test_valid_table_still_resolves_liveness(restore_table):
    fw._process_table = lambda: ("pythonw.exe c:/repo/scripts/scheduler.py\n"
                                 "node c:/repo/telegram_agent.js")
    running = {r["name"] for r in fw.status() if r["running"]}
    assert "bravo-scheduler" in running
    assert "bravo-telegram" in running


def test_daemon_absent_from_a_readable_table_is_down(restore_table):
    """Fail-closed must not become fail-useless: a genuinely absent daemon still
    has to report down, or the watchdog would never start anything again."""
    fw._process_table = lambda: "node c:/repo/telegram_agent.js"
    down = {r["name"] for r in fw.status() if not r["running"] and not r["disabled"]}
    assert "bravo-scheduler" in down


def test_real_process_table_can_see_python_processes():
    """Guards a near-miss. psutil is 5x faster than wmic and was tried as the
    source; on this machine it returns an EMPTY cmdline for 163 of 579
    processes, including every detached pythonw daemon this file supervises. It
    reported four running daemons as DOWN, which would have started a duplicate
    of each — the very duplication this module now guards against, caused by the
    fix for it. Any future swap of the source must still see live processes."""
    table = fw._process_table()
    if table is None:
        pytest.skip("process table unreadable in this environment")
    assert "python" in table, "process-table source cannot see python processes"


# -------------------------------------------------------------- run lock ---

def test_run_lock_is_exclusive(tmp_path, monkeypatch):
    """Two overlapping passes each seeing a daemon down, and each starting one,
    is the other half of how four schedulers came to exist. The Task Scheduler
    fires this every 5 minutes; a pass can take longer than that."""
    monkeypatch.setattr(fw, "RUN_LOCK", tmp_path / "wd.lock")
    assert fw._acquire_run_lock() is True
    assert fw._acquire_run_lock() is False, "second concurrent pass must be refused"
    fw._release_run_lock()
    assert fw._acquire_run_lock() is True, "lock must be reusable after release"
    fw._release_run_lock()


def test_stale_lock_is_reclaimed(tmp_path, monkeypatch):
    """A pass killed mid-run must not disable supervision forever.

    Ages the lock file rather than setting the threshold to 0: a lock written
    microseconds ago is legitimately NOT older than zero seconds, so that
    version tested a degenerate boundary instead of the real condition (a lock
    left behind by a process that died some time ago).
    """
    import os as _os
    lock = tmp_path / "wd.lock"
    monkeypatch.setattr(fw, "RUN_LOCK", lock)
    lock.write_text("99999")
    stale = time.time() - (fw.LOCK_STALE_SEC + 60)
    _os.utime(lock, (stale, stale))
    assert fw._acquire_run_lock() is True, "a stale lock must be reclaimable"
    fw._release_run_lock()


def test_fresh_lock_is_not_reclaimed(tmp_path, monkeypatch):
    """The other half: a lock held by a pass that is genuinely still running
    must be respected, or the staleness escape hatch defeats the lock."""
    lock = tmp_path / "wd.lock"
    monkeypatch.setattr(fw, "RUN_LOCK", lock)
    lock.write_text("99999")
    assert fw._acquire_run_lock() is False, "a fresh lock must be honoured"
