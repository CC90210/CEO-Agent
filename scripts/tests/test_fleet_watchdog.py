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
