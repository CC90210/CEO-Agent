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
import re
import shutil
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


# ─────────────────────────────────────────────────────────────────────
# Enriched PATH discovery for GUI-launched bridges (macOS / Linux).
# Electron + launchd inherit a slim LaunchServices PATH that misses
# Homebrew, npm-global, Bun, Deno, nvm, etc. Both bridge_chat_server
# (chat dispatch) and bridge_tools (cli_status + install_cli) need
# the same lookup. Lives here so they don't drift.
# ─────────────────────────────────────────────────────────────────────

_LOGIN_SHELL_PATH_CACHE: Optional[str] = None
_CLI_PATH_CACHE: dict = {}


def macos_linux_search_paths() -> list[str]:
    """Common install directories an Electron/launchd-spawned process
    misses because its PATH is the slim LaunchServices set. Apple
    Silicon Homebrew is /opt/homebrew/bin; Intel is /usr/local/bin;
    npm global is ~/.npm-global/bin; etc."""
    home = os.path.expanduser("~")
    return [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/local/sbin",
        f"{home}/.npm-global/bin",
        f"{home}/.bun/bin",
        f"{home}/.local/bin",
        f"{home}/.deno/bin",
        f"{home}/.cargo/bin",
        "/usr/bin",
        "/bin",
    ]


def login_shell_path() -> Optional[str]:
    """Spawn `bash -lc 'echo $PATH'` once and cache the result. A login
    shell sources ~/.zshrc / ~/.bash_profile so the PATH matches what
    the user sees in Terminal — including nvm's `~/.nvm/versions/node/
    <version>/bin`. 1.5s timeout protects against a wedged profile."""
    global _LOGIN_SHELL_PATH_CACHE
    if _LOGIN_SHELL_PATH_CACHE is not None:
        return _LOGIN_SHELL_PATH_CACHE or None
    if os.name == "nt":
        _LOGIN_SHELL_PATH_CACHE = ""
        return None
    try:
        proc = subprocess.run(
            ["bash", "-lc", "echo $PATH"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        lines = (proc.stdout or "").strip().splitlines()
        _LOGIN_SHELL_PATH_CACHE = lines[0] if lines else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        _LOGIN_SHELL_PATH_CACHE = ""
    return _LOGIN_SHELL_PATH_CACHE or None


def which_cli(name: str) -> Optional[str]:
    """shutil.which on steroids — walks the curated install dirs +
    falls back to `bash -lc 'command -v <name>'` so nvm-installed
    binaries are findable from GUI-launched bridges. Cached per-binary
    for the process lifetime."""
    if name in _CLI_PATH_CACHE:
        return _CLI_PATH_CACHE[name] or None
    found = shutil.which(name)
    if not found and os.name == "nt":
        for suffix in (".cmd", ".exe"):
            found = shutil.which(name + suffix)
            if found:
                break
    if not found and os.name != "nt":
        for d in macos_linux_search_paths():
            candidate = os.path.join(d, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found = candidate
                break
    if not found and os.name != "nt":
        # Last-ditch login-shell probe. Slow on the first call (one
        # subprocess spawn), free on subsequent calls (cached).
        try:
            proc = subprocess.run(
                ["bash", "-lc", f"command -v {name} || true"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            lines = (proc.stdout or "").strip().splitlines()
            if lines and lines[0] and os.path.exists(lines[0]):
                found = lines[0]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
    _CLI_PATH_CACHE[name] = found or None
    return found or None


def enriched_path(found_bin: Optional[str] = None) -> str:
    """Build a PATH suitable for spawning a CLI's children. Layers:
    parent dir of sys.executable (so subprocess `python3` resolves to the
    same venv python the bridge is running — without this, claude's
    `bash python3 send_gateway.py` picks up system python on the VPS
    and ImportErrors on packages the bridge's venv has), parent dir of
    the resolved binary, curated search dirs, login-shell PATH, current
    os.environ PATH. De-duped, in priority order.

    The sys.executable prepend was added 2026-06-10 after Solara on the
    SunBiz VPS failed to send email — claude subprocess shelled to
    /usr/bin/python3, which had no `supabase` package, even though the
    bridge's venv at /srv/sunbiz/ceo-agent/.venv had it installed.
    """
    import sys
    parts: list[str] = []
    py_bin_dir = os.path.dirname(sys.executable)
    if py_bin_dir:
        parts.append(py_bin_dir)
    if found_bin:
        parts.append(os.path.dirname(found_bin))
    if os.name != "nt":
        parts.extend(macos_linux_search_paths())
        shell_path = login_shell_path()
        if shell_path:
            parts.extend(shell_path.split(os.pathsep))
    existing = os.environ.get("PATH", "")
    if existing:
        parts.extend(existing.split(os.pathsep))
    seen: set = set()
    ordered: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    return os.pathsep.join(ordered)


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
                first_name = Path(first).name
                if (
                    first.endswith(".cmd")
                    or first.endswith(".bat")
                    or first_name in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
                ):
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
                first_name = Path(first).name
                if (
                    first.endswith(".cmd")
                    or first.endswith(".bat")
                    or first_name in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
                ):
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
    "command_without_cmd_shim",
    "safe_run",
    "safe_popen",
    "safe_daemon_popen",
]
