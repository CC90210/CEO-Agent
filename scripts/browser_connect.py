#!/usr/bin/env python3
"""Connect Browser Harness to Chrome with the OASIS business profile.

Handles the full lifecycle:
1. Checks if Chrome is running with remote debugging
2. If not, restarts Chrome with --remote-debugging-port=9222 and OASIS profile
3. Waits for the debug port to come alive
4. Gets the WebSocket URL
5. Attaches the Browser Harness daemon

Usage:
    python scripts/browser_connect.py          # connect (interactive)
    python scripts/browser_connect.py --check  # just check status
    python scripts/browser_connect.py --json   # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _subprocess_helpers import safe_popen, safe_run
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CDP_PORT = 9222
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
# OASIS AI Solutions profile — has all business passwords/cookies
CHROME_PROFILE = "Profile 1"


def _port_open(port: int = CDP_PORT) -> bool:
    """Check if the CDP port is listening."""
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=2)
        sock.close()
        return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def _get_ws_url(port: int = CDP_PORT) -> str | None:
    """Get the WebSocket debugger URL from Chrome's /json/version endpoint."""
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("webSocketDebuggerUrl")
    except Exception:
        return None


def _get_browser_info(port: int = CDP_PORT) -> dict[str, Any] | None:
    """Get full browser info from Chrome's debug endpoint."""
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _chrome_running() -> bool:
    """Check if any Chrome process is running."""
    if os.name == "nt":
        result = safe_run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True, text=True, timeout=10
        )
        return "chrome.exe" in result.stdout
    return False


def _kill_chrome() -> None:
    """Kill all Chrome processes."""
    if os.name == "nt":
        safe_run(
            ["taskkill", "/F", "/IM", "chrome.exe"],
            capture_output=True, timeout=15
        )
    time.sleep(3)


def _launch_chrome_debug() -> None:
    """Launch Chrome with remote debugging on the OASIS profile."""
    args = [
        CHROME_EXE,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        "--remote-debugging-address=127.0.0.1",
        f'--profile-directory={CHROME_PROFILE}',
        f"--user-data-dir={CHROME_USER_DATA}",
        "--restore-last-session",
    ]
    safe_popen(args, close_fds=True)


def _attach_harness(ws_url: str) -> dict[str, Any]:
    """Attach the Browser Harness daemon to the Chrome WebSocket."""
    harness = shutil.which("browser-harness")
    if not harness:
        return {"ok": False, "error": "browser-harness not found in PATH"}

    env = os.environ.copy()
    env["BU_CDP_WS"] = ws_url

    if os.name == "nt":
        quoted = str(harness).replace("'", "''")
        command = "& '" + quoted + "' --setup"
        result = safe_run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, timeout=30, env=env
        )
    else:
        result = subprocess.run(
            [str(harness), "--setup"],
            capture_output=True, text=True, timeout=30, env=env
        , creationflags=WINDOWLESS_FLAGS)

    output = (result.stdout + "\n" + result.stderr).strip()
    return {
        "ok": "daemon is up" in output.lower(),
        "output": output,
        "returncode": result.returncode,
    }


def check_status() -> dict[str, Any]:
    """Return the current connection status without changing anything."""
    port_open = _port_open()
    ws_url = _get_ws_url() if port_open else None
    browser_info = _get_browser_info() if port_open else None
    chrome_running = _chrome_running()

    return {
        "chrome_running": chrome_running,
        "debug_port_open": port_open,
        "ws_url": ws_url,
        "browser": browser_info.get("Browser") if browser_info else None,
        "profile": CHROME_PROFILE,
        "profile_email": "oasisaisolutions@gmail.com",
        "port": CDP_PORT,
    }


def connect(interactive: bool = True) -> dict[str, Any]:
    """Full connection sequence."""
    def _print(msg: str) -> None:
        if interactive:
            print(msg)

    # Step 1: Check if debug port is already open
    if _port_open():
        _print(f"Chrome debug port {CDP_PORT} already active.")
        ws_url = _get_ws_url()
        if ws_url:
            _print(f"WebSocket: {ws_url}")
            _print("Attaching Browser Harness...")
            attach = _attach_harness(ws_url)
            if attach["ok"]:
                _print("Browser Harness daemon is up.")
            else:
                _print(f"Attach failed: {attach.get('output', '')[:200]}")
            return {"ok": attach["ok"], "ws_url": ws_url, "attach": attach}
        return {"ok": False, "error": "Port open but no WebSocket URL"}

    # Step 2: Chrome is running without debug — need to restart
    if _chrome_running():
        _print("Chrome is running but without remote debugging.")
        _print("Restarting Chrome with debug port and OASIS profile...")
        _kill_chrome()
        # Confirm it's dead
        for _ in range(5):
            if not _chrome_running():
                break
            time.sleep(1)

    # Step 3: Launch Chrome with debugging
    _print(f"Launching Chrome on port {CDP_PORT} with {CHROME_PROFILE}...")
    _launch_chrome_debug()

    # Step 4: Wait for port
    _print("Waiting for Chrome debug port...")
    for i in range(15):
        if _port_open():
            break
        time.sleep(1)
    else:
        return {"ok": False, "error": f"Port {CDP_PORT} did not open after 15s"}

    time.sleep(2)  # Let Chrome fully initialize

    # Step 5: Get WebSocket URL
    ws_url = _get_ws_url()
    if not ws_url:
        return {"ok": False, "error": "Chrome is listening but no WebSocket URL available"}

    _print(f"WebSocket: {ws_url}")

    # Step 6: Attach harness
    _print("Attaching Browser Harness daemon...")
    attach = _attach_harness(ws_url)
    if attach["ok"]:
        _print("Browser Harness daemon is up. All wires connected.")
    else:
        _print(f"Attach issue: {attach.get('output', '')[:200]}")

    return {"ok": attach["ok"], "ws_url": ws_url, "attach": attach}


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect Browser Harness to Chrome (OASIS profile)")
    parser.add_argument("--check", action="store_true", help="Just check status, don't connect")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    if args.check:
        status = check_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"Chrome running:    {'YES' if status['chrome_running'] else 'NO'}")
            print(f"Debug port {CDP_PORT}:   {'OPEN' if status['debug_port_open'] else 'CLOSED'}")
            print(f"WebSocket URL:     {status['ws_url'] or 'N/A'}")
            print(f"Browser:           {status['browser'] or 'N/A'}")
            print(f"Profile:           {status['profile']} ({status['profile_email']})")
        return 0 if status["debug_port_open"] else 1

    result = connect(interactive=not args.json)
    if args.json:
        print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
