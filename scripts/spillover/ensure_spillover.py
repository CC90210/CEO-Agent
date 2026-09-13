#!/usr/bin/env python3
"""ensure_spillover.py - user SessionStart hook that keeps the spillover proxy up.

Registered by `omniroute_tool.py spillover enable-routing` (CONTRACT section 12)
and run windowless: `pythonw -S HOME_DIR/bin/ensure_spillover.py` (the -S skips
the venv's ~2 s site import; this file is stdlib only and deployed outside the repo).

  healthy, direct    prints nothing and exits 0 (well under 150 ms)
  healthy, spilling  SessionStart additionalContext: "FALLBACK active until <time>"
  down               spawns `node --use-system-ca HOME_DIR/app/supervisor.js`,
                     detached and windowless, waits up to 2 s for health, then says
                     "proxy restarted" or "proxy DOWN - run claude-direct ..."

The hook payload on stdin is read and ignored. The script never raises and always
exits 0: a failing SessionStart hook must not get in the way of a session.
HOME_DIR is %LOCALAPPDATA%\\bravo-spillover (Windows) or
~/Library/Application Support/bravo-spillover (macOS); the env var
BRAVO_SPILLOVER_HOME overrides it (tests).
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time

DEFAULT_HOST, DEFAULT_PORT = "127.0.0.1", 20131
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
HEALTH_PATH = "/__spillover/health"
PROBE_TIMEOUT_S = 0.3
RESTART_WAIT_S = 2.0
MAX_RESPONSE_BYTES = 65536
CREATE_NO_WINDOW, DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP = 0x08000000, 0x00000008, 0x00000200
SPAWN_FLAGS = CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
# The supervisor allowlists the env of everything it launches (CONTRACT section 10).
# Scrubbing here as well keeps the session's routing and credential vars out of the
# supervisor process itself.
SCRUB_PREFIXES = ("ANTHROPIC_", "OPENAI_", "CLAUDE_")
DOWN_ADVICE = "run claude-direct (bypasses the proxy) or omniroute_tool.py doctor"


def home_dir() -> str:
    override = os.environ.get("BRAVO_SPILLOVER_HOME")
    if override:
        return override
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "bravo-spillover")
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "bravo-spillover")


def load_config(home: str) -> dict:
    try:
        with open(os.path.join(home, "config.json"), "rb") as fh:
            data = json.loads(fh.read(1_000_000).decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def proxy_addr(cfg: dict) -> tuple[str, int]:
    proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
    host = proxy.get("host") if proxy.get("host") in LOOPBACK_HOSTS else DEFAULT_HOST
    port = proxy.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        port = DEFAULT_PORT
    return host, port


def probe_health(host: str, port: int, timeout: float = PROBE_TIMEOUT_S) -> dict | None:
    """GET the health endpoint over a raw socket. None means down or not ours.

    HTTP/1.0 so the reply is never chunked; a raw socket because urllib pulls in
    ssl and email and would eat most of the time budget.
    """
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall((f"GET {HEALTH_PATH} HTTP/1.0\r\nHost: {host}:{port}\r\n"
                          "Accept: application/json\r\nConnection: close\r\n\r\n").encode("ascii"))
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                sock.settimeout(remaining)
                data = sock.recv(8192)
                if not data:
                    break
                chunks.append(data)
                total += len(data)
                if total > MAX_RESPONSE_BYTES:
                    return None
    except OSError:
        return None
    head, sep, body = b"".join(chunks).partition(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].split()
    if not sep or len(status) < 2 or status[1] != b"200":
        return None
    try:
        doc = json.loads(body.decode("utf-8"))
    except ValueError:
        return None
    # instance_id tells our proxy apart from a foreign process on the port.
    if not isinstance(doc, dict) or doc.get("ok") is not True or not doc.get("instance_id"):
        return None
    return doc


def _epoch(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        secs = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            secs = float(value)
        except ValueError:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
    else:
        return None
    if secs > 1e11:
        secs /= 1000.0
    return secs if secs > 0 else None


def _clock(epoch: float) -> str:
    when, today = time.localtime(epoch), time.localtime()
    return time.strftime("%H:%M" if when[:3] == today[:3] else "%a %H:%M", when)


def context_for(health: dict) -> str | None:
    """The message a session should see, or None for the silent healthy case."""
    if health.get("mode") != "spilling":
        return None
    reset = _epoch(health.get("reset_at"))
    until = _clock(reset) if reset else "the limit resets"
    if health.get("fallback_healthy") is False:
        return (f"Usage limit hit and the fallback is DOWN until {until} - requests get the "
                "normal usage-limit reply. Run omniroute_tool.py doctor.")
    return f"FALLBACK active until {until} - answers come from GPT via OmniRoute"


def spawn_supervisor(home: str) -> str | None:
    """Launch the supervisor detached and windowless. Returns an error, or None."""
    supervisor = os.path.join(home, "app", "supervisor.js")
    if not os.path.isfile(supervisor):
        return "supervisor.js is not deployed"
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        return "node is not on PATH"
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(SCRUB_PREFIXES)}
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "cwd": os.path.dirname(supervisor), "env": env, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = SPAWN_FLAGS
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([node, "--use-system-ca", supervisor], **kwargs)
    except OSError as exc:
        return f"spawn failed: {exc.strerror or exc}"
    return None


def run() -> str | None:
    home = home_dir()
    host, port = proxy_addr(load_config(home))
    health = probe_health(host, port)
    if health is not None:
        return context_for(health)
    err = spawn_supervisor(home)
    if err:
        return f"proxy DOWN ({err}) - {DOWN_ADVICE}"
    deadline = time.monotonic() + RESTART_WAIT_S
    while time.monotonic() < deadline:
        time.sleep(0.1)
        health = probe_health(host, port)
        if health is not None:
            ctx = context_for(health)
            return "proxy restarted" + (f". {ctx}" if ctx else "")
    return f"proxy DOWN - {DOWN_ADVICE}"


def emit(context: str) -> None:
    if sys.stdout is None:  # pythonw with no pipe attached: nobody to tell
        return
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                  "additionalContext": "## Claude Spillover\n" + context}}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def _drain_stdin() -> None:
    stdin = sys.stdin
    if stdin is not None and not stdin.isatty():
        stdin.buffer.read(1_000_000)


def main() -> int:
    try:
        _drain_stdin()
        context = run()
        if context:
            emit(context)
    except BaseException:  # noqa: BLE001 - never block a session start
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
