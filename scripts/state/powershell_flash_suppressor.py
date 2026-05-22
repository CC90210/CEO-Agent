#!/usr/bin/env python3
"""Hide throwaway PowerShell console windows from known noisy parent apps.

This does not disable ASUS Armoury, Wispr Flow, or any OASIS background job.
It only hides transient powershell.exe/pwsh.exe windows whose parent chain or
command line matches sources we have observed flashing on CC's workstation.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psutil

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib.subprocess_helpers import prefer_pythonw, safe_daemon_popen, safe_run  # noqa: E402

STATE_DIR = REPO_ROOT / "state"
PID_PATH = STATE_DIR / "powershell_flash_suppressor.pid"
LOG_PATH = STATE_DIR / "powershell_flash_suppressor.log"
TASK_NAME = "OASIS PowerShell Flash Suppressor"
STARTUP_LAUNCHER = (
    Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
    / "OASIS-PowerShell-Flash-Suppressor.vbs"
)

TARGET_PROCESS_NAMES = {"powershell.exe", "pwsh.exe"}
CONSOLE_HOST_PROCESS_NAMES = {"conhost.exe", "openconsole.exe"}
TARGET_PARENT_NAMES = {
    "asus_framework.exe",
    "wispr flow.exe",
}
TARGET_COMMAND_MARKERS = {
    "repair_chrome_audio.ps1",
}

SW_HIDE = 0
EVENT_OBJECT_SHOW = 0x8002
OBJID_WINDOW = 0
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
PM_REMOVE = 0x0001


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(event: str, **payload: object) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        row = {"ts": _utc(), "event": event, **payload}
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _is_alive(pid: int) -> bool:
    try:
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        return False


def _read_pid() -> int | None:
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_pid() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _process_name(proc: psutil.Process) -> str:
    try:
        return (proc.name() or "").lower()
    except Exception:
        return ""


def _cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline()).lower()
    except Exception:
        return ""


def _parent_names(proc: psutil.Process, max_depth: int = 6) -> list[str]:
    names: list[str] = []
    current = proc
    for _ in range(max_depth):
        try:
            parent = current.parent()
        except Exception:
            break
        if parent is None:
            break
        name = _process_name(parent)
        if name:
            names.append(name)
        current = parent
    return names


def _ancestors(proc: psutil.Process, max_depth: int = 6) -> list[psutil.Process]:
    ancestors: list[psutil.Process] = []
    current = proc
    for _ in range(max_depth):
        try:
            parent = current.parent()
        except Exception:
            break
        if parent is None:
            break
        ancestors.append(parent)
        current = parent
    return ancestors


def _target_reason(proc: psutil.Process) -> str | None:
    name = _process_name(proc)
    if name not in TARGET_PROCESS_NAMES and name not in CONSOLE_HOST_PROCESS_NAMES:
        return None

    cmdline = _cmdline(proc)
    for marker in TARGET_COMMAND_MARKERS:
        if marker in cmdline:
            return f"command:{marker}"

    ancestors = _ancestors(proc)
    parent_names = [_process_name(parent) for parent in ancestors]

    for parent in ancestors:
        parent_cmdline = _cmdline(parent)
        for marker in TARGET_COMMAND_MARKERS:
            if marker in parent_cmdline:
                return f"ancestor-command:{marker}"

    for parent in parent_names:
        if name in TARGET_PROCESS_NAMES and parent in TARGET_PARENT_NAMES:
            return f"parent:{parent}"

    if name in CONSOLE_HOST_PROCESS_NAMES:
        has_powershell_ancestor = any(parent in TARGET_PROCESS_NAMES for parent in parent_names)
        if has_powershell_ancestor:
            for parent in parent_names:
                if parent in TARGET_PARENT_NAMES:
                    return f"console-host-parent:{parent}"

    return None


def _visible_windows() -> Iterable[tuple[int, int]]:
    user32 = ctypes.windll.user32
    hwnds: list[tuple[int, int]] = []

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            hwnds.append((int(hwnd), int(pid.value)))
        return True

    user32.EnumWindows(enum_proc_type(enum_proc), 0)
    return hwnds


def _window_class(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(256)
    try:
        user32.GetClassNameW(hwnd, buf, 256)
        return (buf.value or "").strip()
    except Exception:
        return ""


def _hide_window_if_target(
    user32: object,
    hwnd: int,
    pid: int,
    seen: dict[tuple[int, int], float],
    protected: set[tuple[int, int]] | None = None,
    hide_new_console_hosts: bool = True,
) -> bool:
    protected = protected or set()
    now = time.monotonic()
    key = (hwnd, pid)
    if key in protected:
        return False
    try:
        proc = psutil.Process(pid)
    except Exception:
        return False
    reason = _target_reason(proc)
    if not reason and hide_new_console_hosts and _process_name(proc) in CONSOLE_HOST_PROCESS_NAMES:
        reason = "new-console-host"
    if not reason and hide_new_console_hosts and _process_name(proc) in TARGET_PROCESS_NAMES:
        reason = "new-powershell"
    if not reason and hide_new_console_hosts and _window_class(hwnd) == "ConsoleWindowClass":
        reason = "new-console-window"
    if not reason:
        return False
    user32.ShowWindow(hwnd, SW_HIDE)
    try:
        user32.ShowWindowAsync(hwnd, SW_HIDE)
    except Exception:
        pass
    if key not in seen:
        seen[key] = now
        _log(
            "hidden",
            pid=pid,
            process=_process_name(proc),
            reason=reason,
            parents=_parent_names(proc),
        )
    return True


def _hide_matching_windows(
    seen: dict[tuple[int, int], float],
    protected: set[tuple[int, int]] | None = None,
    hide_new_console_hosts: bool = True,
) -> int:
    user32 = ctypes.windll.user32
    hidden = 0
    now = time.monotonic()
    for key, ts in list(seen.items()):
        if now - ts > 30:
            seen.pop(key, None)

    for hwnd, pid in _visible_windows():
        if _hide_window_if_target(user32, hwnd, pid, seen, protected, hide_new_console_hosts):
            hidden += 1
    return hidden


def _install_show_hook(
    seen: dict[tuple[int, int], float],
    protected: set[tuple[int, int]],
    hide_new_console_hosts: bool,
) -> tuple[int, object] | tuple[None, None]:
    user32 = ctypes.windll.user32
    win_event_proc_type = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    def callback(_hook, event, hwnd, id_object, _id_child, _thread, _time_ms) -> None:
        if event != EVENT_OBJECT_SHOW or id_object != OBJID_WINDOW or not hwnd:
            return
        if not user32.IsWindowVisible(hwnd):
            return
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            _hide_window_if_target(
                user32,
                int(hwnd),
                int(pid.value),
                seen,
                protected=protected,
                hide_new_console_hosts=hide_new_console_hosts,
            )

    callback_ref = win_event_proc_type(callback)
    hook = user32.SetWinEventHook(
        EVENT_OBJECT_SHOW,
        EVENT_OBJECT_SHOW,
        0,
        callback_ref,
        0,
        0,
        WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
    )
    if not hook:
        return None, None
    return int(hook), callback_ref


def _pump_window_messages() -> None:
    user32 = ctypes.windll.user32
    msg = wintypes.MSG()
    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def run(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print(json.dumps({"ok": False, "error": "Windows only"}))
        return 1
    existing = _read_pid()
    if existing and existing != os.getpid() and _is_alive(existing):
        print(json.dumps({"ok": True, "already_running": True, "pid": existing}))
        return 0

    _write_pid()
    protected = set(_visible_windows())
    _log("started", pid=os.getpid(), poll_ms=args.poll_ms, protected_windows=len(protected))
    seen: dict[tuple[int, int], float] = {}
    hook, _callback_ref = _install_show_hook(
        seen,
        protected,
        hide_new_console_hosts=not args.targeted_only,
    )
    _log("show_hook", installed=bool(hook))
    sleep_s = max(0.01, args.poll_ms / 1000.0)
    try:
        while True:
            _pump_window_messages()
            _hide_matching_windows(
                seen,
                protected=protected,
                hide_new_console_hosts=not args.targeted_only,
            )
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        _log("stopped", pid=os.getpid(), reason="keyboard_interrupt")
        return 0
    finally:
        if hook:
            try:
                ctypes.windll.user32.UnhookWinEvent(hook)
            except Exception:
                pass


def start(_args: argparse.Namespace) -> int:
    existing = _read_pid()
    if existing and _is_alive(existing):
        print(json.dumps({"ok": True, "already_running": True, "pid": existing}))
        return 0

    script = Path(__file__).resolve()
    pythonw = prefer_pythonw(sys.executable)
    proc = safe_daemon_popen(
        [str(pythonw), str(script), "run", "--poll-ms", "5"],
        stdin=None,
        stdout=None,
        stderr=None,
        close_fds=True,
        cwd=str(REPO_ROOT),
    )
    time.sleep(0.5)
    pid = _read_pid() or proc.pid
    print(json.dumps({"ok": True, "pid": pid, "python": str(pythonw)}))
    return 0


def install(args: argparse.Namespace) -> int:
    script = Path(__file__).resolve()
    pythonw = prefer_pythonw(sys.executable)
    task_run = f'"{pythonw}" "{script}" run --poll-ms 5'
    create = safe_run(
        [
            "schtasks",
            "/Create",
            "/SC",
            "ONLOGON",
            "/TN",
            TASK_NAME,
            "/TR",
            task_run,
            "/F",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if create.returncode != 0:
        launcher = _install_startup_launcher(pythonw, script)
        if args.start:
            start(args)
        print(
            json.dumps(
                {
                    "ok": True,
                    "task": None,
                    "startup_launcher": str(launcher),
                    "note": "Scheduled task unavailable; installed Startup launcher instead.",
                    "schtasks_error": create.stderr.strip() or create.stdout.strip(),
                }
            )
        )
        return 0

    # `schtasks /Create` has no Hidden switch. Set it through the Task
    # Scheduler cmdlets using a hidden PowerShell child.
    ps = (
        f"$t = Get-ScheduledTask -TaskName {json.dumps(TASK_NAME)}; "
        "$t.Settings.Hidden = $true; "
        "Set-ScheduledTask -InputObject $t | Out-Null"
    )
    safe_run(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if args.start:
        start(args)
    print(json.dumps({"ok": True, "task": TASK_NAME, "python": str(pythonw)}))
    return 0


def _install_startup_launcher(pythonw: Path, script: Path) -> Path:
    STARTUP_LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
    command = f'"{pythonw}" "{script}" run --poll-ms 5'
    vbs_command = command.replace('"', '""')
    STARTUP_LAUNCHER.write_text(
        "' Auto-generated by Business-Empire-Agent.\r\n"
        "' Runs the PowerShell flash suppressor without a console window.\r\n"
        "Set WshShell = CreateObject(\"WScript.Shell\")\r\n"
        f'WshShell.Run "{vbs_command}", 0, False\r\n',
        encoding="utf-8",
    )
    _log("startup_launcher_installed", path=str(STARTUP_LAUNCHER))
    return STARTUP_LAUNCHER


def status(_args: argparse.Namespace) -> int:
    pid = _read_pid()
    running = bool(pid and _is_alive(pid))
    task = safe_run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "running": running,
                "pid": pid if running else None,
                "task_installed": task.returncode == 0,
                "startup_launcher": str(STARTUP_LAUNCHER) if STARTUP_LAUNCHER.exists() else None,
                "log": str(LOG_PATH),
            }
        )
    )
    return 0


def once(_args: argparse.Namespace) -> int:
    seen: dict[tuple[int, int], float] = {}
    hidden = _hide_matching_windows(seen, protected=set(), hide_new_console_hosts=True)
    print(json.dumps({"ok": True, "hidden": hidden}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hide known throwaway PowerShell flash windows")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--poll-ms", type=int, default=5)
    p_run.add_argument(
        "--targeted-only",
        action="store_true",
        help="Only hide known ASUS/Wispr/OASIS PowerShell windows, not all new Console Host windows.",
    )
    p_run.set_defaults(func=run)
    sub.add_parser("start").set_defaults(func=start)
    p_install = sub.add_parser("install")
    p_install.add_argument("--start", action="store_true")
    p_install.set_defaults(func=install)
    sub.add_parser("status").set_defaults(func=status)
    sub.add_parser("once").set_defaults(func=once)
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
