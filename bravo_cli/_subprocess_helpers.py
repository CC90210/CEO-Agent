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
import sys
from pathlib import Path
from typing import Any, Optional, Union

# 0x08000000 == CREATE_NO_WINDOW on Windows. Hides the conhost flicker
# direct-exe spawns would otherwise create.
WINDOWLESS_FLAGS: int = 0x08000000 if os.name == "nt" else 0

# DETACHED_PROCESS | CREATE_NO_WINDOW — for daemon-style children that
# must keep running after the parent exits.
DETACHED_FLAGS: int = (0x08000000 | 0x00000008) if os.name == "nt" else 0


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


def prefer_pythonw(python_path: Union[str, Path]) -> Path:
    """Given a python.exe path, return the pythonw.exe sibling if it exists
    (Windows). On non-Windows or if pythonw.exe isn't present, return the
    input unchanged.

    Used wherever a Python subprocess will be long-lived and must NOT carry
    a console subsystem — pythonw.exe is the gold-standard fix because it
    physically cannot allocate a console window. Callers retain control
    over WHICH python to start from (sys.executable vs venv vs custom)."""
    p = Path(python_path)
    if sys.platform != "win32":
        return p
    cand = p.with_name(p.name.replace("python.exe", "pythonw.exe"))
    return cand if cand.exists() else p


def _merge_creationflags(kw: dict, base: int) -> dict:
    existing = kw.pop("creationflags", 0) or 0
    kw["creationflags"] = existing | base
    return kw


def safe_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run with CREATE_NO_WINDOW forced on Windows. Caller's
    creationflags are preserved (ORed). Also auto-applies the windowless
    startupinfo when shell=True or a .cmd/.bat shim is detected."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, WINDOWLESS_FLAGS)
        if "startupinfo" not in kwargs:
            if kwargs.get("shell"):
                kwargs["startupinfo"] = windowless_startupinfo()
            elif isinstance(cmd, (list, tuple)) and cmd:
                first = str(cmd[0]).lower()
                if first.endswith(".cmd") or first.endswith(".bat"):
                    kwargs["startupinfo"] = windowless_startupinfo()
    return subprocess.run(cmd, **kwargs)


def safe_popen(cmd: Any, **kwargs: Any) -> subprocess.Popen:
    """subprocess.Popen with CREATE_NO_WINDOW forced on Windows. Same
    shim auto-detection as safe_run."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, WINDOWLESS_FLAGS)
        if "startupinfo" not in kwargs:
            if kwargs.get("shell"):
                kwargs["startupinfo"] = windowless_startupinfo()
            elif isinstance(cmd, (list, tuple)) and cmd:
                first = str(cmd[0]).lower()
                if first.endswith(".cmd") or first.endswith(".bat"):
                    kwargs["startupinfo"] = windowless_startupinfo()
    return subprocess.Popen(cmd, **kwargs)


def safe_daemon_popen(cmd: Any, **kwargs: Any) -> subprocess.Popen:
    """Popen for long-lived daemons that must outlive the parent —
    CREATE_NO_WINDOW + DETACHED_PROCESS so the child has no parent
    linkage and won't be SIGINT'd when the parent exits."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, DETACHED_FLAGS)
    return subprocess.Popen(cmd, **kwargs)


__all__ = [
    "WINDOWLESS_FLAGS",
    "DETACHED_FLAGS",
    "windowless_startupinfo",
    "prefer_pythonw",
    "safe_run",
    "safe_popen",
    "safe_daemon_popen",
]
