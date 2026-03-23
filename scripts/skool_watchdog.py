"""Skool Engine Watchdog — reliable single-instance daemon management on Windows.

Called by skool-watchdog.cmd every 5 minutes via Task Scheduler.
Ensures exactly ONE skool_engine daemon is running at all times.

Fixed 2026-03-23: Replaces unreliable os.kill(pid,0) with tasklist-based detection.
Fixed 2026-03-23: Kills orphan processes before restarting to prevent accumulation.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "tmp" / "skool_daemon.pid"
LOG_FILE = ROOT / "tmp" / "logs" / "watchdog.log"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ENGINE_SCRIPT = ROOT / "scripts" / "skool_engine.py"


def log(msg: str):
    """Append timestamped message to watchdog log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def get_python_processes() -> list[dict]:
    """Get all running python.exe processes with their PIDs and command lines."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get",
             "ProcessId,CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True, timeout=10
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


def is_daemon_alive() -> bool:
    """Check if the daemon PID from the PID file is actually running."""
    if not PID_FILE.exists():
        return False
    try:
        data = json.loads(PID_FILE.read_text())
        target_pid = data["pid"]
    except (json.JSONDecodeError, KeyError, OSError):
        return False

    processes = get_python_processes()
    return any(p["pid"] == target_pid for p in processes)


def count_skool_engines() -> list[int]:
    """Return PIDs of all running skool_engine processes."""
    processes = get_python_processes()
    return [p["pid"] for p in processes if "skool_engine" in p.get("cmd", "")]


def kill_orphans(exclude_pid: int | None = None):
    """Kill all skool_engine processes except the given PID."""
    engine_pids = count_skool_engines()
    killed = 0
    for pid in engine_pids:
        if pid == exclude_pid:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
            killed += 1
        except Exception:
            pass
    if killed:
        log(f"Killed {killed} orphan skool_engine process(es)")
    return killed


def start_daemon():
    """Start a single skool_engine daemon — no popup window."""
    PID_FILE.unlink(missing_ok=True)

    # CREATE_NO_WINDOW (0x08000000) prevents any terminal window from appearing
    CREATE_NO_WINDOW = 0x08000000
    log_path = ROOT / "tmp" / "logs" / "skool_daemon_live.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(ENGINE_SCRIPT), "daemon", "--interval", "2"],
        cwd=str(ROOT),
        creationflags=CREATE_NO_WINDOW,
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
    )
    # Do NOT write PID file here — skool_engine.py writes its own PID file.
    # Writing it here causes the daemon to see a stale PID and exit immediately.
    log(f"Skool daemon started (PID {proc.pid}, no window)")


def main():
    engine_pids = count_skool_engines()
    engine_count = len(engine_pids)

    if engine_count > 1:
        # Multiple engines running — this is the accumulation bug. Keep newest, kill rest.
        log(f"ALERT: {engine_count} skool_engine processes running! Consolidating to 1.")
        # Keep the one from PID file if it's valid, otherwise keep the highest PID (newest)
        keep_pid = None
        if PID_FILE.exists():
            try:
                keep_pid = json.loads(PID_FILE.read_text())["pid"]
                if keep_pid not in engine_pids:
                    keep_pid = None
            except Exception:
                pass
        if keep_pid is None:
            keep_pid = max(engine_pids)
        kill_orphans(exclude_pid=keep_pid)
        log(f"Consolidated to PID {keep_pid}")
        return

    if engine_count == 1:
        # Exactly one engine running — healthy state
        return

    # engine_count == 0: No engine running
    if is_daemon_alive():
        # PID file says alive but no skool_engine found — stale PID file
        log("Stale PID file detected (process not found). Cleaning up.")
        PID_FILE.unlink(missing_ok=True)

    log("Skool daemon not running. Starting...")
    kill_orphans()  # Clean any lingering processes
    start_daemon()


if __name__ == "__main__":
    main()
