"""Shared subprocess constants + helpers for scripts/.

Single source of truth for two patterns that used to live inline in
six+ files:
  1. WINDOWLESS_FLAGS — the CREATE_NO_WINDOW magic for subprocess calls
  2. prefer_pythonw() — promote python.exe to pythonw.exe on Windows for
     long-lived daemon spawns (no console subsystem at all)

Usage:
    from _subprocess_helpers import WINDOWLESS_FLAGS, prefer_pythonw

    subprocess.run([...], creationflags=WINDOWLESS_FLAGS)
    daemon_python = prefer_pythonw(sys.executable)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Union

# 0x08000000 == CREATE_NO_WINDOW on Windows. Hides the conhost flicker
# that otherwise appears every time a Task-Scheduler / PM2 / n8n /
# scheduler.run_script invocation shells out. Zero on non-Windows so
# code is portable.
WINDOWLESS_FLAGS: int = 0x08000000 if sys.platform == "win32" else 0


def prefer_pythonw(python_path: Union[str, Path]) -> Path:
    """Given a python.exe path, return the pythonw.exe sibling if it exists
    (Windows). On non-Windows or if pythonw.exe isn't present, return the
    input unchanged.

    Used wherever a Python subprocess will be long-lived and must NOT carry
    a console subsystem — pythonw.exe physically cannot allocate a console.
    The skool_watchdog → skool_engine spawn is the canonical example."""
    p = Path(python_path)
    if sys.platform != "win32":
        return p
    cand = p.with_name(p.name.replace("python.exe", "pythonw.exe"))
    return cand if cand.exists() else p
