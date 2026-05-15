#!/usr/bin/env python3
"""
bravo_cli/local_bridge.py — local-machine pinger for the OASIS dashboard.

Detects what's installed on the operator's machine (FFmpeg, Whisper, Playwright,
Chrome harness, the agent CLIs) and pings /api/bridge/ping every 60s with a
status report. The dashboard's Integrations page then reflects real local
state instead of guessing.

Authenticates with the bridge token issued by the setup-wizard at
/api/auth/pair. Token lives at ~/.oasis/bridge_token (chmod 600).

Lifecycle:
  bravo bridge start   — backgrounds this script, writes ~/.oasis/bridge.pid
  bravo bridge stop    — kills the PID, removes the file
  bravo bridge status  — reports running / not running + last successful ping

This is a simple loop, not a system service. The trade-off: no auto-start on
reboot, but no admin-elevation pain during install. `bravo bridge start` is
all the operator ever runs.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error


try:
    from ._constants import dashboard_url as _resolve_dashboard_url
    from ._subprocess_helpers import WINDOWLESS_FLAGS
except ImportError:  # script-mode invocation (python local_bridge.py _loop)
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from _constants import dashboard_url as _resolve_dashboard_url  # type: ignore
    from _subprocess_helpers import WINDOWLESS_FLAGS  # type: ignore

HOME = Path.home()
OASIS_DIR = HOME / ".oasis"
TOKEN_PATH = OASIS_DIR / "bridge_token"
PID_PATH = OASIS_DIR / "bridge.pid"
LOG_PATH = OASIS_DIR / "bridge.log"
LAST_PING_PATH = OASIS_DIR / "bridge.last_ping"

PING_INTERVAL_SEC = 60


# --------------------------------------------------------------------------
# Detection — each function returns a dict the API records as
#   { status, metadata?, last_error? } per service slug.
# --------------------------------------------------------------------------

def _which_version(cmd: str, args: list[str], timeout: int = 5) -> tuple[bool, str]:
    """Run `cmd args` and return (success, first-line-of-output)."""
    bin_path = shutil.which(cmd)
    if not bin_path:
        return False, ""
    try:
        out = subprocess.check_output([bin_path, *args], timeout=timeout,
                                      stderr=subprocess.STDOUT,
                                      creationflags=WINDOWLESS_FLAGS)
        return True, out.decode("utf-8", errors="ignore").strip().splitlines()[0]
    except Exception as e:
        return False, str(e)


def detect_ffmpeg() -> dict:
    ok, line = _which_version("ffmpeg", ["-version"])
    if ok:
        return {"status": "healthy", "metadata": {"version": line, "path": shutil.which("ffmpeg")}}
    return {"status": "unconfigured", "last_error": "ffmpeg not on PATH"}


def detect_whisper() -> dict:
    ok, _ = _which_version("whisper", ["--help"])
    if ok:
        return {"status": "healthy", "metadata": {"path": shutil.which("whisper")}}
    return {"status": "unconfigured", "last_error": "whisper CLI not on PATH"}


def detect_browser_harness() -> dict:
    """Chrome present + (optionally) the harness CDP port reachable."""
    chrome = (
        shutil.which("chrome")
        or shutil.which("google-chrome")
        or shutil.which("Google Chrome")
        or _windows_chrome_path()
    )
    if not chrome:
        return {"status": "unconfigured", "last_error": "Chrome not detected"}
    cdp_alive = _port_open("127.0.0.1", 9222, timeout=0.5)
    return {
        "status": "healthy" if cdp_alive else "degraded",
        "metadata": {"chrome": chrome, "cdp_9222": cdp_alive},
        "last_error": None if cdp_alive else "Chrome installed but CDP port 9222 not open (browser-harness not running)",
    }


def detect_playwright() -> dict:
    ok, _ = _which_version("playwright", ["--version"])
    if ok:
        return {"status": "healthy", "metadata": {"path": shutil.which("playwright")}}
    # npx playwright is also valid
    ok2, line = _which_version("npx", ["playwright", "--version"])
    if ok2:
        return {"status": "healthy", "metadata": {"via": "npx", "version": line}}
    return {"status": "unconfigured", "last_error": "playwright not detected via PATH or npx"}


def detect_node() -> dict:
    ok, line = _which_version("node", ["--version"])
    if ok:
        return {"status": "healthy", "metadata": {"version": line.strip()}}
    return {"status": "unconfigured"}


def detect_python() -> dict:
    return {
        "status": "healthy",
        "metadata": {"version": platform.python_version(), "executable": sys.executable},
    }


def detect_repo_clones() -> dict[str, dict]:
    """Bravo / Atlas / Maven / Aura / Hermes — repo present on disk."""
    home = HOME
    candidates = {
        "bravo_repo": [home / "Business-Empire-Agent"],
        "atlas_repo": [home / "APPS" / "CFO-Agent"],
        "maven_repo": [home / "CMO-Agent"],
        "aura_repo": [home / "AURA"],
        "hermes_repo": [home / "hermes"],
    }
    out: dict[str, dict] = {}
    for slug, paths in candidates.items():
        present = next((p for p in paths if p.exists()), None)
        if present:
            out[slug] = {"status": "healthy", "metadata": {"path": str(present)}}
        else:
            out[slug] = {"status": "unconfigured"}
    return out


# Map env-var names to the integrations_registry service slug they prove up
# on. Detection is presence-only — we never read the actual value, never
# transmit it. Keys live on the operator's machine; the dashboard just
# learns "Anthropic key is on file locally" so it can flip the green dot.
ENV_TO_SERVICE: dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai_codex",
    "GOOGLE_AI_API_KEY": "google_ai",
    "GEMINI_API_KEY": "google_ai",
    "OPENROUTER_API_KEY": "openrouter",
    "STRIPE_SECRET_KEY": "stripe",
    "STRIPE_API_KEY": "stripe",
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "supabase",
    "SUPABASE_SERVICE_ROLE_KEY": "supabase",
    "VERCEL_TOKEN": "vercel",
    "CLOUDFLARE_API_TOKEN": "cloudflare",
    "HOSTINGER_API_TOKEN": "hostinger",
    "TELEGRAM_BOT_TOKEN": "telegram",
    "TWILIO_ACCOUNT_SID": "text_torrent",
    "JOTFORM_WEBHOOK_URL": "jotform",
    "FIRECRAWL_API_KEY": "firecrawl",
    "ELEVENLABS_API_KEY": "elevenlabs",
    "LATE_API_KEY": "late",
    "ZERNIO_API_KEY": "late",
    "N8N_API_KEY": "n8n_inbound",
    "KRAKEN_API_KEY": "kraken",
    "WISE_API_TOKEN": "wise",
    "IBKR_API_TOKEN": "interactive_brokers",
}

# Locations to scan for the operator's env file. We read it ONCE per ping,
# parse only the keys (never the values), and emit a service ping for each.
def _env_file_paths() -> list[Path]:
    here = Path.cwd()
    return [
        here / ".env.agents",
        here / ".env",
        HOME / ".bravo" / ".env.agents",
        HOME / "Business-Empire-Agent" / ".env.agents",
    ]


def _read_env_map() -> dict[str, str]:
    """Walk every plausible env-file path, return name->value map.

    Caller's responsibility to use values carefully — the names alone
    are safe to log; values must NEVER be logged or transmitted outside
    the explicit seed-keys flow.

    Empty dict if no file exists. Idempotent on re-runs.
    """
    out: dict[str, str] = {}
    for path in _env_file_paths():
        if not path.exists():
            continue
        try:
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in out:
                    out[k] = v
        except Exception:
            continue
    return out


def _read_env_keys() -> set[str]:
    """Just the names — safe to log. Built on top of _read_env_map()."""
    return set(_read_env_map().keys())


def detect_local_credentials() -> dict[str, dict]:
    """Walk the env file(s), emit a healthy ping for every service whose key
    is on disk. Operator-only signal — the bridge token is tenant-scoped, so
    these pings only ever land on the operator's tenant. Clients still BYO
    via /settings → Agents.
    """
    keys = _read_env_keys()
    out: dict[str, dict] = {}
    for env_var, service in ENV_TO_SERVICE.items():
        if env_var in keys and service not in out:
            out[service] = {
                "status": "healthy",
                "metadata": {
                    "via": "local_install",
                    "source_env_var": env_var,
                },
            }
    return out


def detect_claude_code_cli() -> dict:
    """Claude Code CLI presence — used by the operator chat path to spawn
    the operator's subscription instead of charging an API key."""
    ok, line = _which_version("claude", ["--version"])
    if ok:
        return {"status": "healthy", "metadata": {"path": shutil.which("claude"), "version": line}}
    return {"status": "unconfigured", "last_error": "claude CLI not on PATH"}


