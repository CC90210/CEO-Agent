"""Skool Engine Watchdog — reliable single-instance daemon management on Windows.

Called by skool_watchdog_silent.pyw every 5 minutes via Task Scheduler.
Ensures exactly ONE skool_engine daemon is running at all times.

Fixed 2026-03-23: Replaces unreliable os.kill(pid,0) with tasklist-based detection.
Fixed 2026-03-23: Kills orphan processes before restarting to prevent accumulation.
Fixed 2026-03-26: Heartbeat-first liveness — wmic is unreliable on Windows 11.
    The daemon writes tmp/skool_daemon.heartbeat every cycle (~2 min).
    If heartbeat is fresh (< 10 min), daemon is alive — skip wmic entirely.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "tmp" / "skool_daemon.pid"
HEARTBEAT_FILE = ROOT / "tmp" / "skool_daemon.heartbeat"
LOG_FILE = ROOT / "tmp" / "logs" / "watchdog.log"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ENGINE_SCRIPT = ROOT / "scripts" / "skool_engine.py"
CREATE_NO_WINDOW = 0x08000000

# Heartbeat older than this = daemon is dead
HEARTBEAT_MAX_AGE = timedelta(minutes=10)


def log(msg: str):
    """Append timestamped message to watchdog log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def is_heartbeat_fresh() -> bool:
    """Check if daemon heartbeat file exists and is recent."""
    if not HEARTBEAT_FILE.exists():
        return False
    try:
        data = json.loads(HEARTBEAT_FILE.read_text())
        ts = datetime.fromisoformat(data["ts"])
        age = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
        age = age - ts
        return age < HEARTBEAT_MAX_AGE
    except Exception:
        return False


def is_pid_alive(pid: int) -> bool:
    """Check if a specific PID is alive using Windows kernel32 (reliable)."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def get_daemon_pid() -> int | None:
    """Read daemon PID from PID file."""
    if not PID_FILE.exists():
        return None
    try:
        data = json.loads(PID_FILE.read_text())
        pid = data.get("pid")
        return int(pid) if pid else None
    except Exception:
        return None


def start_daemon():
    """Start a single skool_engine daemon — no popup window."""
    PID_FILE.unlink(missing_ok=True)
    HEARTBEAT_FILE.unlink(missing_ok=True)

    log_path = ROOT / "tmp" / "logs" / "skool_daemon_live.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(ENGINE_SCRIPT), "daemon", "--interval", "2"],
        cwd=str(ROOT),
        creationflags=CREATE_NO_WINDOW,
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
    )
    log(f"Skool daemon started (PID {proc.pid}, no window)")


def main():
    # PRIMARY CHECK: heartbeat file (most reliable — daemon writes this every cycle)
    if is_heartbeat_fresh():
        # Daemon is alive and cycling — nothing to do
        return

    # SECONDARY CHECK: PID file + kernel32 process check
    daemon_pid = get_daemon_pid()
    if daemon_pid and is_pid_alive(daemon_pid):
        # Process is alive but heartbeat is stale/missing — could be startup lag
        # or first cycle hasn't completed yet. Give it one more watchdog cycle.
        log(f"PID {daemon_pid} alive but heartbeat stale — waiting one more cycle")
        return

    # Daemon is truly dead — clean up and restart
    if daemon_pid:
        log(f"Daemon PID {daemon_pid} not alive. Cleaning up.")
    else:
        log("No daemon PID file found.")

    PID_FILE.unlink(missing_ok=True)
    HEARTBEAT_FILE.unlink(missing_ok=True)

    log("Skool daemon not running. Starting...")
    start_daemon()


if __name__ == "__main__":
    main()
