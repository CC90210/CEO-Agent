---
name: python-daemon-automation
description: Build, deploy, and manage Python background daemons on Windows — includes 5-step redeploy protocol, watchdog patterns, zombie process detection, and kill switches
tags: [skill, automation, python, daemon, windows]
---

# Python Daemon Automation — Windows Background Process Management

> **Purpose:** Prevent zombie daemon incidents. A running Python process does NOT pick up source code changes. This skill encodes every lesson from a 7-day zombie incident where an old Skool automation kept sending unwanted DMs because the process was never properly killed and restarted after code changes.

## The Core Law

```
EDITING A .PY FILE DOES NOT AFFECT THE RUNNING PROCESS.
The process loaded the module into memory at startup.
Kill it. Clean bytecache. Restart. There is no other way.
```

---

## 1. Architecture Pattern for Python Daemons

Every daemon must be built with these five components from day one.

### 1a. Single-Instance Enforcement (File Lock)

```python
import msvcrt
import os

LOCK_FILE = "tmp/locks/daemon_name.lock"

def acquire_lock():
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    lock_fd = open(LOCK_FILE, "w")
    try:
        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd  # Caller must hold this reference — GC will release the lock
    except OSError:
        lock_fd.close()
        return None  # Another instance is running

# In main():
lock = acquire_lock()
if lock is None:
    print("Already running. Exiting.")
    sys.exit(0)
```

### 1b. Heartbeat File

Written every cycle. Tells the watchdog the process is alive and working.

```python
import json
import time

HEARTBEAT_FILE = "tmp/heartbeat/daemon_name.json"

def write_heartbeat(cycle: int) -> None:
    os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({
            "pid": os.getpid(),
            "timestamp": time.time(),
            "cycle": cycle,
            "status": "running"
        }, f)

def heartbeat_is_fresh(max_age_seconds: int = 300) -> bool:
    """Returns True if heartbeat was written within max_age_seconds."""
    try:
        with open(HEARTBEAT_FILE) as f:
            data = json.load(f)
        return (time.time() - data["timestamp"]) < max_age_seconds
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return False
```

### 1c. PID File with Start Time

```python
import psutil

PID_FILE = "tmp/pids/daemon_name.pid"

def write_pid_file() -> None:
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    pid = os.getpid()
    start_time = psutil.Process(pid).create_time()
    with open(PID_FILE, "w") as f:
        json.dump({"pid": pid, "start_time": start_time}, f)

def read_pid_file() -> dict | None:
    try:
        with open(PID_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def pid_is_stale(max_age_hours: int = 24) -> bool:
    """Returns True if the PID file process is too old or gone."""
    data = read_pid_file()
    if not data:
        return False
    try:
        proc = psutil.Process(data["pid"])
        age_hours = (time.time() - data["start_time"]) / 3600
        return age_hours > max_age_hours
    except psutil.NoSuchProcess:
        return False  # Process is already gone, not stale
```

### 1d. Log File per Daemon

```python
import logging
from logging.handlers import RotatingFileHandler
from datetime import date

LOG_FILE = f"tmp/logs/daemon_name_{date.today()}.log"

def setup_logging(name: str) -> logging.Logger:
    os.makedirs("tmp/logs", exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger
```

### 1e. Kill Switch Pattern

One constant per dangerous feature, at module level. Cannot be bypassed.

```python
# ============================================================
# KILL SWITCHES — Set True to disable feature immediately on restart
# ============================================================
DM_AUTOMATION_DISABLED = True   # Set False to re-enable DM sending
POST_AUTOMATION_DISABLED = False
EMAIL_AUTOMATION_DISABLED = False
# ============================================================

def send_dm(user_id: str, message: str) -> bool:
    if DM_AUTOMATION_DISABLED:
        log.info(f"DM DISABLED — would have sent to {user_id}: {message[:40]}...")
        return False
    # ... actual DM code below
```

