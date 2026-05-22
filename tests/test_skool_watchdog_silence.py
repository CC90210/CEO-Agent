"""Lock the persistent-terminal fix in skool_watchdog.start_daemon.

CC reported on 2026-05-09 that a Windows Terminal tab kept popping up
and staying open. Triple-flag suppression (pythonw.exe + CREATE_NO_WINDOW
+ STARTUPINFO/SW_HIDE) fixed it; this test guards each leg.

ARCHIVED 2026-05-18: skool_watchdog moved to scripts/_archive/skool/
when the primary retainer ended. Tests now point at the archive so the
historical-fix guard still runs.
"""

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent
       / "scripts" / "_archive" / "skool" / "skool_watchdog.py")


def _start_daemon_block() -> str:
    text = SRC.read_text(encoding="utf-8")
    m = re.search(r"def start_daemon\([^)]*\):\s*\n([\s\S]+?)\n\ndef ", text)
    assert m, "start_daemon function not found"
    return m.group(1)


def test_pythonw_resolver_exists():
    """The watchdog must have a way to prefer pythonw over python."""
    text = SRC.read_text(encoding="utf-8")
    assert "pythonw.exe" in text, "watchdog must reference pythonw.exe"
    assert "_resolve_daemon_python" in text, (
        "expected a resolver function that picks pythonw when available"
    )


def test_start_daemon_uses_resolver_not_raw_python():
    """start_daemon must use the resolver — not the raw VENV_PYTHON.
    Picking python.exe directly would re-introduce the leak."""
    block = _start_daemon_block()
    assert "_resolve_daemon_python(" in block, (
        "start_daemon must call _resolve_daemon_python() instead of "
        "hard-coding VENV_PYTHON — pythonw is the no-leak path"
    )


def test_start_daemon_passes_all_three_suppression_flags():
    """All three layers must be present: CREATE_NO_WINDOW, STARTUPINFO,
    SW_HIDE. Any one missing and the popup can leak through ConPTY."""
    block = _start_daemon_block()
    assert "creationflags=CREATE_NO_WINDOW" in block, "missing CREATE_NO_WINDOW"
    assert "STARTUPINFO" in block, "missing STARTUPINFO instantiation"
    assert "SW_HIDE" in block, "missing SW_HIDE on STARTUPINFO"
    assert "startupinfo=startupinfo" in block, "STARTUPINFO not passed to Popen"
