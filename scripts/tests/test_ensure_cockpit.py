"""Tests for ensure_cockpit's liveness check.

The Bravo Console has been a plain cmd.exe running bravo_console_tail.cmd since
2026-08-14, when the launcher stopped using Windows Terminal. The check kept
looking for WindowsTerminal.exe, never found it, and so opened another console
on every Claude session start: 100 of them were open on 2026-09-11, each with
its own `pm2 logs` node process.

The process table is faked, so these run on any OS.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ensure_cockpit as ec  # noqa: E402

# Verbatim from this machine's process table on 2026-09-11.
LIVE_CONSOLE = ('"C:\\Windows\\System32\\cmd.exe" /k '
                '"C:\\Users\\User\\Business-Empire-Agent\\scripts\\bravo_console_tail.cmd"')
OTHER_CMD = '"C:\\Windows\\System32\\cmd.exe" /c npm run build'


def _table(monkeypatch, *cmdlines, rc=0, end=True):
    """Answer the CIM query with these cmd.exe command lines."""
    out = "\n".join([*cmdlines, *([ec._END] if end else [])]) + "\n"
    monkeypatch.setattr(ec.sys, "platform", "win32")
    monkeypatch.setattr(ec, "safe_run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, rc, stdout=out, stderr=""))


def test_the_console_the_launcher_really_starts_counts_as_alive(monkeypatch):
    """No WindowsTerminal.exe anywhere: the real state of this machine."""
    _table(monkeypatch, OTHER_CMD, LIVE_CONSOLE)
    assert ec._cockpit_is_alive() is True


def test_another_cmd_window_is_not_the_console(monkeypatch):
    _table(monkeypatch, OTHER_CMD, '"C:\\Windows\\System32\\cmd.exe"')
    assert ec._cockpit_is_alive() is False


def test_no_cmd_at_all_is_not_alive(monkeypatch):
    _table(monkeypatch)
    assert ec._cockpit_is_alive() is False


@pytest.mark.parametrize("cmdlines, rc, end", [
    ([LIVE_CONSOLE], 1, True),      # the query failed; its output proves nothing
    ([], 0, False),                 # nothing came back at all
    ([OTHER_CMD], 0, False),        # cut off before the end marker
], ids=["query-failed", "empty", "truncated"])
def test_an_unreadable_table_is_unknown_not_dead(monkeypatch, cmdlines, rc, end):
    """False means "launch one". Saying it on no evidence is the leak again."""
    _table(monkeypatch, *cmdlines, rc=rc, end=end)
    assert ec._cockpit_is_alive() is None


def test_a_query_that_raises_is_unknown(monkeypatch):
    monkeypatch.setattr(ec.sys, "platform", "win32")

    def _timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(ec, "safe_run", _timeout)
    assert ec._cockpit_is_alive() is None


def _run_main(monkeypatch, states):
    answers = iter(states)
    launches: list[int] = []
    monkeypatch.setattr(ec.sys, "platform", "win32")
    monkeypatch.setattr(ec, "_cockpit_is_alive", lambda **kw: next(answers))
    monkeypatch.setattr(ec, "_launch_cockpit", lambda: launches.append(1))
    monkeypatch.setattr(ec.time, "sleep", lambda s: None)
    return ec.main(), launches


def test_an_open_console_is_left_alone(monkeypatch):
    rc, launches = _run_main(monkeypatch, [True])
    assert (rc, launches) == (0, [])


def test_an_unreadable_table_never_launches(monkeypatch):
    rc, launches = _run_main(monkeypatch, [None])
    assert (rc, launches) == (0, []), "a blind launch is how 100 consoles piled up"


def test_a_missing_console_is_launched_once(monkeypatch):
    rc, launches = _run_main(monkeypatch, [False, True])
    assert (rc, launches) == (0, [1])


def test_the_post_launch_checks_stay_inside_the_five_second_budget(monkeypatch):
    """Each check after a launch gets only what is left of the budget. With the
    query's own 30s timeout, one stalled read could hold the session start far
    past the 5s it promises. (Codex, PR #79.)"""
    timeouts: list[float] = []
    answers = iter([False, None, True])     # missing, a stalled read, then up

    def _alive(timeout=30):
        timeouts.append(timeout)
        return next(answers)

    monkeypatch.setattr(ec.sys, "platform", "win32")
    monkeypatch.setattr(ec, "_cockpit_is_alive", _alive)
    monkeypatch.setattr(ec, "_launch_cockpit", lambda: None)
    monkeypatch.setattr(ec.time, "sleep", lambda s: None)
    assert ec.main() == 0
    assert len(timeouts) == 3
    assert all(t <= 5 for t in timeouts[1:]), timeouts


def test_the_query_runs_under_the_callers_timeout(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(ec.sys, "platform", "win32")
    monkeypatch.setattr(ec, "safe_run", lambda cmd, **kw: seen.update(kw) or
                        subprocess.CompletedProcess(cmd, 0, stdout=ec._END + "\n", stderr=""))
    ec._cockpit_is_alive(timeout=2.5)
    assert seen["timeout"] == 2.5


def test_the_check_matches_what_the_launcher_runs():
    """The defect was this check drifting away from the launcher. If the
    launcher ever stops running the tail through cmd.exe, this fails before
    another leak can start."""
    vbs = ec.LAUNCHER_VBS.read_text(encoding="utf-8", errors="replace")
    assert f'"{ec.CONSOLE_MARKER}"' in vbs
    assert 'Cmd = "cmd /k' in vbs
    assert "Name = 'cmd.exe'" in " ".join(ec._CONSOLE_QUERY)