Even if an old process is running (it shouldn't be after following this skill), the kill switch takes effect on restart. It is the last line of defense.

---

## 2. The 5-Step Daemon Redeploy Protocol

**Use this EVERY TIME you change any daemon source file.**

### Step 1: EDIT
Make your code changes to the `.py` file. Save it.

### Step 2: KILL
Find the running process — sort by start time, not command line. Zombie processes often have empty `CommandLine` on Windows.

```powershell
# Find all Python processes with start times
Get-Process python,pythonw -EA SilentlyContinue | Select Id, StartTime, Path | Sort StartTime

# If CommandLine is needed (WMI — slower but shows args)
Get-WmiObject Win32_Process -Filter "name='python.exe'" | `
    Select ProcessId, ParentProcessId, CommandLine, CreationDate | `
    Sort CreationDate
```

Kill it:
```powershell
# Standard kill
taskkill /PID <pid> /F

# If it survives taskkill (zombie) — nuclear WMI Terminate
(Get-WmiObject Win32_Process -Filter 'ProcessId=<pid>').Terminate()
```

### Step 3: CLEAN
Delete the bytecache for the changed module. Python can load old compiled `.pyc` files even after the source `.py` is updated if the timestamp comparison fails.

```bash
# From the script's directory
find . -name "*.pyc" -path "*/__pycache__/*" -delete

# Or target the specific module
rm scripts/__pycache__/skool_engine*.pyc 2>/dev/null
rm scripts/__pycache__/daemon_name*.pyc 2>/dev/null
```

### Step 4: VERIFY DEAD
Confirm the process is gone AND confirm log files stop updating. These are two separate checks — a PID being gone does not mean no other copy is running.

```bash
# Check 1: Process is gone
Get-Process python,pythonw -EA SilentlyContinue | Select Id, StartTime

# Check 2: Log file timestamps stop changing
# Run twice, 30 seconds apart — timestamps MUST match if process is dead
stat -c '%Y' tmp/logs/daemon_name_*.log
# wait 30 seconds
stat -c '%Y' tmp/logs/daemon_name_*.log
```

If the timestamp changed between checks: **there is still a running instance**. Go back to Step 2.

### Step 5: RESTART
Start the new process, watch the first cycle output, confirm behavior matches expectations.

```bash
# Start headless (no console window)
pythonw scripts/daemon_name.py &

# Or via startup script
python scripts/bravo_startup.pyw

# Watch logs for first cycle
tail -f tmp/logs/daemon_name_$(date +%Y-%m-%d).log
```

Verify the first log line confirms the new code version is running (log the git hash or version constant on startup).

---

## 3. Watchdog Pattern

The watchdog is a separate script run by Task Scheduler every 5 minutes. It is the process manager — it detects dead or stale daemons and restarts them.

### Watchdog Check Order (Order Matters)

```
1. Kill stale processes (>24h old) FIRST
2. Clean bytecache
3. Check file lock (is another instance already holding it?)
4. Check heartbeat file (is the process cycling normally?)
5. Check PID file (does the PID still exist?)
6. Restart if any check fails
```

Stale kills BEFORE lock checks. Otherwise a stale zombie holds the lock and the watchdog thinks the daemon is running.

### Watchdog Script Template

```python
"""
daemon_watchdog.py — Watchdog for daemon_name.py
Run via Task Scheduler every 5 minutes.
"""
import subprocess
import sys
import os
import time
import json
import logging
import psutil
from pathlib import Path

PYTHON_EXE = r"C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe"
DAEMON_SCRIPT = r"C:\Users\User\Business-Empire-Agent\scripts\daemon_name.py"
HEARTBEAT_FILE = r"C:\Users\User\Business-Empire-Agent\tmp\heartbeat\daemon_name.json"
PID_FILE = r"C:\Users\User\Business-Empire-Agent\tmp\pids\daemon_name.pid"
LOG_FILE = r"C:\Users\User\Business-Empire-Agent\tmp\logs\watchdog_daemon_name.log"
LOCK_FILE = r"C:\Users\User\Business-Empire-Agent\tmp\locks\daemon_name.lock"
MAX_AGE_HOURS = 24
HEARTBEAT_MAX_AGE_SECONDS = 300

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("watchdog")


def kill_stale_processes() -> int:
    """Kill any python processes running daemon_name older than MAX_AGE_HOURS. Returns count killed."""
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        try:
            if proc.info["name"] not in ("python.exe", "pythonw.exe"):
                continue
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "daemon_name" not in cmdline and "daemon_name" not in str(proc.exe()):
                continue
            age_hours = (time.time() - proc.info["create_time"]) / 3600
            if age_hours > MAX_AGE_HOURS:
                log.warning(f"Killing stale process PID={proc.pid} age={age_hours:.1f}h")
                try:
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


def clean_bytecache() -> None:
    script_dir = Path(DAEMON_SCRIPT).parent
    cache_dir = script_dir / "__pycache__"
    if cache_dir.exists():
        for pyc in cache_dir.glob("daemon_name*.pyc"):
            pyc.unlink()
            log.info(f"Cleaned bytecache: {pyc}")


def heartbeat_is_fresh() -> bool:
    try:
        with open(HEARTBEAT_FILE) as f:
            data = json.load(f)
        return (time.time() - data["timestamp"]) < HEARTBEAT_MAX_AGE_SECONDS
    except Exception:
        return False


def pid_is_alive() -> bool:
    try:
        with open(PID_FILE) as f:
            data = json.load(f)
        return psutil.pid_exists(data["pid"])
    except Exception:
        return False


def start_daemon() -> None:
    log.info(f"Starting daemon: {DAEMON_SCRIPT}")
    subprocess.Popen(
        [PYTHON_EXE, DAEMON_SCRIPT],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        close_fds=True
    )


def main() -> None:
    log.info("=== Watchdog check ===")

    # Step 1: Kill stale processes first
    killed = kill_stale_processes()
    if killed:
        log.info(f"Killed {killed} stale process(es). Sleeping 5s before continuing.")
        time.sleep(5)

    # Step 2: Clean bytecache
    clean_bytecache()

    # Step 3-5: Check health signals
    alive = heartbeat_is_fresh() and pid_is_alive()

    if alive:
        log.info("Daemon is healthy. No action needed.")
        return

    log.warning("Daemon appears dead (heartbeat stale or PID gone). Restarting.")
    start_daemon()
    log.info("Restart issued.")


if __name__ == "__main__":
    main()
```

### Task Scheduler Entry (Critical Settings)

```
Action: Start a program
Program/script: C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe
Add arguments: C:\Users\User\Business-Empire-Agent\scripts\daemon_watchdog.py
Start in: C:\Users\User\Business-Empire-Agent

Trigger: Every 5 minutes, indefinitely
Run whether user is logged on or not: YES
Run with highest privileges: YES
```

NEVER use bare `python` or `pythonw` in the Program/script field. Use the full path. Bare names cause error 0x80070002 (file not found) because Task Scheduler does not inherit PATH.

---

## 4. Windows Process Debugging Commands

### Finding Processes

```powershell
# All Python processes sorted by age (oldest first — zombies are usually oldest)
Get-Process python,pythonw -EA SilentlyContinue | Select Id, StartTime, Path | Sort StartTime

# WMI query — shows CommandLine (slower, but works when CommandLine is empty in Get-Process)
Get-WmiObject Win32_Process -Filter "name='python.exe'" | `
    Select ProcessId, ParentProcessId, CommandLine, CreationDate | `
    Sort CreationDate

# Check if a specific PID is still alive
Get-Process -Id <pid> -EA SilentlyContinue
```

### Killing Processes

```powershell
# Standard force kill
taskkill /PID <pid> /F

# Kill process tree (kills parent + all children)
taskkill /PID <pid> /T /F

# Nuclear option — WMI Terminate (works on zombies that survive taskkill)
(Get-WmiObject Win32_Process -Filter 'ProcessId=<pid>').Terminate()
```

### Verifying Death

```bash
# Check log file is no longer updating (run twice, 30s apart)
stat -c '%Y' tmp/logs/daemon_name_*.log
sleep 30
stat -c '%Y' tmp/logs/daemon_name_*.log
# If BOTH timestamps are identical: process is dead
# If second timestamp is newer: another instance is still running
```

### Checking File Lock Status

```python
# Quick lock test script — paste into python REPL
import msvcrt, os
fd = open("tmp/locks/daemon_name.lock", "r+")
try:
    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
    print("Lock is FREE — no daemon running")
    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
except OSError:
    print("Lock is HELD — daemon is running")
fd.close()
```

---

## 5. Kill Switch Reference Pattern

Place all kill switches together at the top of the daemon script, immediately after imports. One block, easy to find, impossible to miss.

```python
import os
import sys
# ... other imports ...

# ============================================================
# FEATURE KILL SWITCHES
# Edit this file and restart the daemon to apply.
# True = DISABLED, False = ENABLED (fail-safe defaults)
# ============================================================
DM_AUTOMATION_DISABLED = True
POST_AUTOMATION_DISABLED = False
OUTREACH_DISABLED = False
WEBHOOK_DISABLED = False
# ============================================================


def send_dm(recipient_id: str, message: str) -> bool:
    if DM_AUTOMATION_DISABLED:
        log.info(f"[KILL SWITCH] DM to {recipient_id} suppressed")
        return False
    # ... real implementation ...


def post_content(payload: dict) -> bool:
    if POST_AUTOMATION_DISABLED:
        log.info("[KILL SWITCH] Post suppressed")
        return False
    # ... real implementation ...
```

**Why this works even with a running zombie:** If you cannot kill the process, the kill switch will take effect on the NEXT restart. The code path returns early before any side effects. It is the last line of defense when the 5-step protocol fails.

---

## 6. Startup Architecture (`bravo_startup.pyw`)

The startup script is the single entry point for all daemons. It runs at Windows logon via Task Scheduler.

```python
"""
bravo_startup.pyw — Single entry point for all daemons.
.pyw extension = no console window.
"""
import subprocess
import os
import sys
import time
import json
import logging
import psutil

CREATE_NO_WINDOW = 0x08000000
PYTHON_EXE = r"C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe"
BASE_DIR = r"C:\Users\User\Business-Empire-Agent"
LOG_FILE = os.path.join(BASE_DIR, "tmp", "logs", "startup.log")

os.makedirs(os.path.join(BASE_DIR, "tmp", "logs"), exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("startup")

DAEMONS = [
    {
        "name": "skool_engine",
        "script": os.path.join(BASE_DIR, "scripts", "skool_engine.py"),
        "lock": os.path.join(BASE_DIR, "tmp", "locks", "skool_engine.lock"),
    },
    # Add more daemons here
]


def kill_orphans(daemon_name: str) -> None:
    """Kill any orphaned processes for this daemon before starting fresh."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] not in ("python.exe", "pythonw.exe"):
                continue
            cmdline = " ".join(proc.info["cmdline"] or [])
            if daemon_name in cmdline:
                log.warning(f"Killing orphan {daemon_name} PID={proc.pid}")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def lock_is_held(lock_path: str) -> bool:
    import msvcrt
    try:
        fd = open(lock_path, "r+")
        msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        fd.close()
        return False  # Lock is free
    except (OSError, FileNotFoundError):
        return True   # Lock is held


def start_daemon(daemon: dict) -> None:
    kill_orphans(daemon["name"])
    time.sleep(1)

    if lock_is_held(daemon["lock"]):
        log.info(f"{daemon['name']}: lock held, already running — skipping")
        return

    log.info(f"Starting {daemon['name']}")
    subprocess.Popen(
        [PYTHON_EXE, daemon["script"]],
        cwd=BASE_DIR,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True
    )


if __name__ == "__main__":
    log.info("=== bravo_startup.pyw ===")
    for daemon in DAEMONS:
        start_daemon(daemon)
    log.info("All daemons started.")
```

---

## 7. Anti-Patterns (Never Do These)

| Anti-Pattern | Why It Fails | Correct Approach |
|---|---|---|
| Edit `.py` and assume running process picks up changes | Python loads modules into memory at startup — edits are invisible to the live process | Kill → clean bytecache → restart every time |
| Use bare `python` or `pythonw` in Task Scheduler | Task Scheduler does not inherit PATH — causes error 0x80070002 | Always use full path to `python.exe` |
| Trust `taskkill` exit code alone | Taskkill can return 0 on a zombie that survives | Verify with `Get-Process` AND log timestamp check |
| Search for zombies by `CommandLine` only | Windows zombies often have empty `CommandLine` | Sort by `StartTime` instead; use WMI `CreationDate` |
| Skip bytecache cleanup after code change | `.pyc` files can be newer than the `.py` if clock skew or partial write occurred | Always delete `__pycache__/*.pyc` before restart |
| Assume a process is dead after killing it | The kill may have failed silently | Check log timestamps 30s apart — they must match |
| Multiple entry points for the same daemon | Creates race conditions and duplicate instances (e.g., `skool-cron.cmd` + `bravo_startup.pyw` + `skool_watchdog` all starting the same script) | One entry point, one watchdog, period |
| No kill switch on dangerous features | A zombie with DM automation runs for 7 days sending unwanted messages | Every side-effectful feature gets a `FEATURE_DISABLED` constant |
| Running watchdog without stale-process cleanup as first step | Stale zombie holds the file lock, watchdog sees lock held and thinks daemon is running, does nothing | Kill stale processes FIRST, then check health |

---

## 8. Checklist for New Python Daemon

Copy this when building any new daemon automation.

```
[ ] Single entry point — one script starts it, one watchdog manages it
[ ] msvcrt file lock for single-instance enforcement
[ ] Heartbeat file written every cycle: PID + timestamp + cycle count
[ ] PID file with process start time (for age-based stale detection)
[ ] Kill switch constant for each side-effectful feature (DM, email, post, webhook)
[ ] Full path to python.exe in all Task Scheduler entries — never bare `python`
[ ] Rotating log file named with daemon name and date
[ ] Watchdog script with stale process detection (>24h → kill)
[ ] Watchdog cleans bytecache before restart
[ ] Watchdog checks heartbeat freshness AND PID existence
[ ] `--dry-run` CLI flag for testing without side effects
[ ] `--status` subcommand printing heartbeat/lock/PID state
[ ] bravo_startup.pyw entry updated with new daemon
[ ] Version constant or git hash logged at startup (confirms new code is live)
[ ] 5-step redeploy protocol verified by running it once after initial deploy
```

## Obsidian Links
- [[scripts/bravo_startup]] | [[scripts/skool_engine]] | [[scripts/skool_watchdog]] | [[brain/CAPABILITIES]]
- [[skills/background-workers/SKILL]] | [[skills/hooks-automation/SKILL]]
- [[memory/MISTAKES]] | [[memory/SESSION_LOG]]