def detect_codex_cli() -> dict:
    ok, line = _which_version("codex", ["--version"])
    if ok:
        return {"status": "healthy", "metadata": {"path": shutil.which("codex"), "version": line}}
    return {"status": "unconfigured"}


def detect_pm2_daemons() -> dict[str, dict]:
    """Snapshot the operator's PM2 process table — surfaces background
    workers (sequence-runner, event-router, override-consumer, claude-bridge,
    lender-response-classifier, bravo-scheduler, bravo-telegram) on the
    dashboard's /automations page so the operator can see at a glance which
    daemons are alive vs stopped.

    Each PM2 entry becomes a service report keyed `pm2.<name>` with status
    `healthy` (online), `degraded` (stopped/errored), or `unconfigured` (not
    in PM2 / pm2 CLI missing). Failure is non-fatal — pm2 not installed
    just yields an empty dict and the dashboard renders the "PM2 not
    detected" path.

    Also probes for the standalone Skool daemon (NOT in PM2 — it owns its
    own DaemonLock per ecosystem.config.js header) by checking for the
    lock file or process.
    """
    out: dict[str, dict] = {}
    pm2_bin = shutil.which("pm2")
    if pm2_bin:
        try:
            res = subprocess.run(
                [pm2_bin, "jlist"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=WINDOWLESS_FLAGS,
            )
            if res.returncode == 0 and res.stdout.strip():
                procs = json.loads(res.stdout)
                for p in procs if isinstance(procs, list) else []:
                    name = p.get("name") or "unnamed"
                    pm2_env = p.get("pm2_env") or {}
                    status = pm2_env.get("status") or "unknown"
                    # PM2 statuses: online, stopping, stopped, launching,
                    # errored, one-launch-status. Map to integrations_health
                    # vocabulary.
                    if status == "online":
                        health = "healthy"
                    elif status in ("errored", "stopped"):
                        health = "down"
                    else:
                        health = "degraded"
                    monit = p.get("monit") or {}
                    out[f"pm2.{name}"] = {
                        "status": health,
                        "metadata": {
                            "pm2_status": status,
                            "pid": p.get("pid") or 0,
                            "restart_count": pm2_env.get("restart_time") or 0,
                            "uptime_ms": pm2_env.get("pm_uptime") or 0,
                            "memory_bytes": monit.get("memory") or 0,
                            "cpu_pct": monit.get("cpu") or 0,
                        },
                    }
        except Exception:
            # pm2 jlist exploded for whatever reason — don't crash the
            # heartbeat. The dashboard will just show "no PM2 data" until
            # the next successful tick.
            pass

    # Standalone Skool daemon — runs outside PM2 (DaemonLock conflict per
    # ecosystem.config.js). Detect via its lock file under the project root.
    # Resolved from this file's location since collect_services() is called
    # from arbitrary CWDs depending on PM2 invocation context.
    skool_lock = Path(__file__).resolve().parent.parent / "tmp" / "skool_engine.lock"
    if skool_lock.exists():
        try:
            mtime = skool_lock.stat().st_mtime
            stale = (time.time() - mtime) > 600  # >10 min = considered stopped
            out["skool_engine"] = {
                "status": "down" if stale else "healthy",
                "metadata": {
                    "via": "lockfile",
                    "lock_age_sec": int(time.time() - mtime),
                    "note": "Standalone daemon — `python scripts/skool_engine.py daemon --interval 5`",
                },
            }
        except Exception:
            pass
    return out


def collect_services() -> dict[str, dict]:
    services: dict[str, dict] = {
        "ffmpeg": detect_ffmpeg(),
        "whisper": detect_whisper(),
        "browser_harness": detect_browser_harness(),
        "playwright": detect_playwright(),
        "claude_code_cli": detect_claude_code_cli(),
        "codex_cli": detect_codex_cli(),
    }
    services.update(detect_repo_clones())
    # PM2 daemon snapshot — populates the dashboard's Background Workers
    # panel so the operator sees sequence-runner / event-router / claude-bridge /
    # override-consumer / lender-response-classifier status without SSH'ing
    # into their own machine.
    services.update(detect_pm2_daemons())
    # Credentials on disk — flips integration cards green for the operator
    # without them ever pasting a key into the dashboard.
    services.update(detect_local_credentials())
    return services


# --------------------------------------------------------------------------
# Network helpers
# --------------------------------------------------------------------------

def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _windows_chrome_path() -> str | None:
    if os.name != "nt":
        return None
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


# --------------------------------------------------------------------------
# Ping loop
# --------------------------------------------------------------------------

def _read_token() -> str | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _dashboard_url() -> str:
    return _resolve_dashboard_url()


class BridgeAuthError(Exception):
    """Raised when the dashboard rejects our token (401/403). Daemon should
    exit so the operator can re-pair via the wizard, not spin forever."""


def _collect_tool_capabilities() -> list[str]:
    """Return the bridge's advertised tool registry — Phase F of giggly-reef.
    Used by the heartbeat so the dashboard knows which bridge tools to put
    in TOOL_DEFINITIONS for this tenant. Failure is non-fatal: missing
    bridge_tools.py just yields an empty list and the dashboard falls back
    to "no advertised tools" semantics (which the /api/chat side treats as
    "trust the hardcoded list" for backwards compat)."""
    try:
        try:
            from .bridge_tools import list_available_tools
        except ImportError:
            from bridge_tools import list_available_tools  # type: ignore
        return list_available_tools()
    except Exception:
        return []


def _post_ping(token: str, services: dict[str, dict]) -> tuple[bool, str]:
    url = f"{_dashboard_url()}/api/bridge/ping"
    body = json.dumps({
        "services": services,
        "tool_capabilities": _collect_tool_capabilities(),
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=body,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "user-agent": f"oasis-bridge/1.0 ({platform.system()})",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise BridgeAuthError(f"HTTP {e.code} {e.reason}") from e
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:
        return False, str(e)


def _log(msg: str) -> None:
    OASIS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _poll_and_execute_cron(token: str) -> None:
    """Phase I: pull tenant_cron_jobs from the dashboard, execute any that are
    due, report results back. Called once per outer ping loop iteration so
    cron resolution is bounded by the ping interval (60s typical). Cron
    expressions are evaluated against the operator-machine clock — the
    dashboard just stores the spec; the bridge owns execution.

    Best-effort: any HTTP / parse error logs and returns. The ping loop
    continues; next iteration retries fresh.
    """
    try:
        from .cron_runner import poll_once  # type: ignore
    except ImportError:
        try:
            from cron_runner import poll_once  # type: ignore
        except ImportError:
            # Cron module not yet present in this bridge install — older
            # daemon. Skip silently; operator runs an unsupported version
            # of the bridge.
            return
    try:
        ran = poll_once(token=token, dashboard_url=_dashboard_url())
        if ran:
            _log(f"CRON ran {ran} job(s)")
    except Exception as e:
        _log(f"CRON loop error: {e}")


def run_loop() -> int:
    token = _read_token()
    if not token:
        _log(f"ABORT: no bridge token at {TOKEN_PATH}")
        print(f"No bridge token at {TOKEN_PATH}. Run the setup wizard first.", file=sys.stderr)
        return 2
    OASIS_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    _log(f"START pid={os.getpid()} dashboard={_dashboard_url()}")
    try:
        while True:
            services = collect_services()
            try:
                ok, info = _post_ping(token, services)
            except BridgeAuthError as e:
                _log(f"AUTH FAIL {e} — token rejected, exiting. "
                     f"Re-pair with `bravo setup` then `bravo bridge start`.")
                return 3
            if ok:
                LAST_PING_PATH.write_text(
                    datetime.now(timezone.utc).isoformat(), encoding="utf-8"
                )
                _log(f"OK ping recorded {len(services)} services {info}")
                # Cron tick — same cadence as ping. Polls /api/cron-jobs/poll
                # via the bridge token, evaluates schedules locally, runs
                # whatever's due. Best-effort; failures don't block the ping
                # loop.
                _poll_and_execute_cron(token)
            else:
                _log(f"FAIL {info}")
            time.sleep(PING_INTERVAL_SEC)
    except KeyboardInterrupt:
        _log("STOP via SIGINT")
        return 0
    finally:
        try:
            PID_PATH.unlink()
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------
# CLI commands (called by bravo_cli/main.py)
# --------------------------------------------------------------------------

def cmd_start(_args) -> int:
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            if _pid_alive(pid):
                print(f"Bridge already running (pid {pid}).")
                return 0
        except Exception:
            pass
    OASIS_DIR.mkdir(parents=True, exist_ok=True)
    # Background spawn — detached, output to ~/.oasis/bridge.log.
    # DETACHED_PROCESS detaches from the caller's console; WINDOWLESS_FLAGS
    # additionally prevents the spawned python.exe from allocating its
    # OWN console (DETACHED_PROCESS alone doesn't suppress that — leaks
    # a brief popup if the caller invoked us from python.exe rather than
    # pythonw.exe).
    creation_flags = 0
    if os.name == "nt":
        creation_flags = (
            subprocess.DETACHED_PROCESS  # type: ignore
            | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore
            | WINDOWLESS_FLAGS
        )
    log_fh = LOG_PATH.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_loop"],
        stdout=log_fh, stderr=log_fh,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=(os.name != "nt"),
        creationflags=creation_flags,
    )
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    print(f"Bridge started (pid {proc.pid}). Logs: {LOG_PATH}")
    return 0


def cmd_stop(_args) -> int:
    if not PID_PATH.exists():
        print("Bridge not running.")
        return 0
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        PID_PATH.unlink(missing_ok=True)
        print("Stale PID file removed.")
        return 0
    if not _pid_alive(pid):
        PID_PATH.unlink(missing_ok=True)
        print(f"Process {pid} not alive — cleaned up.")
        return 0
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False,
                           creationflags=WINDOWLESS_FLAGS)
        else:
            os.kill(pid, 15)
        PID_PATH.unlink(missing_ok=True)
        print(f"Bridge stopped (pid {pid}).")
        return 0
    except Exception as e:
        print(f"Failed to stop pid {pid}: {e}", file=sys.stderr)
        return 1


def _chat_pid_path() -> Path:
    return OASIS_DIR / "bridge_chat.pid"


def _kill_chat_server() -> tuple[bool, str]:
    """Stop the running chat server (`bravo bridge serve`).

    Strategy:
      1. Read ~/.oasis/bridge_chat.pid (written by serve_forever) and
         taskkill / SIGTERM that PID.
      2. Fallback: scan running processes for a command line containing
         `bridge_chat_server` and kill matches. Catches the case where
         the .vbs from Startup spawned a chat server before the PID
         tracking shipped.
    Returns (anything_killed, message).
    """
    killed: list[int] = []
    pid_path = _chat_pid_path()
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            if _pid_alive(pid):
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   check=False, creationflags=WINDOWLESS_FLAGS)
                else:
                    os.kill(pid, 15)
                killed.append(pid)
        except Exception:
            pass
        try:
            pid_path.unlink(missing_ok=True)
        except Exception:
            pass

    # Fallback scan — older bridges had no PID file, and the .vbs in
    # Startup may have launched a chat server we don't yet track.
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["wmic", "process", "where",
                 "name='python.exe' or name='pythonw.exe'",
                 "get", "ProcessId,CommandLine", "/format:list"],
                stderr=subprocess.DEVNULL, timeout=10,
                creationflags=WINDOWLESS_FLAGS,
            ).decode("utf-8", errors="ignore")
            current_pid = -1
            current_cmd = ""
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("CommandLine="):
                    current_cmd = line[len("CommandLine="):]
                elif line.startswith("ProcessId="):
                    try:
                        current_pid = int(line[len("ProcessId="):])
                    except Exception:
                        current_pid = -1
                    if current_pid > 0 and "bridge_chat_server" in current_cmd and current_pid not in killed:
                        subprocess.run(["taskkill", "/F", "/PID", str(current_pid)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       check=False, creationflags=WINDOWLESS_FLAGS)
                        killed.append(current_pid)
                    current_pid = -1
                    current_cmd = ""
        else:
            out = subprocess.check_output(["ps", "-eo", "pid,args"],
                                          stderr=subprocess.DEVNULL, timeout=10,
                                          creationflags=WINDOWLESS_FLAGS).decode("utf-8", errors="ignore")
            for line in out.splitlines()[1:]:
                parts = line.strip().split(None, 1)
                if len(parts) != 2:
                    continue
                try:
                    pid = int(parts[0])
                except Exception:
                    continue
                if "bridge_chat_server" in parts[1] and pid not in killed:
                    try:
                        os.kill(pid, 15)
                        killed.append(pid)
                    except Exception:
                        pass
    except Exception:
        pass

    if not killed:
        return False, "no chat-server process found"
    return True, f"killed chat-server pid(s) {killed}"


def _spawn_chat_server() -> tuple[bool, str]:
    """Background-spawn `bravo bridge serve` with no console window.
    Returns (ok, message-with-pid-or-error).
    """
    py = _resolve_pythonw()
    creation_flags = 0
    startupinfo = None
    if os.name == "nt":
        # DETACHED_PROCESS so it survives this shell, CREATE_NO_WINDOW so
        # no console flickers. Both flags together = no terminal anywhere
        # at any point — the popup CC reported is impossible from this path.
        creation_flags = (
            subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | WINDOWLESS_FLAGS
        )
    OASIS_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = LOG_PATH.open("a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [py, "-m", "bravo_cli.bridge_chat_server"],
            cwd=str(Path.cwd().resolve()),
            stdout=log_fh, stderr=log_fh,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=(os.name != "nt"),
            creationflags=creation_flags,
            startupinfo=startupinfo,
        )
        return True, f"chat-server started (pid {proc.pid}). Logs: {LOG_PATH}"
    except Exception as e:
        return False, f"failed to start chat-server: {e}"


def cmd_restart(_args) -> int:
    """Stop both bridge daemons (heartbeat + chat-server), wait for ports
    to free, then start both again. The single command CC needs after
    code changes — replaces the old "kill the python.exe in Task Manager"
    ritual."""
    print("restarting oasis bridge…")

    # 1. Stop heartbeat (uses existing cmd_stop logic).
    if PID_PATH.exists():
        cmd_stop(_args)

    # 2. Stop chat-server.
    ok, msg = _kill_chat_server()
    print(f"  chat-server: {msg}")

    # 3. Brief settle so the OS releases :9100 before we rebind.
    if ok:
        time.sleep(1.0)

    # 4. Start heartbeat (background pinger).
    rc = cmd_start(_args)
    if rc != 0:
        print("  heartbeat: failed to start", file=sys.stderr)
        return rc

    # 5. Start chat-server (HTTP on :9100).
    ok2, msg2 = _spawn_chat_server()
    print(f"  {msg2}")
    return 0 if ok2 else 1


def cmd_seed_keys(_args) -> int:
    """One-shot: read .env.agents, push provider keys to /api/auth/pair so
    every chat-eligible agent gets a working agent_model_config row.

    This is what makes admin chat "just work" without the operator pasting
    keys into /settings → Agents. The dashboard ALWAYS encrypts at rest
    (AES-256-GCM via BRAVO_FIELD_ENCRYPTION_KEY); the wire payload is over
    HTTPS and gated by CLI_SIGNUP_SECRET.
    """
    keys = _read_env_keys()
    if not keys:
        print("No .env.agents found. Run from your bravo install dir.", file=sys.stderr)
        return 2

    # Resolve the secrets we need to call the dashboard
    env_map = _read_env_map()
    secret = env_map.get("CLI_SIGNUP_SECRET", "")
    email = (
        env_map.get("USER_EMAIL")
        or env_map.get("OPERATOR_EMAIL")
        or env_map.get("USER_PRIMARY_EMAIL")
        or ""
    )
    if not secret:
        print("CLI_SIGNUP_SECRET missing from .env.agents — cannot authenticate to dashboard.", file=sys.stderr)
        return 2
    if not email:
        print("USER_EMAIL / OPERATOR_EMAIL missing from .env.agents.", file=sys.stderr)
        return 2

    # Map env names to provider slugs the API recognizes
    PROVIDER_KEYS = {
        "openrouter": ["OPENROUTER_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "google": ["GOOGLE_AI_API_KEY", "GEMINI_API_KEY"],
    }
    api_keys: dict[str, str] = {}
    for provider, candidates in PROVIDER_KEYS.items():
        for env_name in candidates:
            v = env_map.get(env_name, "").strip()
            if v:
                api_keys[provider] = v
                break

    if not api_keys:
        print(
            "No provider keys found in .env.agents. Add at least one of: "
            "OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_AI_API_KEY.",
            file=sys.stderr,
        )
        return 2

    body = json.dumps({
        "email": email,
        "profile": {},
        "machine": {
            "label": f"{platform.system()} · {socket.gethostname()}",
            "fingerprint": f"{platform.system()}|{platform.machine()}|{socket.gethostname()}",
        },
        "api_keys": api_keys,
    }).encode("utf-8")
    url = f"{_dashboard_url()}/api/auth/pair"
    req = urllib.request.Request(
        url,
        method="POST",
        data=body,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {secret}",
            "user-agent": f"oasis-bridge/1.0 ({platform.system()})",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        print(f"Dashboard returned {e.code}: {err_body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Could not reach dashboard: {e}", file=sys.stderr)
        return 1

    if not payload.get("ok"):
        print(f"Dashboard rejected: {payload.get('error', 'unknown')}", file=sys.stderr)
        return 1

    # Persist the new bridge token (this also re-pairs)
    bridge_token = (payload.get("bridge") or {}).get("token", "")
    if bridge_token:
        OASIS_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(bridge_token, encoding="utf-8")
        if os.name != "nt":
            try:
                os.chmod(TOKEN_PATH, 0o600)
            except Exception:
                pass

    seeded = payload.get("seeded") or {}
    print(f"OK — seeded {seeded.get('agents', 0)} agent(s) using provider {seeded.get('provider', '?')}.")
    print(f"Providers detected locally: {', '.join(api_keys.keys())}")
    print(f"Open https://agent-dashboard-cc90210.vercel.app/agents and start chatting.")
    return 0


def cmd_status(_args) -> int:
    running = False
    pid: int | None = None
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            running = _pid_alive(pid)
        except Exception:
            running = False
    last_ping = None
    if LAST_PING_PATH.exists():
        try:
            last_ping = LAST_PING_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    print("oasis local bridge")
    print(f"  running   : {'yes' if running else 'no'}" + (f" (pid {pid})" if pid else ""))
    print(f"  token     : {'on file' if TOKEN_PATH.exists() else 'MISSING — run setup wizard'}")
    print(f"  last ping : {last_ping or 'never'}")
    print(f"  log       : {LOG_PATH}")
    return 0 if running else 1


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}"],
                stderr=subprocess.DEVNULL,
                creationflags=WINDOWLESS_FLAGS,
            ).decode("utf-8", errors="ignore")
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _resolve_pythonw() -> str:
    """Return a windowless Python interpreter path. Wraps the shared
    `prefer_pythonw` primitive so this caller and skool_watchdog stay in
    lockstep — one source of truth for the python→pythonw resolution.
    Returns a string for backward-compat with existing callers (wizard,
    schtasks, plist, .vbs)."""
    try:
        from ._subprocess_helpers import prefer_pythonw
    except ImportError:  # script-mode invocation
        from _subprocess_helpers import prefer_pythonw  # type: ignore
    return str(prefer_pythonw(sys.executable))


def _install_windows_startup_folder(py: str) -> tuple[bool, str]:
    """Fallback for Windows when schtasks denies access. Drops a .vbs
    in the user's Startup folder. .vbs is run via wscript.exe with no
    visible window — `.cmd` files would pop a brief cmd.exe console
    on every login (CC reported this; user-visible regression). The
    .vbs version uses `WshShell.Run("cmd /c ...", 0, False)` which
    hides the console entirely.
    Always works — no admin / interactive session required. Idempotent:
    overwrites any prior .vbs AND removes a stale .cmd from older
    installs so we don't end up with duplicate startup entries.
    Returns (ok, message).
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return False, "APPDATA env var missing — can't locate Startup folder"
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    if not startup.is_dir():
        return False, f"Startup folder not found at {startup}"
    cwd = Path.cwd().resolve()

    # Remove the legacy .cmd if a previous install left one — otherwise
    # both fire at login and the user sees the popup we're trying to
    # eliminate.
    legacy_cmd = startup / "OASIS-Bravo-Bridge.cmd"
    if legacy_cmd.is_file():
        try:
            legacy_cmd.unlink()
        except Exception:
            pass

    # VBS launcher — same hidden-console pattern as start-bravo.vbs and
    # atlas_paper_trade.vbs already in CC's Startup folder. Quotes
    # inside the cmd string are doubled per VBS string-escape rules.
    cwd_q = str(cwd).replace('"', '""')
    py_q = str(py).replace('"', '""')
    vbs_path = startup / "OASIS-Bravo-Bridge.vbs"
    vbs_path.write_text(
        "' OASIS Bravo Bridge - Silent auto-start on Windows login\r\n"
        "' Replaces OASIS-Bravo-Bridge.cmd (which popped a console window)\r\n"
        "' Auto-installed by `bravo bridge install`.\r\n"
        "Set WshShell = CreateObject(\"WScript.Shell\")\r\n"
        f'WshShell.Run "cmd /c cd /d ""{cwd_q}"" && ""{py_q}"" -m bravo_cli.bridge_chat_server", 0, False\r\n',
        encoding="utf-8",
    )
    return True, str(vbs_path)


def cmd_install(_args) -> int:
    """Register the bridge to auto-start at user login.

    Windows: schtasks ONLOGON first; falls back to dropping a .cmd in
             the Startup folder when schtasks denies (common in non-
             interactive subprocesses, restricted-user accounts, or
             group-policy-locked machines).
    macOS:   ~/Library/LaunchAgents/work.oasisai.bravo-bridge.plist with
             RunAtLoad=true.
    Linux:   ~/.config/systemd/user/bravo-bridge.service + `systemctl
             --user enable --now`. Falls back to ~/.config/autostart/
             *.desktop when systemd-user isn't available (containers,
             non-systemd distros).

    Idempotent: re-running updates the existing entry. Reports which
    install path was taken so the operator knows what to expect.
    """
    py_runner = _resolve_pythonw()
    label = "OASIS Bravo Bridge"

    if os.name == "nt":
        task_name = "OASIS-Bravo-Bridge"
        # First try schtasks — runs as user at login, no admin needed.
        # /F — force overwrite if task exists.
        # /RL LIMITED — runs as user, no elevation.
        # /TR uses bridge_chat_server directly (the chat HTTP server) so
        # the auto-start matches what the dashboard expects on :9100.
        cmd = [
            "schtasks", "/Create",
            "/TN", task_name,
            "/SC", "ONLOGON",
            "/RL", "LIMITED",
            "/F",
            "/TR", f'"{py_runner}" -m bravo_cli.bridge_chat_server',
        ]
        schtasks_err: str | None = None
        try:
            r = subprocess.run(cmd, check=False, capture_output=True, text=True,
                               creationflags=WINDOWLESS_FLAGS)
            if r.returncode == 0:
                print(f"OK — registered Windows scheduled task '{task_name}'.")
                print(f"     Path: schtasks ONLOGON")
                print(f"     Run now: schtasks /Run /TN {task_name}")
                print(f"     Remove:  bravo bridge uninstall")
                return 0
            schtasks_err = (r.stderr.strip() or r.stdout.strip() or "unknown error").splitlines()[0]
        except FileNotFoundError:
            schtasks_err = "schtasks.exe not on PATH"
        # Fallback — Startup folder drop. Works without elevation or an
        # interactive session token.
        ok, msg = _install_windows_startup_folder(py_runner)
        if ok:
            print(f"NOTE — schtasks declined ({schtasks_err}); used Startup-folder fallback.")
            print(f"OK — installed launcher at {msg}.")
            print(f"     Path: Windows Startup folder (works without elevation)")
            print(f"     Will auto-start the bridge each time you log in.")
            print(f"     Remove:  bravo bridge uninstall")
            return 0
        print(f"FAIL — schtasks: {schtasks_err}", file=sys.stderr)
        print(f"FAIL — Startup-folder fallback: {msg}", file=sys.stderr)
        return 1

    if sys.platform == "darwin":
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path = plist_dir / "work.oasisai.bravo-bridge.plist"
        # WorkingDirectory: launchd starts the process with cwd=/, so
        # `python -m bravo_cli.local_bridge` can't find the package
        # unless we pin cwd to the repo root captured at install time.
        cwd = str(Path.cwd().resolve())
        plist_path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>work.oasisai.bravo-bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py_runner}</string>
        <string>-m</string>
        <string>bravo_cli.local_bridge</string>
        <string>serve</string>
    </array>
    <key>WorkingDirectory</key><string>{cwd}</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{LOG_PATH}</string>
    <key>StandardErrorPath</key><string>{LOG_PATH}</string>
</dict>
</plist>
""", encoding="utf-8")
        try:
            subprocess.run(["launchctl", "unload", str(plist_path)],
                           check=False, capture_output=True,
                           creationflags=WINDOWLESS_FLAGS)
        except FileNotFoundError:
            pass
        try:
            subprocess.run(["launchctl", "load", "-w", str(plist_path)],
                           check=False, capture_output=True,
                           creationflags=WINDOWLESS_FLAGS)
        except FileNotFoundError:
            pass
        print(f"OK — installed launchd plist at {plist_path}.")
        print(f"     Will auto-start the bridge each time you log in.")
        print(f"     Status: launchctl list | grep bravo-bridge")
        print(f"     Remove: bravo bridge uninstall")
        return 0

    # Linux — assume systemd user. WorkingDirectory pinned at install
    # time so `python -m bravo_cli.local_bridge` resolves the package
    # (same fix as the macOS plist; without it systemd starts with cwd=/
    # and hits ModuleNotFoundError).
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "bravo-bridge.service"
    cwd = str(Path.cwd().resolve())
    unit_path.write_text(f"""[Unit]
Description={label}
After=network-online.target

[Service]
Type=simple
WorkingDirectory={cwd}
ExecStart={py_runner} -m bravo_cli.local_bridge serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
""", encoding="utf-8")
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False,
                       creationflags=WINDOWLESS_FLAGS)
        subprocess.run(["systemctl", "--user", "enable", "--now", "bravo-bridge.service"],
                       check=False, capture_output=True,
                       creationflags=WINDOWLESS_FLAGS)
    except FileNotFoundError:
        print("systemctl not found — install manually:", file=sys.stderr)
        print(f"  systemctl --user enable --now bravo-bridge.service", file=sys.stderr)
        return 1
    print(f"OK — installed systemd user unit at {unit_path}.")
    print(f"     Status: systemctl --user status bravo-bridge")
    print(f"     Remove: bravo bridge uninstall")
    return 0


