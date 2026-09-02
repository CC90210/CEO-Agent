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


# ─────────────────────────────────────────────────────────────────────
# Enriched PATH discovery for GUI-launched bridges (macOS / Linux).
# Electron + launchd inherit a slim LaunchServices PATH that misses
# Homebrew, npm-global, Bun, Deno, nvm. Mirrored in bravo_cli/
# _subprocess_helpers.py — keep both copies in sync.
# ─────────────────────────────────────────────────────────────────────

_LOGIN_SHELL_PATH_CACHE: Optional[str] = None
_CLI_PATH_CACHE: dict = {}


def macos_linux_search_paths() -> list[str]:
    """Common install directories an Electron/launchd-spawned process
    misses. Apple Silicon Homebrew is /opt/homebrew/bin; Intel is
    /usr/local/bin; npm global is ~/.npm-global/bin; nvm bin lives
    under ~/.nvm/versions/node/<v>/bin but we resolve that via the
    login-shell probe rather than enumerating versions here."""
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
    """Spawn `bash -lc 'echo $PATH'` once and cache. Login shell sources
    the user's profile so PATH matches Terminal — including nvm's
    versioned bin. 1.5s timeout protects against a wedged profile."""
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
    """shutil.which on steroids — curated install dirs + bash -lc
    fallback so nvm-installed binaries are findable from GUI-launched
    bridges. Cached per-binary for the process lifetime."""
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
    """PATH suitable for subprocess.run(env=...) when the parent was
    spawned by GUI/launchd. Layered, de-duped: resolved binary's parent
    dir, curated search dirs, login-shell PATH, current os.environ."""
    parts: list[str] = []
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


def _default_stdin_devnull(kw: dict) -> dict:
    """Give the child a valid stdin, because it will not inherit one.

    WHY (2026-09-02): daemons on this box run under pythonw.exe, which has NO
    CONSOLE. subprocess redirects stdout and stderr when asked and leaves stdin
    INHERITED, so every child of a windowless parent inherited a console handle
    that does not exist and intermittently died at interpreter startup with
    exit 3221225480 — 0xC0000008 STATUS_INVALID_HANDLE, roughly 1 run in 100,
    23 dumps between 2026-08-15 and 09-02, with both output streams empty every
    time. It was read as an access violation (0xC0000005) for two and a half
    weeks and chased in the wrong place.

    It belongs HERE and not in any one caller. 37 files spawn through these
    helpers; fixing the four sites in scheduler.py fixed the four sites in
    scheduler.py. The fault is a property of "spawned by a windowless parent",
    which is what this module is for.

    Never overrides an explicit stdin, and never sets one alongside `input=` —
    subprocess raises ValueError if both are given, and self_audit.py:447 does
    pass input=.
    """
    if "stdin" in kw or "input" in kw:
        return kw
    kw = dict(kw)
    kw["stdin"] = subprocess.DEVNULL
    return kw


def safe_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Drop-in replacement for subprocess.run that hides the console on
    Windows by default. Any caller-supplied creationflags are preserved
    (ORed with WINDOWLESS_FLAGS). Auto-applies windowless STARTUPINFO
    on shell=True or .cmd/.bat shim spawns. Pass-through everywhere else."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, WINDOWLESS_FLAGS)
        kwargs = _auto_startupinfo(kwargs, cmd)
        kwargs = _default_stdin_devnull(kwargs)
    return subprocess.run(cmd, **kwargs)


def safe_popen(cmd: Any, **kwargs: Any) -> subprocess.Popen:
    """Drop-in replacement for subprocess.Popen that hides the console on
    Windows by default. Same auto-detection as safe_run."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, WINDOWLESS_FLAGS)
        kwargs = _auto_startupinfo(kwargs, cmd)
        kwargs = _default_stdin_devnull(kwargs)
    return subprocess.Popen(cmd, **kwargs)


def safe_daemon_popen(cmd: Any, **kwargs: Any) -> subprocess.Popen:
    """Popen for long-lived daemons that must outlive the parent. Adds
    DETACHED_PROCESS on top of CREATE_NO_WINDOW so the child has no
    parent-process linkage and won't be SIGINT'd if the parent dies."""
    if os.name == "nt":
        kwargs = _merge_creationflags(kwargs, DETACHED_FLAGS)
        # A detached daemon needs this MORE than a short-lived child, not less:
        # it has no parent to inherit a console from at all, and it lives for
        # days. See _default_stdin_devnull.
        kwargs = _default_stdin_devnull(kwargs)
    return subprocess.Popen(cmd, **kwargs)


def pid_is_gone(pid: int) -> bool:
    """True ONLY when this pid provably no longer exists.

    For stale-lock recovery. Two O_EXCL locks in this repo record their
    holder's pid and then never ask about it, falling back to an age fence:
    instagram_dm_poller's poll lock (15 min) and fleet_watchdog's supervision
    lock (10 min). Both therefore turn any hard kill into minutes of dead time
    — the poller was found idling on a lock whose holder had been gone the
    whole while, logging "another poll holds the lock" every 20s, and the
    watchdog's equivalent stops supervising the entire fleet for two passes.

    Fails CLOSED on every uncertainty — a non-positive pid, our own pid, or an
    OS that will not answer all return False, which leaves the caller's age
    fence in charge. Guessing "gone" wrongly is how two holders run at once,
    and for the poller that means one prospect answered twice. "I cannot tell"
    is not "it is dead".

    Callers must keep their age fence: a recycled pid looks alive, and only
    elapsed time catches that.
    """
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            import ctypes  # noqa: PLC0415

            # PROCESS_QUERY_LIMITED_INFORMATION. A NULL handle with
            # ERROR_INVALID_PARAMETER (87) is the OS saying "no such pid";
            # any other failure means we may not ask, which is not evidence.
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return ctypes.windll.kernel32.GetLastError() == 87
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        os.kill(pid, 0)  # POSIX: raises ProcessLookupError when absent
        return False
    except ProcessLookupError:
        return True
    except Exception:  # noqa: BLE001 — an unanswerable probe is not a death
        return False


__all__ = [
    "WINDOWLESS_FLAGS",
    "DETACHED_FLAGS",
    "pid_is_gone",
    "windowless_startupinfo",
    "prefer_pythonw",
    "command_without_cmd_shim",
    "safe_run",
    "safe_popen",
    "safe_daemon_popen",
    "which_cli",
    "enriched_path",
    "macos_linux_search_paths",
    "login_shell_path",
]
