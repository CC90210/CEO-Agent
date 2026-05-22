"""Shared subprocess constants + helpers for scripts/.

Single source of truth for the patterns that suppress visible terminal
pop-ups when a background daemon (PM2, scheduler, n8n handler) shells
out to a child process on Windows:

  1. WINDOWLESS_FLAGS  — CREATE_NO_WINDOW bit for subprocess creationflags
  2. DETACHED_FLAGS    — CREATE_NO_WINDOW | DETACHED_PROCESS, for spawns
                         that must outlive the parent (long-lived daemons)
  3. prefer_pythonw()  — promote python.exe → pythonw.exe (no console
                         subsystem) for any long-lived Python child
  4. safe_run()        — drop-in subprocess.run with windowless default
  5. safe_popen()      — drop-in subprocess.Popen with windowless default
  6. safe_daemon_popen() — safe_popen + DETACHED_PROCESS for daemons

CANONICAL USAGE — any subprocess call that runs from a background daemon
(PM2-managed, scheduler-managed, hook-driven, n8n-action-driven) MUST go
through safe_run / safe_popen / safe_daemon_popen. Direct subprocess.run
or subprocess.Popen calls in daemon-spawned code are blocked by the
PreToolUse subprocess_guard.py hook.

Example:
    from _subprocess_helpers import safe_run, safe_popen, prefer_pythonw

    safe_run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    safe_popen([str(prefer_pythonw(sys.executable)), "daemon.py"])
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Union


def windowless_startupinfo() -> Optional["subprocess.STARTUPINFO"]:
    """Return a STARTUPINFO that hides console windows on Windows.
    None on non-Windows. Required for .cmd / .bat shim invocations
    (npm-installed binaries, playwright.cmd etc.) where the conhost
    leaks despite CREATE_NO_WINDOW."""
    if os.name != "nt":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si

# 0x08000000 == CREATE_NO_WINDOW on Windows. Suppresses the conhost
# allocation that otherwise appears whenever a pythonw / Node daemon
# spawns a python.exe child (Windows allocates a fresh console because
# the parent has none to share). Zero on non-Windows so call sites
# stay portable.
WINDOWLESS_FLAGS: int = 0x08000000 if sys.platform == "win32" else 0

# 0x00000008 == DETACHED_PROCESS. Combined with CREATE_NO_WINDOW, used
# for daemon-style children that must keep running after the parent
# exits (override consumer, event router, sequence runner). Zero on
# non-Windows.
DETACHED_FLAGS: int = (0x08000000 | 0x00000008) if sys.platform == "win32" else 0


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


def command_without_cmd_shim(bin_path: str) -> list[str]:
    """Return argv that bypasses npm .cmd/.bat shims on Windows.

    CREATE_NO_WINDOW + SW_HIDE normally suppresses console windows, but
    cmd.exe can still allocate a visible conhost before an npm shim hands
    off to node.exe. npm's generated shim contains the real JS entrypoint
    as "%dp0%\\node_modules\\..."; invoking that through node.exe keeps
    cmd.exe out of the process tree entirely.
    """
    path = Path(bin_path)
    if os.name != "nt" or path.suffix.lower() not in {".cmd", ".bat"}:
        return [bin_path]
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [bin_path]
    match = re.search(r'"%dp0%\\([^"]+)"\s+%\*', text)
    if match:
        target = path.parent / match.group(1)
    elif path.name.lower() == "npm.cmd":
        target = path.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    else:
        return [bin_path]
    node = shutil.which("node")
    bundled_node = path.parent / "node.exe"
    if bundled_node.exists():
        node = str(bundled_node)
    if not node or not target.exists():
        return [bin_path]
    return [node, str(target)]


def _merge_creationflags(kw: dict, base: int) -> dict:
    """OR the caller's creationflags with `base` so an explicit
    DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, etc. isn't lost."""
    existing = kw.pop("creationflags", 0) or 0
    kw["creationflags"] = existing | base
    return kw


def _auto_startupinfo(kw: dict, cmd: Any) -> dict:
    """Auto-apply STARTUPINFO with SW_HIDE for shell=True or .cmd/.bat
    shim invocations on Windows where CREATE_NO_WINDOW alone can leak
    a console (npm-installed binaries, cmd.exe re-shells)."""
    if os.name != "nt" or "startupinfo" in kw:
        return kw
    needs = False
    if kw.get("shell"):
        needs = True
    elif isinstance(cmd, (list, tuple)) and cmd:
        first = str(cmd[0]).lower()
        first_name = Path(first).name
        if (
            first.endswith(".cmd")
            or first.endswith(".bat")
            or first_name in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
        ):
            needs = True
    if needs:
        kw["startupinfo"] = windowless_startupinfo()
    return kw


def safe_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Drop-in replacement for subprocess.run that hides the console on
    Windows by default. Any caller-supplied creationflags are preserved
    (ORed with WINDOWLESS_FLAGS). Auto-applies windowless STARTUPINFO
    on shell=True or .cmd/.bat shim spawns. Pass-through everywhere else."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, WINDOWLESS_FLAGS)
        kwargs = _auto_startupinfo(kwargs, cmd)
    return subprocess.run(cmd, **kwargs)


def safe_popen(cmd: Any, **kwargs: Any) -> subprocess.Popen:
    """Drop-in replacement for subprocess.Popen that hides the console on
    Windows by default. Same auto-detection as safe_run."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, WINDOWLESS_FLAGS)
        kwargs = _auto_startupinfo(kwargs, cmd)
    return subprocess.Popen(cmd, **kwargs)


def safe_daemon_popen(cmd: Any, **kwargs: Any) -> subprocess.Popen:
    """Popen for long-lived daemons that must outlive the parent. Adds
    DETACHED_PROCESS on top of CREATE_NO_WINDOW so the child has no
    parent-process linkage and won't be SIGINT'd if the parent dies."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, DETACHED_FLAGS)
    return subprocess.Popen(cmd, **kwargs)


__all__ = [
    "WINDOWLESS_FLAGS",
    "DETACHED_FLAGS",
    "windowless_startupinfo",
    "prefer_pythonw",
    "command_without_cmd_shim",
    "safe_run",
    "safe_popen",
    "safe_daemon_popen",
]