def cmd_uninstall(_args) -> int:
    """Reverse of cmd_install. Cleans up BOTH paths on Windows since
    cmd_install may have used either schtasks OR the Startup-folder
    fallback — we don't track which one, so try both."""
    if os.name == "nt":
        task_name = "OASIS-Bravo-Bridge"
        removed_any = False
        # Try schtasks
        try:
            r = subprocess.run(
                ["schtasks", "/Delete", "/TN", task_name, "/F"],
                check=False, capture_output=True, text=True,
                creationflags=WINDOWLESS_FLAGS,
            )
            if r.returncode == 0:
                print(f"OK — removed Windows scheduled task '{task_name}'.")
                removed_any = True
        except FileNotFoundError:
            pass
        # Try Startup-folder launcher
        appdata = os.environ.get("APPDATA")
        if appdata:
            cmd_path = (Path(appdata) / "Microsoft" / "Windows" / "Start Menu"
                        / "Programs" / "Startup" / "OASIS-Bravo-Bridge.cmd")
            if cmd_path.exists():
                cmd_path.unlink()
                print(f"OK — removed Startup-folder launcher at {cmd_path}.")
                removed_any = True
        if not removed_any:
            print("Nothing to remove — bridge was not installed via either path.")
        return 0
    if sys.platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / "work.oasisai.bravo-bridge.plist"
        try:
            subprocess.run(["launchctl", "unload", str(plist_path)],
                           check=False, capture_output=True,
                           creationflags=WINDOWLESS_FLAGS)
        except FileNotFoundError:
            pass
        plist_path.unlink(missing_ok=True)
        print(f"OK — removed launchd plist.")
        return 0
    # Linux
    try:
        subprocess.run(["systemctl", "--user", "disable", "--now", "bravo-bridge.service"],
                       check=False, capture_output=True,
                       creationflags=WINDOWLESS_FLAGS)
    except FileNotFoundError:
        pass
    unit_path = Path.home() / ".config" / "systemd" / "user" / "bravo-bridge.service"
    unit_path.unlink(missing_ok=True)
    print(f"OK — removed systemd user unit.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bravo-bridge", description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start", help="Background the bridge daemon")
    sub.add_parser("stop", help="Stop the bridge daemon")
    sub.add_parser("restart", help="Stop + start both heartbeat and chat-server")
    sub.add_parser("status", help="Show bridge status")
    sub.add_parser("seed-keys",
                   help="Push local .env.agents API keys to the dashboard so admin chat works")
    sub.add_parser("serve",
                   help="Run the local chat HTTP server on localhost:9100 — dashboard chat connects here")
    sub.add_parser("install",
                   help="Auto-start the bridge at login (Win schtasks / mac launchd / Linux systemd)")
    sub.add_parser("uninstall",
                   help="Reverse `install` — removes the OS auto-start entry")
    sub.add_parser("_loop", help="(internal) run the ping loop in foreground")
    args = ap.parse_args(argv)
    if args.cmd == "start":
        return cmd_start(args)
    if args.cmd == "stop":
        return cmd_stop(args)
    if args.cmd == "restart":
        return cmd_restart(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "seed-keys":
        return cmd_seed_keys(args)
    if args.cmd == "serve":
        from . import bridge_chat_server
        return bridge_chat_server.serve_forever()
    if args.cmd == "install":
        return cmd_install(args)
    if args.cmd == "uninstall":
        return cmd_uninstall(args)
    if args.cmd == "_loop":
        return run_loop()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
