"""Windows console-suppression helpers for the bravo_cli package.

Mirrors scripts/_subprocess_helpers.py for the CLI/bridge codebase.
Two reasons it lives here separately:
  1. bravo_cli is a proper Python package — `from _subprocess_helpers
     import …` from scripts/ would require sys.path gymnastics that
     break when the CLI is pip-installed.
  2. The bridge needs an extra helper (`windowless_startupinfo`) that
     scripts/ doesn't — the heartbeat probes call .cmd shims like
     `playwright.cmd`, where CREATE_NO_WINDOW alone leaks a popup.

Usage:
    from ._subprocess_helpers import WINDOWLESS_FLAGS, windowless_startupinfo

    subprocess.run(
        [...],
        creationflags=WINDOWLESS_FLAGS,
        startupinfo=windowless_startupinfo(),
    )

When to pass startupinfo
  - Calling a .cmd / .bat shim (npm-installed binaries on Windows)
  - Calling anything that re-shells via cmd.exe
  - When in doubt, pass it — it's a no-op on non-Windows.

When the constant alone is enough
  - Direct .exe spawns (python.exe, claude.exe, ffmpeg.exe)
  - subprocess.Popen with shell=False and a fully-resolved exe path
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

# 0x08000000 == CREATE_NO_WINDOW on Windows. Hides the conhost flicker
# direct-exe spawns would otherwise create.
WINDOWLESS_FLAGS: int = 0x08000000 if os.name == "nt" else 0


def windowless_startupinfo() -> Optional["subprocess.STARTUPINFO"]:
    """Return a STARTUPINFO that hides console windows on Windows.
    None on non-Windows. Required for .cmd / .bat shim invocations
    where CREATE_NO_WINDOW alone is not enough."""
    if os.name != "nt":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si
