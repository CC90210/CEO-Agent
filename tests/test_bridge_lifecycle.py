"""Smoke-tests for `bravo bridge` lifecycle commands.

These don't actually start the bridge — they verify the dispatcher
wiring (action choices, restart helpers exist) so a typo in the
argparse table doesn't ship silently.
"""

import argparse

from bravo_cli import local_bridge as lb
from bravo_cli import main as bm


def test_bridge_action_choices_include_restart():
    """`bravo bridge restart` must be reachable through the top-level
    argparse table — adding the function but forgetting the choice
    leaves it unreachable from the CLI."""
    parser = bm.build_parser()
    # Walk the subparsers to find the bridge subcommand.
    bridge_action = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            bridge_parser = action.choices.get("bridge")
            assert bridge_parser is not None, "bridge subparser missing"
            for sub in bridge_parser._actions:
                if isinstance(sub, argparse._StoreAction) and sub.dest == "action":
                    bridge_action = sub
                    break
    assert bridge_action is not None, "bridge action arg not found"
    assert "restart" in bridge_action.choices, \
        f"bridge action choices missing 'restart' (got {bridge_action.choices})"
    assert "start" in bridge_action.choices
    assert "stop" in bridge_action.choices


def test_local_bridge_exports_restart_helpers():
    """The two helpers cmd_restart relies on must exist by name. Renaming
    silently would break restart on Windows where _kill_chat_server scans
    wmic output, OR on the Startup-folder fallback path."""
    for fn in ("cmd_restart", "_kill_chat_server", "_spawn_chat_server",
               "cmd_start", "cmd_stop"):
        assert callable(getattr(lb, fn, None)), f"local_bridge missing {fn}"


def test_kill_chat_server_no_op_when_nothing_running(tmp_path, monkeypatch):
    """When no PID file exists AND no python process matches, the
    helper must return (False, msg) — never raise. This is the path
    that runs on a clean boot before serve_forever has ever started."""
    # Point OASIS_DIR / PID paths at an empty tmpdir so we don't
    # accidentally kill a real bridge running on the dev machine.
    monkeypatch.setattr(lb, "OASIS_DIR", tmp_path)
    monkeypatch.setattr(lb, "PID_PATH", tmp_path / "bridge.pid")
    monkeypatch.setattr(lb, "_chat_pid_path", lambda: tmp_path / "bridge_chat.pid")

    # Force the wmic/ps fallback to return nothing matching.
    import subprocess
    real_check_output = subprocess.check_output

    def fake_check_output(args, *a, **kw):  # type: ignore[no-untyped-def]
        # Return empty for the process-list scan; defer everything else
        # to the real call (defensive — currently nothing else uses it).
        if isinstance(args, list) and (args[0] in ("wmic", "ps")):
            return b""
        return real_check_output(args, *a, **kw)

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    ok, msg = lb._kill_chat_server()
    assert ok is False
    assert "no chat-server" in msg.lower()
