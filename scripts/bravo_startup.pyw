"""Bravo Startup — Single entry point for all background daemons.

Runs at Windows logon via Task Scheduler. The .pyw extension means
Python runs this with pythonw.exe (no console window at all).

Responsibilities:
  1. Start scheduler.py (cron job engine) — single instance, headless
  2. Start skool_engine.py (Skool community daemon) — single instance, headless
  3. Prevent duplicates using tasklist-based detection
  4. Log everything to tmp/logs/startup.log

CC turns off his computer at night. This script auto-starts everything
when he logs back in.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "tmp" / "logs" / "startup.log"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SYSTEM_PYTHON = Path(r"C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe")
CREATE_NO_WINDOW = 0x08000000


def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def get_python_processes() -> list[dict]:
    """Get all running python.exe processes with PIDs and command lines."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get",
             "ProcessId,CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        processes = []
        for line in result.stdout.strip().splitlines():
            if not line.strip() or line.startswith("Node"):
                continue
            parts = line.split(",", 2)
            if len(parts) >= 3:
                cmd = parts[1]
                pid = parts[2].strip()
                if pid.isdigit():
                    processes.append({"pid": int(pid), "cmd": cmd})
        return processes
    except Exception:
        return []


def count_processes(keyword: str) -> list[int]:
    """Return PIDs of Python processes whose command line contains keyword."""
    return [p["pid"] for p in get_python_processes() if keyword in p.get("cmd", "")]


def kill_extras(keyword: str, keep_count: int = 1):
    """Kill duplicate processes, keeping only keep_count (newest by PID)."""
    pids = count_processes(keyword)
    if len(pids) <= keep_count:
        return
    pids.sort()
    to_kill = pids[:-keep_count]
    for pid in to_kill:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5,
                           creationflags=CREATE_NO_WINDOW)
            log(f"  Killed duplicate {keyword} (PID {pid})")
        except Exception:
            pass


def start_daemon(script: str, python: Path = None, args: list = None,
                 log_name: str = None):
    """Start a Python script headless with CREATE_NO_WINDOW."""
    if python is None:
        python = VENV_PYTHON
    script_path = ROOT / "scripts" / script
    if not script_path.exists():
        log(f"  SKIP: {script} not found")
        return None
    if not python.exists():
        log(f"  SKIP: Python not found at {python}")
        return None

    cmd = [str(python), str(script_path)] + (args or [])
    log_path = ROOT / "tmp" / "logs" / (log_name or f"{script_path.stem}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        creationflags=CREATE_NO_WINDOW,
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    log(f"  Started {script} (PID {proc.pid}) -> {log_path.name}")
    return proc.pid


def main():
    log("=" * 50)
    log("BRAVO STARTUP — initializing background daemons")
    log("=" * 50)

    time.sleep(5)

    # 1. Scheduler (cron job engine)
    scheduler_pids = count_processes("scheduler.py")
    if len(scheduler_pids) > 1:
        log(f"Scheduler: {len(scheduler_pids)} instances — consolidating")
        kill_extras("scheduler.py", keep_count=1)
    elif len(scheduler_pids) == 1:
        log(f"Scheduler: already running (PID {scheduler_pids[0]})")
    else:
        log("Scheduler: not running — starting")
        python = VENV_PYTHON if VENV_PYTHON.exists() else SYSTEM_PYTHON
        start_daemon("scheduler.py", python=python, log_name="scheduler.log")

    # 2. Skool Engine V2 — post replies ONLY (DMs disabled 2026-04-02)
    # CC handles all DMs manually. Only community post replies are automated.
    # The daemon uses an exclusive file lock (msvcrt.locking) to prevent duplicates.
    # Check the lock FIRST — if held, daemon is alive. Don't start another.
    lock_file = ROOT / "tmp" / "skool_daemon.lock"
    lock_held = False
    if lock_file.exists():
        try:
            import msvcrt as _msvcrt
            fh = open(lock_file, "r+")
            try:
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_NBLCK, 1)
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)
                fh.close()
            except (OSError, IOError):
                fh.close()
                lock_held = True
        except Exception:
            pass

    if lock_held:
        log("Skool Engine V2: lock held — daemon is alive")
    else:
        # Lock not held — check if any zombie processes exist and kill them
        engine_pids = count_processes("skool_engine")
        if engine_pids:
            log(f"Skool Engine: {len(engine_pids)} orphan(s) found — killing all before fresh start")
            for pid in engine_pids:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=5,
                                   creationflags=CREATE_NO_WINDOW)
                except Exception:
                    pass
            time.sleep(2)

        # Clean up stale state files
        for f in [ROOT / "tmp" / "skool_daemon.pid",
                  ROOT / "tmp" / "skool_daemon.heartbeat",
                  lock_file]:
            f.unlink(missing_ok=True) if f.exists() else None

        log("Skool Engine V2: starting fresh (exclusive lock)")
        python = VENV_PYTHON if VENV_PYTHON.exists() else SYSTEM_PYTHON
        start_daemon("skool_engine.py", python=python,
                     args=["daemon", "--interval", "5"],
                     log_name="skool_engine.log")

    log("Startup complete.")
    log("")


if __name__ == "__main__":
    main()