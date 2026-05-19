#!/usr/bin/env python3
"""
gateway_admin.py — CLI admin tool for the multi-platform messaging gateway.

Subcommands:
  start           Start the gateway (via PM2 if available, else direct spawn)
  stop            Stop the gateway gracefully via HTTP control port
  status          Show gateway health (reads health.json + HTTP control port)
  send            Send a message via a specific platform adapter
  test-connection Test HTTP control server reachability
  list-adapters   List all configured adapters and their active status

All subcommands support --json for machine-readable output.

Usage examples:
  python scripts/gateway_admin.py status
  python scripts/gateway_admin.py list-adapters --json
  python scripts/gateway_admin.py send --platform telegram --to 123456789 --message "hello"
  python scripts/gateway_admin.py start
  python scripts/gateway_admin.py stop
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# ---- CONFIG ----
REPO_ROOT = Path(__file__).parent.parent.resolve()
GATEWAY_ENTRY = REPO_ROOT / "gateway" / "index.js"
HEALTH_FILE = REPO_ROOT / "gateway" / "health.json"
CONTROL_PORT = int(os.environ.get("GATEWAY_CONTROL_PORT", "7773"))
CONTROL_BASE = f"http://127.0.0.1:{CONTROL_PORT}"
PM2_PROCESS_NAME = "bravo-gateway"
NODE_EXE = "node"


def _http_get(path: str, timeout: int = 5) -> dict:
    """GET request to the gateway control server. Returns parsed JSON dict."""
    url = f"{CONTROL_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _http_post(path: str, body: dict, timeout: int = 10) -> dict:
    """POST request to the gateway control server. Returns parsed JSON dict."""
    url = f"{CONTROL_BASE}{path}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _pm2_available() -> bool:
    """Check if PM2 is on PATH."""
    try:
        result = subprocess.run(
            ["pm2", "--version"], capture_output=True, timeout=5,
         creationflags=WINDOWLESS_FLAGS)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _read_health_file() -> dict:
    """Read gateway/health.json if it exists."""
    try:
        with open(HEALTH_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        return {"error": str(e)}


def _print_or_json(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return
    # Human-readable fallback
    if not data.get("ok", True):
        print(f"ERROR: {data.get('error', 'unknown error')}")
        return
    for key, value in data.items():
        if key == "ok":
            continue
        if isinstance(value, (list, dict)):
            print(f"{key}:")
            print(json.dumps(value, indent=2))
        else:
            print(f"{key}: {value}")


# ---- SUBCOMMANDS ----

def cmd_start(args) -> dict:
    """Start the gateway process."""
    if not GATEWAY_ENTRY.exists():
        return {"ok": False, "error": f"Gateway entry not found: {GATEWAY_ENTRY}"}

    # Check if already running
    health = _http_get("/status", timeout=2)
    if health.get("ok"):
        pid = health.get("gateway", {}).get("pid", "?")
        return {"ok": True, "status": "already_running", "pid": pid}

    if args.pm2 or _pm2_available():
        # Start via PM2
        result = subprocess.run(
            ["pm2", "start", str(GATEWAY_ENTRY), "--name", PM2_PROCESS_NAME,
             "--no-autorestart" if getattr(args, "no_autorestart", False) else "--"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
         creationflags=WINDOWLESS_FLAGS)
        # Strip --no-autorestart placeholder arg
        if result.returncode == 0:
            return {"ok": True, "status": "started_pm2", "process": PM2_PROCESS_NAME}
        return {"ok": False, "error": result.stderr.strip() or "pm2 start failed"}
    else:
        # Direct spawn — detached, non-blocking
        log_file = REPO_ROOT / "gateway" / "gateway.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as lf:
            proc = subprocess.Popen(
                [NODE_EXE, str(GATEWAY_ENTRY)],
                cwd=str(REPO_ROOT),
                stdout=lf, stderr=lf,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
                close_fds=True,
            )
        # Wait up to 5s for the control server to come up
        for _ in range(10):
            time.sleep(0.5)
            health = _http_get("/status", timeout=2)
            if health.get("ok"):
                return {"ok": True, "status": "started_direct", "pid": proc.pid,
                        "log": str(log_file)}
        return {"ok": True, "status": "started_direct", "pid": proc.pid,
                "warning": "Control server not yet responding — check gateway.log"}


def cmd_stop(args) -> dict:
    """Stop the gateway via HTTP control port."""
    result = _http_post("/stop", {})
    if result.get("ok"):
        return {"ok": True, "status": "stop_requested"}
    # Try PM2 as fallback
    if _pm2_available():
        r = subprocess.run(
            ["pm2", "stop", PM2_PROCESS_NAME],
            capture_output=True, text=True, timeout=10,
         creationflags=WINDOWLESS_FLAGS)
        if r.returncode == 0:
            return {"ok": True, "status": "stopped_pm2"}
    return {"ok": False, "error": result.get("error", "Could not reach control server")}


def cmd_status(args) -> dict:
    """Show gateway health from HTTP + health.json."""
    live = _http_get("/status", timeout=5)
    health_file = _read_health_file()
    running = live.get("ok", False)

    # Freshness check on health file
    health_age_s = None
    if health_file.get("ts"):
        try:
            ts = datetime.fromisoformat(health_file["ts"].replace("Z", "+00:00"))
            health_age_s = (datetime.now().astimezone() - ts).total_seconds()
        except Exception:
            pass

    return {
        "ok": True,
        "running": running,
        "control_port": CONTROL_PORT,
        "live_data": live if running else None,
        "health_file": health_file,
        "health_file_age_s": round(health_age_s, 1) if health_age_s is not None else None,
        "health_file_stale": health_age_s is not None and health_age_s > 60,
    }


def cmd_send(args) -> dict:
    """Send a message via a platform adapter."""
    if not args.platform:
        return {"ok": False, "error": "--platform required"}
    if not args.to:
        return {"ok": False, "error": "--to required"}
    if not args.message:
        return {"ok": False, "error": "--message required"}

    result = _http_post("/send", {
        "platform": args.platform,
        "to": args.to,
        "message": args.message,
    })
    return result


def cmd_test_connection(args) -> dict:
    """Test HTTP control server reachability."""
    start = time.time()
    result = _http_get("/status", timeout=5)
    latency_ms = round((time.time() - start) * 1000, 1)
    if result.get("ok"):
        return {"ok": True, "reachable": True, "latency_ms": latency_ms,
                "port": CONTROL_PORT}
    return {"ok": False, "reachable": False, "error": result.get("error"), "port": CONTROL_PORT}


def cmd_list_adapters(args) -> dict:
    """List all adapters and their active status."""
    # Try live data first
    live = _http_get("/adapters", timeout=5)
    if live.get("ok") and "adapters" in live:
        return {"ok": True, "source": "live", "adapters": live["adapters"]}

    # Fall back to health.json
    health = _read_health_file()
    if "adapters" in health:
        return {"ok": True, "source": "health_file", "adapters": health["adapters"]}

    # Gateway not running — report from env vars
    adapters = [
        {
            "name": "telegram",
            "configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "active": None,
        },
        {
            "name": "discord",
            "configured": bool(os.environ.get("DISCORD_TOKEN")),
            "active": None,
        },
        {
            "name": "slack",
            "configured": bool(os.environ.get("SLACK_BOT_TOKEN")),
            "active": None,
        },
    ]
    return {
        "ok": True,
        "source": "env_vars",
        "warning": "Gateway not running — showing env-var configuration only",
        "adapters": adapters,
    }


# ---- CLI PARSER ----

def build_parser() -> argparse.ArgumentParser:
    # Shared parent parser so --json works both before AND after the subcommand
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--json", action="store_true", help="Output as JSON")

    parser = argparse.ArgumentParser(
        prog="gateway_admin.py",
        description="Admin CLI for the Bravo multi-platform messaging gateway",
        parents=[shared],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = sub.add_parser("start", help="Start the gateway", parents=[shared])
    p_start.add_argument("--pm2", action="store_true", help="Force PM2 even if not auto-detected")

    # stop
    sub.add_parser("stop", help="Stop the gateway", parents=[shared])

    # status
    sub.add_parser("status", help="Show gateway health and adapter status", parents=[shared])

    # send
    p_send = sub.add_parser("send", help="Send a message via a platform adapter", parents=[shared])
    p_send.add_argument("--platform", required=True, choices=["telegram", "discord", "slack"],
                        help="Target platform")
    p_send.add_argument("--to", required=True, help="Recipient ID (chat ID, channel ID, etc.)")
    p_send.add_argument("--message", required=True, help="Message text to send")

    # test-connection
    sub.add_parser("test-connection", help="Test HTTP control server reachability", parents=[shared])

    # list-adapters
    sub.add_parser("list-adapters", help="List all adapters and their active status", parents=[shared])

    return parser


def main():
    # Load .env.agents before parsing so env vars are available
    env_file = REPO_ROOT / ".env.agents"
    if env_file.exists():
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = value
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "send": cmd_send,
        "test-connection": cmd_test_connection,
        "list-adapters": cmd_list_adapters,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    result = handler(args)
    _print_or_json(result, getattr(args, "json", False))

    # Exit code: 0 if ok, 1 if not
    if not result.get("ok", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
