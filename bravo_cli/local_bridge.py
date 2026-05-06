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
except ImportError:  # script-mode invocation (python local_bridge.py _loop)
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from _constants import dashboard_url as _resolve_dashboard_url  # type: ignore

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
                                      stderr=subprocess.STDOUT)
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


def _post_ping(token: str, services: dict[str, dict]) -> tuple[bool, str]:
    url = f"{_dashboard_url()}/api/bridge/ping"
    body = json.dumps({"services": services}).encode("utf-8")
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
    # Background spawn — detached, output to ~/.oasis/bridge.log
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore
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
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
        else:
            os.kill(pid, 15)
        PID_PATH.unlink(missing_ok=True)
        print(f"Bridge stopped (pid {pid}).")
        return 0
    except Exception as e:
        print(f"Failed to stop pid {pid}: {e}", file=sys.stderr)
        return 1


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
            ).decode("utf-8", errors="ignore")
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bravo-bridge", description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start", help="Background the bridge daemon")
    sub.add_parser("stop", help="Stop the bridge daemon")
    sub.add_parser("status", help="Show bridge status")
    sub.add_parser("seed-keys",
                   help="Push local .env.agents API keys to the dashboard so admin chat works")
    sub.add_parser("serve",
                   help="Run the local chat HTTP server on localhost:9100 — dashboard chat connects here")
    sub.add_parser("_loop", help="(internal) run the ping loop in foreground")
    args = ap.parse_args(argv)
    if args.cmd == "start":
        return cmd_start(args)
    if args.cmd == "stop":
        return cmd_stop(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "seed-keys":
        return cmd_seed_keys(args)
    if args.cmd == "serve":
        from . import bridge_chat_server
        return bridge_chat_server.serve_forever()
    if args.cmd == "_loop":
        return run_loop()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
