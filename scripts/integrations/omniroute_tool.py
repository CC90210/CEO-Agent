"""omniroute_tool.py — operator CLI for Bravo's "Claude Spillover" system.

Claude Spillover fails Claude Code over to OmniRoute (a self-hosted LLM
router, https://github.com/diegosouzapw/OmniRoute) when Anthropic returns an
account-wide subscription usage-limit 429. This tool deploys, starts/stops,
configures and audits the local pieces (`scripts/spillover/*`) and drives
OmniRoute's own HTTP management API — it never talks to Anthropic itself.
Full interface contract: scripts/spillover/CONTRACT.md.

USAGE
-----
    python scripts/integrations/omniroute_tool.py deploy [--json]
    python scripts/integrations/omniroute_tool.py start|stop|status [--json]
    python scripts/integrations/omniroute_tool.py rollback [--all] [--json]
    python scripts/integrations/omniroute_tool.py key set|check [--json]
    python scripts/integrations/omniroute_tool.py secrets init [--json]
    python scripts/integrations/omniroute_tool.py omniroute setup [--models-main M ...] [--models-fast M ...] [--json]
    python scripts/integrations/omniroute_tool.py omniroute connect codex [--json]
    python scripts/integrations/omniroute_tool.py omniroute connect-key cerebras|zai [--json]
    python scripts/integrations/omniroute_tool.py smoke [--model M] [--tools] [--stream] [--corpus DIR] [--json]
    python scripts/integrations/omniroute_tool.py doctor [--json]
    python scripts/integrations/omniroute_tool.py install --verify [--json]
    python scripts/integrations/omniroute_tool.py attest chatgpt-training-off [--json]
    python scripts/integrations/omniroute_tool.py uninstall [--purge] [--yes] [--json]
    python scripts/integrations/omniroute_tool.py spillover mode passthrough|observe|spill [--json]
    python scripts/integrations/omniroute_tool.py spillover enable-routing [--yes] [--json]
    python scripts/integrations/omniroute_tool.py spillover disable-routing [--remove] [--json]
    python scripts/integrations/omniroute_tool.py spillover deny-repo <path> [--json]
    python scripts/integrations/omniroute_tool.py spillover fault set force_limit|force_reset|omniroute_down --ttl SEC [--json]
    python scripts/integrations/omniroute_tool.py spillover fault clear [--json]
    python scripts/integrations/omniroute_tool.py spillover events [--tail N] [--json]
    python scripts/integrations/omniroute_tool.py spillover status [--json]

EXIT CODES
----------
    0 — ok
    1 — bad invocation
    2 — OmniRoute/proxy unreachable
    3 — a doctor/smoke/install-verify check failed
    4 — refused (unsafe state)

TEST SEAMS
----------
    BRAVO_SPILLOVER_HOME   overrides HOME_DIR (default %LOCALAPPDATA%/bravo-spillover
                           on Windows, ~/Library/Application Support/bravo-spillover on macOS)
    BRAVO_CLAUDE_SETTINGS  overrides the Claude Code settings.json path (default ~/.claude/settings.json)
    BRAVO_IDE_SETTINGS     overrides the Antigravity/VS Code settings.json path this tool
                           optionally mirrors the same env keys into, when that file already exists

Real (non-test) runs of this file are limited by the operator to --help and read-only verbs
(status/doctor/install --verify/events); everything else touches only HOME_DIR (never the
OmniRoute source checkout, which is read-only reference) and ~/.claude/settings.json.
"""
from __future__ import annotations

import argparse
import difflib
import getpass
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

try:  # Windows console defaults to cp1252 — same guard harness_eval.py uses
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from lib.tls_trust import ensure_os_trust  # noqa: E402 — Windows CA-bundle fix

ensure_os_trust()

# Governance metadata — parsed statically by scripts/lib/capability_metadata.py.
# Never imported/executed for that purpose, so keep this a plain literal.
CAPABILITY_META = {
    "category": "model.fallback",
    "lifecycle": "active",
    "risk": "local_write",
    "triggers": ["claude usage limit", "switch to fallback model", "omniroute", "spillover status", "claude-direct"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

EXIT_OK, EXIT_USAGE, EXIT_UNREACHABLE, EXIT_CHECK_FAILED, EXIT_REFUSED = 0, 1, 2, 3, 4

IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

SPILLOVER_SRC = REPO / "scripts" / "spillover"
APP_FILE_NAMES = ["spillover_proxy.js", "limit_detector.js", "supervisor.js"]
BIN_FILE_NAMES = ["lane_key.py", "statusline.py", "ensure_spillover.py", "spillover_alert.py", "claude-direct.cmd"]
REPO_CONFIG_PATH = REPO / "config" / "spillover.json"
CONTRACT_PATH = REPO / "scripts" / "spillover" / "CONTRACT.md"

VALID_MODES = ("passthrough", "observe", "spill")
FAULT_MODES = ("force_limit", "force_reset", "omniroute_down")
CLAUDE_CREDENTIAL_KEYS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "apiKeyHelper")
SECRET_SPECS = (("storage_encryption", 32), ("initial_password", 24), ("jwt_secret", 32), ("api_key_secret", 32))
COMBO_MAIN = "bravo-fallback"
COMBO_FAST = "bravo-fallback-fast"
DEFAULT_MODELS_MAIN = ["cx/gpt-5.6-sol", "cx/gpt-6-astra"]
DEFAULT_MODELS_FAST = ["cx/gpt-5.6-sol"]
START_HEALTH_TIMEOUT_SEC = 30.0
# Verified live against the pinned OmniRoute source (src/lib/logEnv.ts): small
# retention/size caps so call/app logs can't grow unbounded. Rotation is
# triggered on write (callLogs.ts -> scheduleCallLogRotation() ->
# rotateCallLogs()), so these caps hold whether or not OmniRoute's background
# cleanup scheduler runs.
# `deploy` seeds these into HOME_DIR/config.json omniroute.log_env without
# overwriting any value the operator already set; `doctor` reports which of
# these names are present/missing (names only, values are non-secret but kept
# out of the check detail for symmetry with the DATA_DIR/.env check).
DEFAULT_OMNIROUTE_LOG_ENV = {
    "CALL_LOG_RETENTION_DAYS": "1",
    "CALL_LOG_MAX_ENTRIES": "200",
    "CALL_LOGS_TABLE_MAX_ROWS": "200",
    "CHAT_LOG_TEXT_LIMIT": "2048",
    "CHAT_LOG_MAX_BODY_KB": "16",
    "CALL_LOG_PIPELINE_CAPTURE_STREAM_CHUNKS": "false",
    "APP_LOG_TO_FILE": "false",
    "CHAT_DEBUG_FILE": "false",
    "APP_LOG_LEVEL": "info",
}
CODEX_BASE = "https://auth.openai.com"
CODEX_API_BASE = f"{CODEX_BASE}/api/accounts"
# Public Codex CLI client id (RFC 8252 — relies on PKCE, not secrecy). Mirrors
# omniroute-src/src/lib/oauth/codexDeviceFlow.ts DEFAULT_CLIENT_ID.
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_VERIFICATION_URI = f"{CODEX_BASE}/codex/device"
CODEX_REDIRECT_URI = f"{CODEX_BASE}/deviceauth/callback"
CODEX_POLL_TIMEOUT_SEC = 15 * 60  # OpenAI expires the device code in 15 min; contract says "or 10 minutes pass"
CODEX_POLL_DEADLINE_SEC = 10 * 60
# provider ids as accepted by POST /api/providers {provider, apiKey, name}
# (omniroute-src/src/shared/validation/schemas/provider.ts). "zai" = api.z.ai
# (international), never the mainland glm-cn variant (forbidden_model_prefixes
# includes "glm-cn/").
CONNECT_KEY_PROVIDERS = {"cerebras": "cerebras", "zai": "zai"}
# omniroute-src/src/shared/constants/dashboardCsrf.ts DASHBOARD_CSRF_HEADER
CSRF_HEADER = "x-omniroute-csrf"


# --------------------------------------------------------------------------- #
# Paths (all test-overridable per CONTRACT-adjacent conventions)
# --------------------------------------------------------------------------- #
def home_dir() -> Path:
    override = os.environ.get("BRAVO_SPILLOVER_HOME")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "bravo-spillover"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "bravo-spillover"


def claude_settings_path() -> Path:
    override = os.environ.get("BRAVO_CLAUDE_SETTINGS")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "settings.json"


def ide_settings_path() -> Path | None:
    """Antigravity/VS Code settings mirror target. None when no default resolves."""
    override = os.environ.get("BRAVO_IDE_SETTINGS")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Antigravity" / "User" / "settings.json"


def startup_vbs_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Bravo Claude Spillover.vbs"


def lane_key_script(home: Path) -> Path:
    deployed = home / "bin" / "lane_key.py"
    return deployed if deployed.is_file() else (SPILLOVER_SRC / "lane_key.py")


def resolve_runtime_dir(home: Path, cfg: dict) -> Path:
    raw = ((cfg.get("omniroute") or {}) if isinstance(cfg.get("omniroute"), dict) else {}).get("runtime_dir") or "omniroute-src"
    p = Path(raw)
    return p if p.is_absolute() else (home / p)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# File I/O: atomic writes with backup, JSON config merge
# --------------------------------------------------------------------------- #
def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    last_exc: OSError | None = None
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:  # pragma: no cover - Windows file-lock races
            last_exc = exc
            time.sleep(0.01 * (attempt + 1))
    try:
        tmp.unlink()
    except OSError:
        pass
    if last_exc:
        raise last_exc


def atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_bytes(path, (json.dumps(obj, indent=2, sort_keys=False) + "\n").encode("utf-8"))


def atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None


def backup_file(path: Path, label: str) -> Path | None:
    if not path.is_file():
        return None
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = path.with_name(f"{path.name}.backup-{label}-{ts}")
    shutil.copy2(path, backup)
    return backup


def merge_missing(dst: dict, src: dict) -> None:
    """Merge keys from src into dst that dst does not already have (recursive)."""
    for key, value in src.items():
        if key not in dst:
            dst[key] = value
        elif isinstance(value, dict) and isinstance(dst.get(key), dict):
            merge_missing(dst[key], value)


def load_home_config(home: Path) -> dict:
    data = load_json_file(home / "config.json")
    return data if isinstance(data, dict) else {}


def proxy_addr(cfg: dict) -> tuple[str, int]:
    proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
    host = proxy.get("host") if proxy.get("host") in ("127.0.0.1", "localhost") else "127.0.0.1"
    port = proxy.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        port = 20131
    return host, port


def omniroute_base(cfg: dict) -> str:
    proxy = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
    return proxy.get("omniroute_base") or "http://127.0.0.1:20128"


# --------------------------------------------------------------------------- #
# Subprocess (Rule 15 — every subprocess windowless, timed, never prints secrets)
# --------------------------------------------------------------------------- #
def run_cmd(cmd: list[str], *, timeout: float = 30, cwd: str | None = None,
            env: dict | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    kwargs: dict[str, Any] = {
        "cwd": cwd, "env": env, "timeout": timeout, "text": True,
        "encoding": "utf-8", "errors": "replace",
        "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
    }
    if input_text is not None:
        kwargs["input"] = input_text
    else:
        kwargs["stdin"] = subprocess.DEVNULL
    if IS_WINDOWS:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def run_interactive(cmd: list[str], *, timeout: float = 120, cwd: str | None = None,
                     env: dict | None = None) -> subprocess.CompletedProcess:
    """Inherits this process's console (for getpass prompts). Still windowless-safe:
    CREATE_NO_WINDOW only suppresses a NEW console, which is never allocated when
    stdio is inherited from an existing one."""
    kwargs: dict[str, Any] = {"cwd": cwd, "env": env, "timeout": timeout}
    if IS_WINDOWS:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def spawn_detached(cmd: list[str], *, cwd: str | None = None, env: dict | None = None) -> subprocess.Popen:
    kwargs: dict[str, Any] = {
        "cwd": cwd, "env": env, "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


# --------------------------------------------------------------------------- #
# lane_key.py wrappers — secrets never touch argv-visible-to-log or stdout of ours
# --------------------------------------------------------------------------- #
def lane_key_exists(python_exe: str, name: str, home: Path) -> bool:
    try:
        cp = run_cmd([python_exe, str(lane_key_script(home)), "exists", name], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return cp.returncode == 0


def lane_key_get(python_exe: str, name: str, home: Path) -> str | None:
    try:
        cp = run_cmd([python_exe, str(lane_key_script(home)), "get", name], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if cp.returncode != 0:
        return None
    value = (cp.stdout or "").strip()
    return value or None


def lane_key_generate(python_exe: str, name: str, home: Path, *, nbytes: int = 32) -> tuple[bool, str]:
    cmd = [python_exe, str(lane_key_script(home)), "generate", name, "--bytes", str(nbytes)]
    try:
        cp = run_cmd(cmd, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return cp.returncode == 0, (cp.stderr or cp.stdout or "").strip()


def lane_key_set_stdin(python_exe: str, name: str, home: Path, value: str) -> bool:
    cmd = [python_exe, str(lane_key_script(home)), "set", name, "--stdin"]
    try:
        cp = run_cmd(cmd, timeout=30, input_text=value + "\n")
    except (OSError, subprocess.SubprocessError):
        return False
    return cp.returncode == 0


# --------------------------------------------------------------------------- #
# HTTP — stdlib only. urllib picks up the OS trust store via ensure_os_trust().
# --------------------------------------------------------------------------- #
class ApiUnreachable(Exception):
    """Network/transport failure talking to the proxy or OmniRoute."""


# auth.openai.com's edge answers Python's default "Python-urllib/x" identity with a 530 (live 2026-09-13)
# while a descriptive User-Agent gets through. This names the tool; it doesn't pose as a browser.
HTTP_USER_AGENT = "bravo-spillover/1.0 (omniroute_tool)"


def http_call(url: str, *, method: str = "GET", headers: dict | None = None,
              json_body: Any = None, raw_body: bytes | None = None,
              timeout: float = 10, opener: urllib.request.OpenerDirector | None = None
              ) -> tuple[int, Any, bytes]:
    hdrs = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in hdrs):
        hdrs["User-Agent"] = HTTP_USER_AGENT
    data: bytes | None = None
    if raw_body is not None:
        data = raw_body
    elif json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    use_opener = opener or urllib.request.build_opener()
    try:
        with use_opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.getcode() or 200
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiUnreachable(str(exc)) from exc
    parsed = None
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
    return status, parsed, raw


def proxy_health(host: str, port: int, timeout: float = 2.0) -> dict | None:
    try:
        status, parsed, _ = http_call(f"http://{host}:{port}/__spillover/health", timeout=timeout)
    except ApiUnreachable:
        return None
    if status == 200 and isinstance(parsed, dict) and parsed.get("ok") is True:
        return parsed
    return None


class OmniRouteAdmin:
    """Dashboard-session client: POST /api/auth/login (password) sets an
    httpOnly auth_token cookie; GET /api/auth/csrf then mints a short-lived
    x-omniroute-csrf token this class attaches to every mutation. Belt-and-
    braces only — omniroute-src/src/server/authz/pipeline.ts falls back to
    Origin-header validation, which passes trivially for a same-host CLI
    client that never sends an Origin header at all — but a real dashboard
    client sends the CSRF token, so we do too (CONTRACT research: "including
    any CSRF step")."""

    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf: str | None = None

    def _call(self, method: str, path: str, body: Any = None, *, use_csrf: bool = True) -> tuple[int, Any, bytes]:
        headers = {}
        if use_csrf and self.csrf and method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            headers[CSRF_HEADER] = self.csrf
        return http_call(self.base_url + path, method=method, headers=headers, json_body=body,
                          timeout=self.timeout, opener=self.opener)

    def login(self, password: str) -> None:
        status, parsed, _ = self._call("POST", "/api/auth/login", {"password": password}, use_csrf=False)
        if status != 200 or not isinstance(parsed, dict) or not parsed.get("success"):
            raise ApiUnreachable(f"omniroute login failed (status {status})")
        status2, parsed2, _ = self._call("GET", "/api/auth/csrf", use_csrf=False)
        if status2 == 200 and isinstance(parsed2, dict) and parsed2.get("token"):
            self.csrf = parsed2["token"]

    def get(self, path: str) -> tuple[int, Any, bytes]:
        return self._call("GET", path)

    def post(self, path: str, body: Any = None) -> tuple[int, Any, bytes]:
        return self._call("POST", path, body)

    def patch(self, path: str, body: Any = None) -> tuple[int, Any, bytes]:
        return self._call("PATCH", path, body)


def admin_session(cfg: dict, home: Path) -> tuple[OmniRouteAdmin | None, str | None]:
    python_exe = cfg.get("python_exe") or sys.executable
    password = lane_key_get(python_exe, "initial_password", home)
    if not password:
        return None, "initial_password secret is not stored (run `secrets init`)"
    session = OmniRouteAdmin(omniroute_base(cfg))
    try:
        session.login(password)
    except ApiUnreachable as exc:
        return None, f"omniroute admin login failed: {exc}"
    finally:
        password = None  # noqa: F841 - drop the reference; never logged either way
    return session, None


# --------------------------------------------------------------------------- #
# Claude Code version checks (used by enable-routing and doctor)
# --------------------------------------------------------------------------- #
def get_running_claude_versions() -> list[str]:
    if not IS_WINDOWS:
        return []
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='claude.exe'\" -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.ExecutablePath } | Where-Object { $_ } | "
        "ForEach-Object { (Get-Item $_ -ErrorAction SilentlyContinue).VersionInfo.ProductVersion }"
    )
    try:
        cp = run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    if cp.returncode != 0:
        return []
    return [ln.strip() for ln in (cp.stdout or "").splitlines() if ln.strip()]


def get_cli_claude_version() -> str | None:
    claude = shutil.which("claude")
    if not claude:
        return None
    try:
        cp = run_cmd([claude, "--version"], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if cp.returncode != 0:
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", cp.stdout or "")
    return m.group(1) if m else None


def version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(value).split("."):
        m = re.match(r"\d+", chunk)
        parts.append(int(m.group()) if m else 0)
    return tuple(parts)


def check_claude_code_versions(cfg: dict, *, running: list[str] | None = None,
                                cli: str | None = "__unset__") -> dict:
    min_v = cfg.get("min_claude_code")
    deny = set(cfg.get("deny_claude_code") or [])
    versions = set(running if running is not None else get_running_claude_versions())
    cli_v = get_cli_claude_version() if cli == "__unset__" else cli
    if cli_v:
        versions.add(cli_v)
    bad = []
    for v in versions:
        if v in deny:
            bad.append([v, "denied"])
        elif min_v and version_tuple(v) < version_tuple(min_v):
            bad.append([v, f"below min {min_v}"])
    return {"ok": not bad, "versions": sorted(versions), "bad": bad}


# --------------------------------------------------------------------------- #
# ACLs / Startup VBS (deploy)
# --------------------------------------------------------------------------- #
def _current_user_for_acl() -> str | None:
    user = os.environ.get("USERNAME")
    domain = os.environ.get("USERDOMAIN")
    if user and domain:
        return f"{domain}\\{user}"
    return user


def restrict_dir_to_owner(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    if not IS_WINDOWS:
        try:
            os.chmod(path, 0o700)
            return "chmod-0700"
        except OSError as exc:
            return f"error: {exc}"
    user = _current_user_for_acl()
    if not user:
        return "error: cannot resolve current user for ACL"
    try:
        cp = run_cmd(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"], timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"error: {exc}"
    if cp.returncode != 0:
        tail = (cp.stderr or cp.stdout or "").strip()[-200:]
        return f"icacls exit {cp.returncode}: {tail}"
    return "owner-only"


def write_startup_vbs(home: Path) -> Path:
    path = startup_vbs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    supervisor = str((home / "app" / "supervisor.js").resolve())
    cmd_line = f'node --use-system-ca "{supervisor}"'
    escaped = cmd_line.replace('"', '""')  # VBScript string-literal escaping
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\r\n'
        f'WshShell.Run "{escaped}", 0, False\r\n'
    )
    atomic_write_text(path, vbs)
    return path


def git_sha(repo: Path = REPO) -> str:
    try:
        cp = run_cmd(["git", "-C", str(repo), "rev-parse", "HEAD"], timeout=10)
        if cp.returncode == 0:
            return cp.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "dev"


# --------------------------------------------------------------------------- #
# Verb implementations — each returns (exit_code, payload: dict, message: str)
# --------------------------------------------------------------------------- #
def _do_deploy() -> tuple[int, dict, str]:
    home = home_dir()
    app_dir = home / "app"
    bin_dir = home / "bin"
    app_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in APP_FILE_NAMES:
        src = SPILLOVER_SRC / name
        if not src.is_file():
            return EXIT_USAGE, {}, f"missing source file: {src}"
        shutil.copy2(src, app_dir / name)
        copied.append(str(app_dir / name))
    for name in BIN_FILE_NAMES:
        src = SPILLOVER_SRC / name
        if not src.is_file():
            return EXIT_USAGE, {}, f"missing source file: {src}"
        shutil.copy2(src, bin_dir / name)
        copied.append(str(bin_dir / name))

    sha = git_sha()
    atomic_write_text(app_dir / "VERSION", sha + "\n")

    if not REPO_CONFIG_PATH.is_file():
        return EXIT_USAGE, {}, f"missing repo config defaults: {REPO_CONFIG_PATH}"
    repo_cfg = json.loads(REPO_CONFIG_PATH.read_text(encoding="utf-8"))
    home_cfg_path = home / "config.json"
    existing = load_json_file(home_cfg_path)
    merged = isinstance(existing, dict)
    final_cfg = existing if merged else {}
    merge_missing(final_cfg, repo_cfg)
    # python_exe is machine-specific, so the repo defaults carry none. Keep a configured interpreter that
    # still exists; otherwise use the one running this deploy (the proxy and supervisor use it for secrets
    # and alerts, so a dangling path takes both down).
    configured_python = final_cfg.get("python_exe")
    if not (isinstance(configured_python, str) and configured_python and Path(configured_python).is_file()):
        final_cfg["python_exe"] = Path(sys.executable).as_posix()
    omni_section = dict(final_cfg.get("omniroute") or {})
    log_env = dict(omni_section.get("log_env") or {})
    merge_missing(log_env, DEFAULT_OMNIROUTE_LOG_ENV)
    omni_section["log_env"] = log_env
    final_cfg["omniroute"] = omni_section
    atomic_write_json(home_cfg_path, final_cfg)

    acl = {sub: restrict_dir_to_owner(home / sub) for sub in ("secrets", "omniroute-data")}

    vbs_path = None
    if IS_WINDOWS:
        try:
            vbs_path = str(write_startup_vbs(home))
        except OSError as exc:
            vbs_path = f"error: {exc}"

    payload = {
        "home": str(home), "copied": copied, "version": sha,
        "config_merged": merged, "config_path": str(home_cfg_path),
        "acl": acl, "startup_vbs": vbs_path,
    }
    return EXIT_OK, payload, f"deployed to {home} (version {sha})"


def _do_start() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    host, port = proxy_addr(cfg)
    already = proxy_health(host, port)
    if already:
        return EXIT_OK, {"already_running": True, "health": already}, "spillover proxy already running"

    supervisor = home / "app" / "supervisor.js"
    if not supervisor.is_file():
        return EXIT_UNREACHABLE, {}, f"supervisor.js is not deployed at {supervisor}; run `deploy` first"
    node = shutil.which("node")
    if not node:
        return EXIT_UNREACHABLE, {}, "node is not on PATH"
    try:
        spawn_detached([node, "--use-system-ca", str(supervisor)], cwd=str(supervisor.parent))
    except OSError as exc:
        return EXIT_UNREACHABLE, {}, f"failed to spawn supervisor: {exc}"

    # Cold node start, then the worker's synchronous lane-key fetch through python_exe: measured at 4-8 s
    # on this box, so a 5 s wait reported a healthy start as a failure.
    deadline = time.monotonic() + START_HEALTH_TIMEOUT_SEC
    health = None
    while time.monotonic() < deadline:
        health = proxy_health(host, port, timeout=0.5)
        if health:
            break
        time.sleep(0.2)
    if not health:
        return EXIT_UNREACHABLE, {}, (
            f"supervisor spawned but health check did not come up within {START_HEALTH_TIMEOUT_SEC:.0f}s; "
            "see state/logs/supervisor.log and proxy.log")
    return EXIT_OK, {"health": health}, "spillover proxy started"


def _do_stop() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    host, port = proxy_addr(cfg)
    state_dir = home / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    stop_file = state_dir / "supervisor.stop"
    atomic_write_text(stop_file, "")

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if proxy_health(host, port, timeout=0.5) is None:
            break
        time.sleep(0.25)

    pid_file = state_dir / "supervisor.pid"
    killed = None
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = None
        if pid:
            if IS_WINDOWS:
                try:
                    cp = run_cmd(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=10)
                    killed = cp.returncode == 0
                except (OSError, subprocess.SubprocessError):
                    killed = False
            else:
                try:
                    os.kill(pid, 15)
                    killed = True
                except OSError:
                    killed = False
    try:
        stop_file.unlink()
    except OSError:
        pass
    return EXIT_OK, {"killed_pid": killed}, "spillover proxy stopped"


def _do_status() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    host, port = proxy_addr(cfg)
    health = proxy_health(host, port, timeout=2.0)
    state = load_json_file(home / "state" / "state.json")
    return EXIT_OK, {"healthy": health is not None, "health": health, "state": state}, (
        "spillover proxy is healthy" if health else "spillover proxy is DOWN")


def _do_mode(mode: str) -> tuple[int, dict, str]:
    if mode not in VALID_MODES:
        return EXIT_USAGE, {}, f"mode must be one of {VALID_MODES}"
    home = home_dir()
    cfg_path = home / "config.json"
    cfg = load_home_config(home)
    if mode == "spill":
        doctor_result = run_doctor_checks(home, cfg)
        attestations = load_json_file(home / "state" / "attestations.json") or {}
        if not doctor_result["ok"]:
            return EXIT_REFUSED, {"doctor": doctor_result}, "refusing spill mode: doctor has failing checks"
        if not (isinstance(attestations, dict) and attestations.get("chatgpt_training_off")):
            return EXIT_REFUSED, {"doctor": doctor_result}, "refusing spill mode: missing chatgpt_training_off attestation"
    proxy_cfg = dict(cfg.get("proxy") or {})
    proxy_cfg["mode"] = mode
    cfg["proxy"] = proxy_cfg
    atomic_write_json(cfg_path, cfg)
    return EXIT_OK, {"mode": mode}, f"proxy.mode set to {mode}"


# --------------------------------------------------------------------------- #
# enable-routing / disable-routing / rollback
# --------------------------------------------------------------------------- #
def _pythonw_for(cfg: dict) -> str:
    python_exe = cfg.get("python_exe") or sys.executable
    if IS_WINDOWS:
        return str(Path(python_exe).with_name("pythonw.exe"))
    return python_exe


def _mirror_ide_settings(env_updates: dict) -> str | None:
    """Best-effort: apply the same env keys to the IDE settings file if (and only
    if) it already exists — never create one for a product that isn't installed."""
    path = ide_settings_path()
    if not path or not path.is_file():
        return None
    settings = load_json_file(path)
    if not isinstance(settings, dict):
        return None
    try:
        env = dict(settings.get("env") or {})
        env.update(env_updates)
        settings["env"] = env
        backup_file(path, "spillover")
        atomic_write_json(path, settings)
        return str(path)
    except OSError:
        return None


def _do_enable_routing(*, assume_yes: bool) -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    host, port = proxy_addr(cfg)
    health = proxy_health(host, port)
    if not health:
        return EXIT_REFUSED, {}, "refusing: spillover proxy is not healthy"

    version_check = check_claude_code_versions(cfg)
    if not version_check["ok"]:
        return EXIT_REFUSED, {"versions": version_check}, f"refusing: Claude Code version check failed: {version_check['bad']}"

    settings_path = claude_settings_path()
    settings = load_json_file(settings_path)
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        return EXIT_USAGE, {}, f"{settings_path} does not contain a JSON object"

    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    for key in CLAUDE_CREDENTIAL_KEYS:
        if key in env or key in settings:
            return EXIT_REFUSED, {}, f"refusing: {settings_path} already sets {key}"

    before = json.dumps(settings, indent=2, sort_keys=True)
    new_settings = json.loads(json.dumps(settings))  # deep copy via round-trip
    new_env = dict(new_settings.get("env") or {})

    # What each owned setting held before routing was first enabled, so `disable-routing --remove` can
    # put it back instead of deleting a value the operator had set. A re-run keeps the first record: by
    # then the live values are our own.
    owned_path = home / "state" / "owned_settings.json"
    prior_owned = load_json_file(owned_path)
    previous = prior_owned.get("previous") if isinstance(prior_owned, dict) else None
    if not isinstance(previous, dict):
        ide_path = ide_settings_path()
        ide_before = load_json_file(ide_path) if ide_path and ide_path.is_file() else None
        ide_env_before = ide_before.get("env") if isinstance(ide_before, dict) else None
        if not isinstance(ide_env_before, dict):
            ide_env_before = {}
        previous = {
            "env": {k: new_env[k] for k in OWNED_ENV_KEYS if k in new_env},
            "ide_env": {k: ide_env_before[k] for k in OWNED_ENV_KEYS if k in ide_env_before},
        }
        if "statusLine" in new_settings:
            previous["statusLine"] = new_settings["statusLine"]

    new_env["ANTHROPIC_BASE_URL"] = f"http://{host}:{port}"
    new_env["ENABLE_TOOL_SEARCH"] = True
    new_settings["env"] = new_env

    # Forward slashes, like every existing hook in ~/.claude/settings.json. machine_parity parses these
    # commands with shlex in posix mode, which would eat backslashes.
    pythonw = Path(_pythonw_for(cfg)).as_posix()
    statusline_py = (home / "bin" / "statusline.py").as_posix()
    ensure_py = (home / "bin" / "ensure_spillover.py").as_posix()
    new_settings["statusLine"] = {
        "type": "command",
        "command": f'"{pythonw}" "{statusline_py}"',
        "refreshInterval": 5,
    }

    hooks = dict(new_settings.get("hooks") or {})
    hook_entry = {
        "matcher": "",
        "hooks": [{"type": "command", "command": f'"{pythonw}" "{ensure_py}"'}],
    }
    # Replace, never stack: a re-run must not register the ensure hook a second time.
    session_start = [e for e in (hooks.get("SessionStart") or []) if not _is_spillover_hook(e)]
    session_start.append(hook_entry)
    hooks["SessionStart"] = session_start
    new_settings["hooks"] = hooks

    after = json.dumps(new_settings, indent=2, sort_keys=True)
    diff = "\n".join(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=str(settings_path), tofile=str(settings_path), lineterm=""))
    print(diff)

    if not assume_yes:
        if not _stdin_is_tty():
            return EXIT_REFUSED, {"diff": diff}, "refusing: non-interactive without --yes"
        reply = input("Apply these changes to Claude Code settings? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            return EXIT_REFUSED, {"diff": diff}, "aborted by operator"

    backup = backup_file(settings_path, "spillover")
    atomic_write_json(settings_path, new_settings)

    owned: dict[str, Any] = {
        "settings_path": str(settings_path),
        "backup_path": str(backup) if backup else None,
        "env_keys": list(OWNED_ENV_KEYS),
        "status_line": True,
        "session_start_hook": hook_entry,
        "previous": previous,
        "applied_at": _iso_now(),
    }
    ide_mirrored = _mirror_ide_settings({"ANTHROPIC_BASE_URL": f"http://{host}:{port}", "ENABLE_TOOL_SEARCH": True})
    if ide_mirrored:
        owned["ide_settings_path"] = ide_mirrored
        owned["ide_env_keys"] = list(OWNED_ENV_KEYS)

    atomic_write_json(owned_path, owned)
    return EXIT_OK, {"diff": diff, "owned": owned}, f"routing enabled via {settings_path}"


OWNED_ENV_KEYS = ("ANTHROPIC_BASE_URL", "ENABLE_TOOL_SEARCH")


def _is_spillover_hook(entry: Any) -> bool:
    """A SessionStart entry that runs our ensure hook, wherever HOME_DIR or the interpreter live."""
    if not isinstance(entry, dict):
        return False
    return any(isinstance(h, dict) and "ensure_spillover.py" in str(h.get("command", ""))
               for h in entry.get("hooks") or [])


def _restore_env(env: dict, keys: Any, previous_env: dict) -> list[str]:
    """Puts each owned env key back to its pre-enable value, or drops it if it had none."""
    touched = []
    for key in keys:
        if key in previous_env:
            env[key] = previous_env[key]
            touched.append(key)
        elif key in env:
            del env[key]
            touched.append(key)
    return touched


def _do_disable_routing(*, remove: bool) -> tuple[int, dict, str]:
    settings_path = claude_settings_path()
    settings = load_json_file(settings_path)
    if not isinstance(settings, dict):
        return EXIT_USAGE, {}, f"{settings_path} not found or unreadable"

    env = dict(settings.get("env") or {})
    env["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com"
    settings["env"] = env
    backup = backup_file(settings_path, "spillover-disable")
    atomic_write_json(settings_path, settings)

    removed: list[str] = []
    if remove:
        home = home_dir()
        owned_path = home / "state" / "owned_settings.json"
        owned = load_json_file(owned_path)
        if isinstance(owned, dict):
            previous = owned.get("previous") if isinstance(owned.get("previous"), dict) else {}
            settings2 = load_json_file(settings_path) or {}
            env2 = dict(settings2.get("env") or {})
            removed += _restore_env(env2, owned.get("env_keys", []), previous.get("env") or {})
            settings2["env"] = env2
            if owned.get("status_line"):
                if "statusLine" in previous:
                    settings2["statusLine"] = previous["statusLine"]
                    removed.append("statusLine")
                elif "statusLine" in settings2:
                    del settings2["statusLine"]
                    removed.append("statusLine")
            owned_hook = owned.get("session_start_hook")
            if isinstance(settings2.get("hooks"), dict):
                arr = settings2["hooks"].get("SessionStart")
                if isinstance(arr, list):
                    kept = [e for e in arr if e != owned_hook and not _is_spillover_hook(e)]
                    if len(kept) != len(arr):
                        settings2["hooks"]["SessionStart"] = kept
                        removed.append("SessionStart hook")
            atomic_write_json(settings_path, settings2)

            ide_path_raw = owned.get("ide_settings_path")
            if ide_path_raw:
                ide_path = Path(ide_path_raw)
                ide_settings = load_json_file(ide_path)
                if isinstance(ide_settings, dict):
                    ide_env = dict(ide_settings.get("env") or {})
                    _restore_env(ide_env, owned.get("ide_env_keys", []), previous.get("ide_env") or {})
                    ide_settings["env"] = ide_env
                    atomic_write_json(ide_path, ide_settings)
                    removed.append("ide settings")
            # Fully undone: the next enable-routing must record the operator's values afresh.
            owned_path.unlink(missing_ok=True)

    return EXIT_OK, {"removed": removed, "backup": str(backup) if backup else None}, (
        "routing disabled" + (" and owned keys removed" if remove else ""))


def _do_rollback(*, all_: bool) -> tuple[int, dict, str]:
    steps = []
    code1, _payload1, msg1 = _do_disable_routing(remove=all_)
    steps.append({"step": "disable-routing", "code": code1, "detail": msg1})

    advice = "restart open Claude sessions"
    print(advice)
    steps.append({"step": "advise", "detail": advice})

    code2, _payload2, msg2 = _do_stop()
    steps.append({"step": "stop-supervisor", "code": code2, "detail": msg2})

    vbs = startup_vbs_path()
    removed_vbs = False
    if vbs.is_file():
        try:
            vbs.unlink()
            removed_vbs = True
        except OSError:
            pass
    steps.append({"step": "remove-startup-vbs", "removed": removed_vbs})

    overall = code1 if code1 != EXIT_OK else EXIT_OK
    return overall, {"steps": steps}, "rollback complete"


# --------------------------------------------------------------------------- #
# key set / key check
# --------------------------------------------------------------------------- #
def _do_key_set() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    python_exe = cfg.get("python_exe") or sys.executable
    try:
        cp = run_interactive([python_exe, str(lane_key_script(home)), "set", "omniroute_lane"], timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return EXIT_UNREACHABLE, {}, f"lane_key.py set failed: {exc}"
    except subprocess.TimeoutExpired:
        return EXIT_UNREACHABLE, {}, "lane_key.py set timed out"
    if cp.returncode != 0:
        return EXIT_UNREACHABLE, {}, f"lane_key.py set exited {cp.returncode}"
    return EXIT_OK, {}, "omniroute_lane stored"


def _do_key_check() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    python_exe = cfg.get("python_exe") or sys.executable
    stored = lane_key_exists(python_exe, "omniroute_lane", home)
    if not stored:
        return EXIT_UNREACHABLE, {"stored": False, "accepted": False, "models": []}, "omniroute_lane secret is not stored"
    value = lane_key_get(python_exe, "omniroute_lane", home)
    if value is None:
        return EXIT_UNREACHABLE, {"stored": True, "accepted": False, "models": []}, "failed to read omniroute_lane secret"
    base = omniroute_base(cfg)
    try:
        status, parsed, _ = http_call(f"{base}/v1/models", headers={"Authorization": f"Bearer {value}"}, timeout=10)
    except ApiUnreachable as exc:
        return EXIT_UNREACHABLE, {"stored": True, "accepted": False, "models": []}, f"OmniRoute unreachable: {exc}"
    finally:
        value = None  # noqa: F841 - never logged
    accepted = status == 200
    models: list[str] = []
    if accepted and isinstance(parsed, dict):
        models = [m.get("id") for m in (parsed.get("data") or []) if isinstance(m, dict) and m.get("id")]
    code = EXIT_OK if accepted else EXIT_UNREACHABLE
    msg = f"lane key accepted, {len(models)} model(s)" if accepted else f"lane key rejected (status {status})"
    return code, {"stored": True, "accepted": accepted, "models": models}, msg


def _do_secrets_init() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    python_exe = cfg.get("python_exe") or sys.executable
    results: dict[str, str] = {}
    for name, nbytes in SECRET_SPECS:
        if lane_key_exists(python_exe, name, home):
            results[name] = "already-present"
            continue
        ok, detail = lane_key_generate(python_exe, name, home, nbytes=nbytes)
        results[name] = "generated" if ok else f"error: {detail}"
    failed = [k for k, v in results.items() if v.startswith("error")]
    code = EXIT_OK if not failed else EXIT_UNREACHABLE
    msg = "all secrets present" if not failed else f"failed to generate: {failed}"
    return code, {"secrets": results}, msg


# --------------------------------------------------------------------------- #
# omniroute setup / connect codex / connect-key
# --------------------------------------------------------------------------- #
def _do_setup(models_main: list[str] | None, models_fast: list[str] | None) -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    session, err = admin_session(cfg, home)
    if session is None:
        return EXIT_UNREACHABLE, {}, err or "could not establish an admin session"

    forbidden_prefixes = tuple(((cfg.get("omniroute") or {}) if isinstance(cfg.get("omniroute"), dict) else {})
                                .get("forbidden_model_prefixes") or [])

    try:
        status, parsed, _ = session.get("/api/providers")
    except ApiUnreachable as exc:
        return EXIT_UNREACHABLE, {}, f"could not list providers: {exc}"
    if status != 200 or not isinstance(parsed, dict):
        return EXIT_UNREACHABLE, {}, f"could not list providers (status {status})"
    connections = parsed.get("connections")
    if not isinstance(connections, list):
        connections = parsed.get("providers") if isinstance(parsed.get("providers"), list) else []

    disabled = []
    forbidden_hits: list[str] = []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        provider = str(conn.get("provider") or "")
        cid = conn.get("id")
        is_active = conn.get("isActive", True)
        if provider in ("opencode", "oc") and is_active and cid:
            st, _p, _r = session.patch(f"/api/providers/{cid}", {"isActive": False})
            disabled.append({"provider": provider, "id": cid, "ok": st in (200, 204)})
        elif is_active and any((provider + "/").startswith(p) for p in forbidden_prefixes):
            # forbidden_model_prefixes are model-id prefixes ("groq/", "gemini-cli/", ...);
            # a connected provider is forbidden when ANY model it would list is forbidden,
            # i.e. its own "<provider>/" namespace falls under a forbidden prefix.
            forbidden_hits.append(provider)

    try:
        cstatus, cparsed, _ = session.get("/api/combos")
    except ApiUnreachable as exc:
        return EXIT_UNREACHABLE, {}, f"could not list combos: {exc}"
    combos = (cparsed or {}).get("combos") if isinstance(cparsed, dict) else None
    combos = combos if isinstance(combos, list) else []

    auto = next((c for c in combos if isinstance(c, dict) and c.get("name") == "auto"), None)
    auto_disabled = False
    if auto and auto.get("isActive", True) and auto.get("id"):
        st, _p, _r = session.patch(f"/api/combos/{auto['id']}", {"isActive": False})
        auto_disabled = st in (200, 204)

    for combo in combos:
        if not isinstance(combo, dict):
            continue
        for m in combo.get("models") or []:
            model_id = m.get("model") if isinstance(m, dict) else m
            if model_id and any(str(model_id).startswith(p) for p in forbidden_prefixes):
                forbidden_hits.append(str(model_id))

    if forbidden_hits:
        return EXIT_UNREACHABLE, {"forbidden": sorted(set(forbidden_hits))}, \
            f"forbidden provider/model connected or in a combo: {sorted(set(forbidden_hits))}"

    def upsert_combo(name: str, models: list[str]) -> tuple[bool, dict | None]:
        body = {
            "name": name,
            "strategy": "priority",
            "models": [{"model": m, "priority": i + 1} for i, m in enumerate(models)],
            "config": {"compressionMode": "off"},
        }
        existing = next((c for c in combos if isinstance(c, dict) and c.get("name") == name), None)
        if existing and existing.get("id"):
            st, p2, _r = session.patch(f"/api/combos/{existing['id']}", body)
        else:
            st, p2, _r = session.post("/api/combos", body)
        return st in (200, 201), p2 if isinstance(p2, dict) else None

    main_ok, _ = upsert_combo(COMBO_MAIN, models_main or DEFAULT_MODELS_MAIN)
    fast_ok, _ = upsert_combo(COMBO_FAST, models_fast or DEFAULT_MODELS_FAST)
    if not (main_ok and fast_ok):
        return EXIT_UNREACHABLE, {}, "failed to create/update bravo-fallback combos"

    key_body = {"name": "bravo-omniroute-lane", "scopes": [], "allowedCombos": [COMBO_MAIN, COMBO_FAST]}
    st, parsed2, _r = session.post("/api/keys", key_body)
    if st != 201 or not isinstance(parsed2, dict) or not parsed2.get("key"):
        return EXIT_UNREACHABLE, {}, f"failed to create the scoped lane key (status {st})"
    key_id = parsed2.get("id")
    key_value = parsed2["key"]
    parsed2 = None  # noqa: F841 - drop the reference carrying the raw key

    st2, _p2, _r2 = session.patch(f"/api/keys/{key_id}", {
        "allowedEndpoints": ["/v1/messages", "/v1/messages/count_tokens", "/v1/models"],
        "compressionEnabled": False,
    })
    if st2 not in (200, 204):
        key_value = None
        return EXIT_UNREACHABLE, {}, "lane key created but failed to scope its endpoints"

    python_exe = cfg.get("python_exe") or sys.executable
    stored = lane_key_set_stdin(python_exe, "omniroute_lane", home, key_value)
    key_value = None
    if not stored:
        return EXIT_UNREACHABLE, {}, "lane key created in OmniRoute but failed to store it locally"

    return EXIT_OK, {
        "combos": [COMBO_MAIN, COMBO_FAST], "disabled_providers": disabled, "auto_combo_disabled": auto_disabled,
    }, "omniroute setup complete"


def _do_connect_codex() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    session, err = admin_session(cfg, home)
    if session is None:
        return EXIT_UNREACHABLE, {}, err or "could not establish an admin session"

    try:
        status, parsed, _ = http_call(f"{CODEX_API_BASE}/deviceauth/usercode", method="POST",
                                       json_body={"client_id": CODEX_CLIENT_ID}, timeout=20)
    except ApiUnreachable as exc:
        return EXIT_UNREACHABLE, {}, f"could not reach OpenAI: {exc}"
    if status == 404:
        return EXIT_UNREACHABLE, {}, "device code login is not enabled for this OpenAI account/workspace"
    if status != 200 or not isinstance(parsed, dict):
        return EXIT_UNREACHABLE, {}, f"failed to request a device code (status {status})"
    device_auth_id = parsed.get("device_auth_id")
    user_code = parsed.get("user_code") or parsed.get("usercode")
    interval = parsed.get("interval")
    interval_sec = interval if isinstance(interval, (int, float)) and interval > 0 else 5
    if not device_auth_id or not user_code:
        return EXIT_UNREACHABLE, {}, "device code response is missing device_auth_id/user_code"

    # flush: the operator needs this line while the poll below runs, and a piped stdout is block-buffered.
    print(f"Open {CODEX_VERIFICATION_URI} and enter this code: {user_code}", flush=True)

    deadline = time.monotonic() + min(CODEX_POLL_DEADLINE_SEC, CODEX_POLL_TIMEOUT_SEC)
    auth_code = None
    code_verifier = None
    while time.monotonic() < deadline:
        time.sleep(interval_sec)
        try:
            st2, parsed2, _ = http_call(f"{CODEX_API_BASE}/deviceauth/token", method="POST",
                                         json_body={"device_auth_id": device_auth_id, "user_code": user_code},
                                         timeout=20)
        except ApiUnreachable:
            continue
        if st2 == 200 and isinstance(parsed2, dict) and parsed2.get("authorization_code"):
            auth_code = parsed2["authorization_code"]
            code_verifier = parsed2.get("code_verifier")
            break
        if st2 in (403, 404):
            continue
        return EXIT_UNREACHABLE, {}, f"polling for authorization failed (status {st2})"
    if not auth_code:
        return EXIT_UNREACHABLE, {}, "authorization timed out"

    form = urllib.parse.urlencode({
        "grant_type": "authorization_code", "client_id": CODEX_CLIENT_ID,
        "code": auth_code, "code_verifier": code_verifier, "redirect_uri": CODEX_REDIRECT_URI,
    }).encode("utf-8")
    try:
        st3, parsed3, _ = http_call(f"{CODEX_BASE}/oauth/token", method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                                     raw_body=form, timeout=20)
    except ApiUnreachable as exc:
        return EXIT_UNREACHABLE, {}, f"token exchange failed: {exc}"
    if st3 != 200 or not isinstance(parsed3, dict) or not parsed3.get("access_token"):
        return EXIT_UNREACHABLE, {}, f"token exchange failed (status {st3})"

    device_complete_body = {
        "access_token": parsed3.get("access_token"),
        "refresh_token": parsed3.get("refresh_token"),
        "id_token": parsed3.get("id_token"),
        "expires_in": parsed3.get("expires_in"),
    }
    parsed3 = None  # noqa: F841 - drop the reference carrying raw tokens
    st4, parsed4, _ = session.post("/api/oauth/codex/device-complete", device_complete_body)
    device_complete_body = None
    if st4 != 200 or not isinstance(parsed4, dict) or not parsed4.get("success"):
        return EXIT_UNREACHABLE, {}, f"failed to persist the Codex connection (status {st4})"
    conn = parsed4.get("connection") or {}
    return EXIT_OK, {"connection": conn}, f"codex connected: {conn.get('email') or conn.get('id')}"


# The .env.agents names `connect-key --from-env-agents` reads (override with --env-name), and the
# substrings used to point at a differently spelled name when the default is absent.
CONNECT_KEY_ENV_NAMES = {"cerebras": "CEREBRAS_API_KEY", "zai": "ZAI_API_KEY"}
CONNECT_KEY_NAME_HINTS = {"cerebras": ("CEREBRAS",), "zai": ("ZAI", "ZHIPU", "BIGMODEL")}


def _secret_loader_module():
    """lib.secret_loader, bound to the checkout that actually holds .env.agents.

    The file is gitignored, so a linked git worktree has none. There, the main checkout's own loader is
    used: the same audited code path, logging to that checkout's state/. This never opens the file itself.
    """
    from lib import secret_loader  # scripts/ is on sys.path
    if secret_loader.ENV_FILE.is_file():
        return secret_loader
    try:
        cp = run_cmd(["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"], timeout=10)
        common = Path(cp.stdout.strip()) if cp.returncode == 0 and cp.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        common = None
    main = common.parent if common is not None and common.name == ".git" else None
    if main is None or main.resolve() == REPO.resolve():
        return secret_loader
    candidate = main / "scripts" / "lib" / "secret_loader.py"
    if not candidate.is_file():
        return secret_loader
    import importlib.util
    spec = importlib.util.spec_from_file_location("bravo_main_checkout_secret_loader", candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _do_connect_key(provider_arg: str, *, from_env_agents: bool = False,
                    env_name: str | None = None) -> tuple[int, dict, str]:
    if provider_arg not in CONNECT_KEY_PROVIDERS:
        return EXIT_USAGE, {}, f"unknown provider {provider_arg!r}; choose one of {sorted(CONNECT_KEY_PROVIDERS)}"
    provider_id = CONNECT_KEY_PROVIDERS[provider_arg]

    key_value = None
    if from_env_agents:
        # From .env.agents straight into the request body: the value is never printed, logged or returned.
        name = env_name or CONNECT_KEY_ENV_NAMES[provider_arg]
        try:
            loader = _secret_loader_module()
            key_value = loader.get(name) or ""
            if not key_value:
                tokens = CONNECT_KEY_NAME_HINTS[provider_arg]
                similar = sorted(k for k in loader.load_env() if k != name and any(t in k.upper() for t in tokens))
            else:
                similar = []
        except Exception as exc:  # noqa: BLE001 -- SecretLoaderRefused, OSError, a malformed file
            return EXIT_USAGE, {"env_name": name}, f"could not load .env.agents: {type(exc).__name__}"
        if not key_value:
            hint = f"; similar names present: {', '.join(similar)} (pass one with --env-name)" if similar else ""
            return EXIT_USAGE, {"env_name": name, "similar_names": similar}, f"{name} is not set in .env.agents{hint}"

    home = home_dir()
    cfg = load_home_config(home)
    session, err = admin_session(cfg, home)
    if session is None:
        return EXIT_UNREACHABLE, {}, err or "could not establish an admin session"

    if key_value is None:
        if not _stdin_is_tty():
            return EXIT_USAGE, {}, "refusing to read an API key from a non-interactive stdin (use --from-env-agents)"
        key_value = getpass.getpass(f"{provider_arg} API key (hidden): ")
        if not key_value:
            return EXIT_USAGE, {}, "empty API key, nothing stored"

    body = {"provider": provider_id, "name": f"bravo-{provider_arg}", "apiKey": key_value}
    key_value = None
    try:
        st, parsed, _ = session.post("/api/providers", body)
    except ApiUnreachable as exc:
        return EXIT_UNREACHABLE, {}, f"could not reach OmniRoute: {exc}"
    finally:
        body["apiKey"] = None
    if st not in (200, 201) or not isinstance(parsed, dict):
        return EXIT_UNREACHABLE, {}, f"failed to create the {provider_arg} connection (status {st})"
    return EXIT_OK, {"id": parsed.get("id"), "provider": provider_id}, f"{provider_arg} connected (id {parsed.get('id')})"


# --------------------------------------------------------------------------- #
# smoke
# --------------------------------------------------------------------------- #
def _smoke_headers(lane_key: str, route_model: str) -> dict:
    return {
        "Authorization": f"Bearer {lane_key}",
        "x-route-model": route_model,
        "x-omniroute-compression": "off",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _assert_tool_name_case(parsed: Any) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "response was not JSON"
    for block in parsed.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name")
            return name == "Get_Weather", f"tool_use name={name!r}"
    return True, "no tool_use block in response (nothing to check)"


def _assert_sse_order(raw: bytes) -> tuple[bool, str]:
    text = raw.decode("utf-8", errors="replace")
    events = [ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.lower().startswith("event:")]
    ok = bool(events) and events[0] == "message_start" and events[-1] == "message_stop"
    return ok, f"order={events[:8]}"


def _do_smoke(model: str | None, want_tools: bool, want_stream: bool, corpus_dir: str | None) -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    python_exe = cfg.get("python_exe") or sys.executable
    lane_key = lane_key_get(python_exe, "omniroute_lane", home)
    if not lane_key:
        return EXIT_UNREACHABLE, {}, "omniroute_lane secret is not stored"
    base = omniroute_base(cfg)
    route_model = model or ((cfg.get("proxy") or {}) if isinstance(cfg.get("proxy"), dict) else {}).get(
        "route_model_main") or COMBO_MAIN

    cases: list[dict] = []

    def run_case(name: str, body: dict, *, raw_check: Callable[[bytes], tuple[bool, str]] | None = None,
                 json_check: Callable[[Any], tuple[bool, str]] | None = None) -> None:
        try:
            status, parsed, raw = http_call(f"{base}/v1/messages", method="POST",
                                             headers=_smoke_headers(lane_key, route_model),
                                             json_body=body, timeout=60)
        except ApiUnreachable as exc:
            cases.append({"name": name, "ok": False, "detail": f"unreachable: {exc}"})
            return
        ok = status == 200
        detail = f"status {status}"
        if ok and raw_check:
            ok, detail = raw_check(raw)
        elif ok and json_check:
            ok, detail = json_check(parsed)
        cases.append({"name": name, "ok": ok, "detail": detail})

    run_case("plain-text", {"model": route_model, "max_tokens": 64,
                             "messages": [{"role": "user", "content": "Say OK."}]})

    if want_tools:
        tool = {
            "name": "Get_Weather", "description": "Get the current weather for a city.",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        }
        run_case("tool-round-trip", {"model": route_model, "max_tokens": 200, "tools": [tool],
                  "messages": [{"role": "user", "content": "What's the weather in Miami? Use the tool."}]})
        run_case("parallel-tool-calls", {"model": route_model, "max_tokens": 200, "tools": [tool],
                  "messages": [{"role": "user", "content": "Weather in Miami and Austin? Use the tool for both, in parallel."}]})
        run_case("tool-name-case", {"model": route_model, "max_tokens": 200, "tools": [tool],
                  "messages": [{"role": "user", "content": "What's the weather in Denver? Use the tool."}]},
                 json_check=_assert_tool_name_case)

    if want_stream:
        run_case("sse-order", {"model": route_model, "max_tokens": 64, "stream": True,
                  "messages": [{"role": "user", "content": "count to three"}]}, raw_check=_assert_sse_order)

    run_case("signed-thinking-history", {"model": route_model, "max_tokens": 64, "messages": [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "reasoning...", "signature": "sig-abc"}]},
        {"role": "user", "content": "continue"},
    ]})

    if corpus_dir:
        cdir = Path(corpus_dir)
        files = sorted(cdir.glob("*.json")) if cdir.is_dir() else []
        if not files:
            cases.append({"name": "corpus", "ok": False, "detail": f"no *.json files under {corpus_dir}"})
        for f in files:
            try:
                body = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                cases.append({"name": f.name, "ok": False, "detail": f"unreadable: {exc}"})
                continue
            run_case(f.name, body)

    lane_key = None
    ok = bool(cases) and all(c["ok"] for c in cases)
    return (EXIT_OK if ok else EXIT_CHECK_FAILED), {"cases": cases}, ("smoke passed" if ok else "smoke FAILED")


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def _check_listen_loopback_only(port: int) -> tuple[bool, str]:
    if not IS_WINDOWS:
        return True, "not Windows; skipped"
    ps = f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalAddress"
    try:
        cp = run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"probe failed: {exc}"
    addrs = [ln.strip() for ln in (cp.stdout or "").splitlines() if ln.strip()]
    if not addrs:
        return False, "port not listening"
    bad = [a for a in addrs if a not in ("127.0.0.1", "::1")]
    return (not bad), f"listening on {addrs}"


def _check_no_tunnel_process() -> tuple[bool, str]:
    if not IS_WINDOWS:
        return True, "not Windows; skipped"
    ps = ("Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
          "Where-Object { $_.CommandLine -match 'omniroute-src' } | "
          "Select-Object -ExpandProperty CommandLine")
    try:
        cp = run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"probe failed, treated as pass: {exc}"
    lines = (cp.stdout or "").lower()
    hits = [name for name in ("cloudflared", "ngrok", "tailscale") if name in lines]
    return (not hits), (f"found: {hits}" if hits else "none found")


def _read_next_version(runtime_dir: Path) -> str | None:
    for rel in ("dist/node_modules/next/package.json", "node_modules/next/package.json"):
        p = runtime_dir / rel
        if p.is_file():
            data = load_json_file(p)
            if isinstance(data, dict) and isinstance(data.get("version"), str):
                return data["version"]
    return None


def _check_next_version(runtime_dir: Path, min_next: str) -> tuple[bool, str]:
    v = _read_next_version(runtime_dir)
    if not v:
        return False, f"next package.json not found under {runtime_dir}"
    return version_tuple(v) >= version_tuple(min_next), f"found {v}, need >= {min_next}"


def _read_runtime_version(runtime_dir: Path) -> str | None:
    data = load_json_file(runtime_dir / "package.json")
    return data.get("version") if isinstance(data, dict) else None


def _check_dotenv_secrets(home: Path, cfg: dict) -> tuple[bool, str]:
    omni_cfg = cfg.get("omniroute") if isinstance(cfg.get("omniroute"), dict) else {}
    data_dir = Path(omni_cfg.get("data_dir") or (home / "omniroute-data"))
    env_path = data_dir / ".env"
    if not env_path.is_file():
        return True, "no .env file present"
    try:
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return False, f"cannot read .env: {exc}"
    bad_names = []
    for ln in lines:
        if "=" not in ln or ln.strip().startswith("#"):
            continue
        k, _, v = ln.partition("=")
        k = k.strip()
        if k == "STORAGE_ENCRYPTION_KEY":
            bad_names.append(k)
        elif k == "INITIAL_PASSWORD" and v.strip().strip('"').strip("'") == "CHANGEME":
            bad_names.append(k)
    return (not bad_names), (f"flagged key names: {bad_names}" if bad_names else "clean")


def _check_log_env(omni_cfg: dict) -> tuple[bool, str]:
    log_env = omni_cfg.get("log_env") if isinstance(omni_cfg.get("log_env"), dict) else {}
    present = sorted(log_env.keys())
    missing = sorted(k for k in DEFAULT_OMNIROUTE_LOG_ENV if k not in log_env)
    detail = f"present={present}" + (f" missing={missing}" if missing else "")
    return (not missing), detail


def _check_forbidden_providers(session: OmniRouteAdmin, omni_cfg: dict) -> tuple[bool, str]:
    prefixes = tuple(omni_cfg.get("forbidden_model_prefixes") or [])
    try:
        status, parsed, _ = session.get("/api/providers")
    except ApiUnreachable as exc:
        return False, f"unreachable: {exc}"
    if status != 200 or not isinstance(parsed, dict):
        return False, f"status {status}"
    conns = parsed.get("connections")
    if not isinstance(conns, list):
        conns = parsed.get("providers") if isinstance(parsed.get("providers"), list) else []
    hits = [c.get("provider") for c in conns if isinstance(c, dict) and c.get("isActive", True)
            and any((str(c.get("provider", "")) + "/").startswith(p) for p in prefixes)]
    return (not hits), (f"active forbidden providers: {hits}" if hits else "none")


def _check_owned_settings_unchanged(home: Path) -> tuple[bool, str]:
    owned = load_json_file(home / "state" / "owned_settings.json")
    if not isinstance(owned, dict):
        return True, "no owned settings recorded yet"
    settings = load_json_file(Path(owned.get("settings_path") or str(claude_settings_path())))
    if not isinstance(settings, dict):
        return False, "settings file missing or unreadable"
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    missing = [k for k in owned.get("env_keys", []) if k not in env]
    if owned.get("status_line") and "statusLine" not in settings:
        missing.append("statusLine")
    hook_entry = owned.get("session_start_hook")
    if hook_entry:
        arr = (settings.get("hooks") or {}).get("SessionStart") if isinstance(settings.get("hooks"), dict) else None
        if not (isinstance(arr, list) and hook_entry in arr):
            missing.append("SessionStart hook")
    return (not missing), (f"missing: {missing}" if missing else "unchanged")


def run_doctor_checks(home: Path, cfg: dict) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail if isinstance(detail, str) else str(detail)})

    proxy_cfg = cfg.get("proxy") if isinstance(cfg.get("proxy"), dict) else {}
    omni_cfg = cfg.get("omniroute") if isinstance(cfg.get("omniroute"), dict) else {}
    host, port = proxy_addr(cfg)
    base = omniroute_base(cfg)
    omni_port = urllib.parse.urlsplit(base).port or 20128

    add("omniroute listens only on 127.0.0.1", *_check_listen_loopback_only(omni_port))

    try:
        status, _parsed, _raw = http_call(f"{base}/v1/models", timeout=10)
        add("unauthenticated /v1/models returns 401", status == 401, f"status {status}")
    except ApiUnreachable as exc:
        add("unauthenticated /v1/models returns 401", False, f"unreachable: {exc}")

    runtime_dir = resolve_runtime_dir(home, cfg)
    add("bundled next >= min_next", *_check_next_version(runtime_dir, omni_cfg.get("min_next") or "16.3.3"))

    version = _read_runtime_version(runtime_dir)
    deny_versions = set(omni_cfg.get("deny_versions") or [])
    patched = bool(omni_cfg.get("next_patched"))
    denied = bool(version) and version in deny_versions and not patched
    add("runtime version not denied", not denied, f"version={version}")

    add("no STORAGE_ENCRYPTION_KEY/INITIAL_PASSWORD=CHANGEME leaked in DATA_DIR/.env",
        *_check_dotenv_secrets(home, cfg))

    add("omniroute log_env configured", *_check_log_env(omni_cfg))

    try:
        status, parsed, _raw = http_call(f"{base}/api/settings/require-login", timeout=10)
        require_login = isinstance(parsed, dict) and parsed.get("requireLogin") is True
        add("requireLogin is true", status == 200 and require_login, f"status {status} body={parsed}")
    except ApiUnreachable as exc:
        add("requireLogin is true", False, f"unreachable: {exc}")

    add("no cloudflared/ngrok/tailscale under the OmniRoute tree", *_check_no_tunnel_process())

    # OmniRoute has no Host allowlist: its unauthenticated status routes (require-login, auth/status)
    # answer any Host. What a DNS-rebinding page must never reach is a route that reads or changes
    # state, so an API route and a management route must both refuse it (live 2026-09-13: both 401).
    for probe_method, probe_path in (("POST", "/v1/messages"), ("GET", "/api/providers")):
        name = f"rebinding Host/Origin probe refused on {probe_method} {probe_path}"
        try:
            status, _p, _r = http_call(f"{base}{probe_path}", method=probe_method,
                                        headers={"Host": "evil.example", "Origin": "http://evil.example"},
                                        json_body={} if probe_method == "POST" else None, timeout=10)
            add(name, status in (401, 403, 421), f"status {status}")
        except ApiUnreachable as exc:
            add(name, False, f"unreachable: {exc}")

    for path, method in (("/api/system/version", "POST"), ("/api/settings/mitm", "POST"),
                          ("/api/settings/require-login", "POST")):
        try:
            status, _p, _r = http_call(f"{base}{path}", method=method, json_body={}, timeout=10)
            add(f"{method} {path} refused without auth", status in (401, 403), f"status {status}")
        except ApiUnreachable as exc:
            add(f"{method} {path} refused without auth", False, f"unreachable: {exc}")

    session, _err = admin_session(cfg, home)
    if session is not None:
        add("forbidden providers absent", *_check_forbidden_providers(session, omni_cfg))
    else:
        add("forbidden providers absent", True, "not checked (no admin session available)")

    health = proxy_health(host, port, timeout=3)
    add("proxy health", health is not None, health if health else "unreachable")

    vc = check_claude_code_versions(cfg)
    add("Claude Code versions ok", vc["ok"], vc)

    add("owned settings keys unchanged", *_check_owned_settings_unchanged(home))

    settings = load_json_file(claude_settings_path()) or {}
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    cred_present = [k for k in CLAUDE_CREDENTIAL_KEYS if k in env or k in settings]
    add("no user-level Anthropic credential vars", not cred_present, cred_present)

    attestations = load_json_file(home / "state" / "attestations.json") or {}
    add("chatgpt_training_off attestation present",
        isinstance(attestations, dict) and bool(attestations.get("chatgpt_training_off")), attestations)

    ok_all = all(c["ok"] for c in checks)
    return {"ok": ok_all, "checks": checks}


# --------------------------------------------------------------------------- #
# install --verify
# --------------------------------------------------------------------------- #
def _do_install_verify() -> tuple[int, dict, str]:
    home = home_dir()
    cfg = load_home_config(home)
    runtime_dir = resolve_runtime_dir(home, cfg)
    omni_cfg = cfg.get("omniroute") if isinstance(cfg.get("omniroute"), dict) else {}
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail if isinstance(detail, str) else str(detail)})

    omniroute_mjs = runtime_dir / "bin" / "omniroute.mjs"
    server_js = runtime_dir / "dist" / "server.js"
    add("bin/omniroute.mjs present", omniroute_mjs.is_file(), str(omniroute_mjs))
    add("dist/server.js present", server_js.is_file(), str(server_js))

    version = _read_runtime_version(runtime_dir)
    add("runtime version readable", bool(version), version or "unknown")

    git_sha_cfg = omni_cfg.get("git_sha")
    if (runtime_dir / ".git").exists():
        head = None
        try:
            cp = run_cmd(["git", "-C", str(runtime_dir), "rev-parse", "HEAD"], timeout=15)
            if cp.returncode == 0:
                head = cp.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            head = None
        sha_ok = bool(head) and bool(git_sha_cfg) and (head == git_sha_cfg or git_sha_cfg.startswith(head) or head.startswith(git_sha_cfg[:12]))
        add("HEAD matches config git_sha", sha_ok, f"HEAD={head} expected={git_sha_cfg}")
    else:
        add("HEAD matches config git_sha", True, "not a git checkout; skipped")

    add("bundled next >= min_next", *_check_next_version(runtime_dir, omni_cfg.get("min_next") or "16.3.3"))

    node = shutil.which("node")
    if not node:
        add("native modules resolve (better-sqlite3)", False, "node not on PATH")
    else:
        dist_dir = runtime_dir / "dist"
        if not dist_dir.is_dir():
            add("native modules resolve (better-sqlite3)", False, f"{dist_dir} not found")
        else:
            try:
                cp = run_cmd([node, "-e", "require('better-sqlite3')"], cwd=str(dist_dir), timeout=30)
                ok = cp.returncode == 0
                add("native modules resolve (better-sqlite3)", ok,
                    "resolved" if ok else (cp.stderr or cp.stdout or "").strip()[:300])
            except (OSError, subprocess.SubprocessError) as exc:
                add("native modules resolve (better-sqlite3)", False, str(exc))

    ok_all = all(c["ok"] for c in checks)
    return (EXIT_OK if ok_all else EXIT_CHECK_FAILED), {"checks": checks}, (
        "install verified" if ok_all else "install verification FAILED")


# --------------------------------------------------------------------------- #
# attest / deny-repo / fault / events / uninstall
# --------------------------------------------------------------------------- #
def _do_attest() -> tuple[int, dict, str]:
    if not _stdin_is_tty():
        return EXIT_USAGE, {}, "refusing: attestation requires an interactive terminal"
    reply = input("Confirm ChatGPT/OpenAI training has been disabled for this account [y/N]: ").strip().lower()
    if reply not in ("y", "yes"):
        return EXIT_REFUSED, {}, "attestation declined"
    home = home_dir()
    path = home / "state" / "attestations.json"
    data = load_json_file(path)
    if not isinstance(data, dict):
        data = {}
    data["chatgpt_training_off"] = {"attested": True, "at": _iso_now()}
    atomic_write_json(path, data)
    return EXIT_OK, data, "attestation recorded"


def _do_deny_repo(repo_path: str) -> tuple[int, dict, str]:
    target = Path(repo_path) / ".claude" / "settings.local.json"
    settings = load_json_file(target)
    if not isinstance(settings, dict):
        settings = {}
    env = dict(settings.get("env") or {})
    header = "X-Bravo-Spill: deny"
    existing = env.get("ANTHROPIC_CUSTOM_HEADERS") or ""
    if header not in existing:
        env["ANTHROPIC_CUSTOM_HEADERS"] = f"{existing}, {header}" if existing else header
    settings["env"] = env
    backup = backup_file(target, "spillover-deny") if target.is_file() else None
    atomic_write_json(target, settings)
    return EXIT_OK, {"path": str(target), "backup": str(backup) if backup else None}, f"denied spillover for {repo_path}"


def _do_fault_set(mode: str, ttl_sec: int) -> tuple[int, dict, str]:
    if mode not in FAULT_MODES:
        return EXIT_USAGE, {}, f"mode must be one of {FAULT_MODES}"
    if ttl_sec <= 0:
        return EXIT_USAGE, {}, "--ttl must be a positive number of seconds"
    if not _stdin_is_tty():
        return EXIT_REFUSED, {}, "refusing: fault injection requires an interactive TTY confirmation"
    reply = input(f"Inject fault {mode!r} for {ttl_sec}s? [y/N]: ").strip().lower()
    if reply not in ("y", "yes"):
        return EXIT_REFUSED, {}, "fault injection aborted by operator"

    home = home_dir()
    cfg_path = home / "config.json"
    cfg = load_home_config(home)
    proxy_cfg = dict(cfg.get("proxy") or {})
    proxy_cfg["allow_fault_injection"] = True
    cfg["proxy"] = proxy_cfg
    atomic_write_json(cfg_path, cfg)

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat(timespec="seconds")
    fault = {"mode": mode, "expires_at": expires_at}
    atomic_write_json(home / "state" / "fault.json", fault)

    python_exe = cfg.get("python_exe") or sys.executable
    alert_script = home / "bin" / "spillover_alert.py"
    if alert_script.is_file():
        try:
            spawn_detached([python_exe, str(alert_script), "fault_injection", mode], cwd=str(home))
        except OSError:
            pass
    return EXIT_OK, fault, f"fault {mode} injected until {expires_at}"


def _do_fault_clear() -> tuple[int, dict, str]:
    home = home_dir()
    cfg_path = home / "config.json"
    cfg = load_home_config(home)
    proxy_cfg = dict(cfg.get("proxy") or {})
    proxy_cfg["allow_fault_injection"] = False
    cfg["proxy"] = proxy_cfg
    atomic_write_json(cfg_path, cfg)
    atomic_write_json(home / "state" / "fault.json", {})
    return EXIT_OK, {}, "fault injection cleared"


def _do_events(tail: int) -> tuple[int, dict, str]:
    home = home_dir()
    path = home / "state" / "events.jsonl"
    if not path.is_file():
        return EXIT_OK, {"events": []}, "no events recorded yet"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail_lines = lines[-tail:] if tail and tail > 0 else lines
    events = []
    for ln in tail_lines:
        try:
            events.append(json.loads(ln))
        except ValueError:
            continue
    return EXIT_OK, {"events": events}, f"{len(events)} event(s)"


def _do_uninstall(*, purge: bool, assume_yes: bool) -> tuple[int, dict, str]:
    if not assume_yes:
        if not _stdin_is_tty():
            return EXIT_REFUSED, {}, "refusing: uninstall requires confirmation (pass --yes or run interactively)"
        reply = input(f"Uninstall Claude Spillover{' and PURGE data/secrets' if purge else ''}? [y/N]: ").strip().lower()
        if reply not in ("y", "yes"):
            return EXIT_REFUSED, {}, "uninstall aborted by operator"

    home = home_dir()
    removed = []
    app_dir = home / "app"
    if app_dir.is_dir():
        shutil.rmtree(app_dir, ignore_errors=True)
        removed.append(str(app_dir))
    if purge:
        for sub in ("omniroute-data", "secrets"):
            d = home / sub
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                removed.append(str(d))
    return EXIT_OK, {"removed": removed}, "uninstall complete"


# --------------------------------------------------------------------------- #
# CLI plumbing
# --------------------------------------------------------------------------- #
def _emit(args: argparse.Namespace, exit_code: int, payload: dict, message: str) -> int:
    if getattr(args, "output_json", False):
        # The message carries the reason for a failure; without it --json callers saw only an exit code.
        out = {"ok": exit_code == EXIT_OK, "exit_code": exit_code, "message": message, **(payload or {})}
        print(json.dumps(out, indent=2, default=str))
    else:
        print(message)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", dest="output_json", action="store_true", help="machine-readable output")

    p = argparse.ArgumentParser(
        prog="omniroute_tool.py",
        description="Operator CLI for Claude Spillover / OmniRoute (see scripts/spillover/CONTRACT.md)",
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("deploy", parents=[parent], help="copy spillover files into HOME_DIR, seed config, set ACLs")
    sub.add_parser("start", parents=[parent], help="spawn the supervisor and wait for health")
    sub.add_parser("stop", parents=[parent], help="stop the supervisor")
    sub.add_parser("status", parents=[parent], help="print proxy health + state.json summary")

    rollback = sub.add_parser("rollback", parents=[parent], help="disable routing, stop the proxy, remove autostart")
    rollback.add_argument("--all", action="store_true", help="also remove owned statusLine/hook and restore backups")

    key = sub.add_parser("key", parents=[parent], help="manage the omniroute_lane secret")
    key_sub = key.add_subparsers(dest="key_verb", required=True)
    key_sub.add_parser("set", parents=[parent], help="interactively store the lane key")
    key_sub.add_parser("check", parents=[parent], help="verify the stored lane key against OmniRoute")

    secrets_p = sub.add_parser("secrets", parents=[parent], help="manage OmniRoute signing secrets")
    secrets_sub = secrets_p.add_subparsers(dest="secrets_verb", required=True)
    secrets_sub.add_parser("init", parents=[parent], help="generate any of the four missing secrets")

    omni = sub.add_parser("omniroute", parents=[parent], help="configure/connect the OmniRoute install")
    omni_sub = omni.add_subparsers(dest="omniroute_verb", required=True)
    setup_p = omni_sub.add_parser("setup", parents=[parent], help="idempotently create combos + scoped lane key")
    setup_p.add_argument("--models-main", nargs="+", metavar="MODEL")
    setup_p.add_argument("--models-fast", nargs="+", metavar="MODEL")
    connect_p = omni_sub.add_parser("connect", parents=[parent], help="connect a provider via OAuth device flow")
    connect_p.add_argument("provider", choices=["codex"])
    connect_key_p = omni_sub.add_parser("connect-key", parents=[parent], help="connect an API-key provider")
    connect_key_p.add_argument("provider", choices=sorted(CONNECT_KEY_PROVIDERS))
    connect_key_p.add_argument("--from-env-agents", action="store_true",
                               help="read the key from .env.agents (CEREBRAS_API_KEY / ZAI_API_KEY) instead of a prompt")
    connect_key_p.add_argument("--env-name", help="the .env.agents name to read with --from-env-agents")

    smoke = sub.add_parser("smoke", parents=[parent], help="exercise the fallback leg end to end")
    smoke.add_argument("--model")
    smoke.add_argument("--tools", action="store_true")
    smoke.add_argument("--stream", action="store_true")
    smoke.add_argument("--corpus", metavar="DIR")

    sub.add_parser("doctor", parents=[parent], help="run the full safety/health check suite")

    install_p = sub.add_parser("install", parents=[parent], help="read-only OmniRoute runtime verification")
    install_p.add_argument("--verify", action="store_true", required=True)

    attest = sub.add_parser("attest", parents=[parent], help="record an operator attestation")
    attest_sub = attest.add_subparsers(dest="attest_verb", required=True)
    attest_sub.add_parser("chatgpt-training-off", parents=[parent])

    uninstall_p = sub.add_parser("uninstall", parents=[parent], help="remove the deployed app (optionally purge data)")
    uninstall_p.add_argument("--purge", action="store_true")
    uninstall_p.add_argument("--yes", action="store_true")

    spillover = sub.add_parser("spillover", parents=[parent], help="mode/routing/fault/event operations")
    spillover_sub = spillover.add_subparsers(dest="spillover_verb", required=True)

    mode_p = spillover_sub.add_parser("mode", parents=[parent])
    mode_p.add_argument("value", choices=list(VALID_MODES))

    enable_p = spillover_sub.add_parser("enable-routing", parents=[parent])
    enable_p.add_argument("--yes", action="store_true")

    disable_p = spillover_sub.add_parser("disable-routing", parents=[parent])
    disable_p.add_argument("--remove", action="store_true")

    deny_p = spillover_sub.add_parser("deny-repo", parents=[parent])
    deny_p.add_argument("path")

    fault_p = spillover_sub.add_parser("fault", parents=[parent])
    fault_sub = fault_p.add_subparsers(dest="fault_verb", required=True)
    fault_set_p = fault_sub.add_parser("set", parents=[parent])
    fault_set_p.add_argument("mode", choices=list(FAULT_MODES))
    fault_set_p.add_argument("--ttl", type=int, required=True, metavar="SEC")
    fault_sub.add_parser("clear", parents=[parent])

    events_p = spillover_sub.add_parser("events", parents=[parent])
    events_p.add_argument("--tail", type=int, default=20)

    spillover_sub.add_parser("status", parents=[parent])

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_USAGE

    if args.command == "deploy":
        return _emit(args, *_do_deploy())
    if args.command == "start":
        return _emit(args, *_do_start())
    if args.command == "stop":
        return _emit(args, *_do_stop())
    if args.command == "status":
        return _emit(args, *_do_status())
    if args.command == "rollback":
        return _emit(args, *_do_rollback(all_=args.all))
    if args.command == "key":
        if args.key_verb == "set":
            return _emit(args, *_do_key_set())
        return _emit(args, *_do_key_check())
    if args.command == "secrets":
        return _emit(args, *_do_secrets_init())
    if args.command == "omniroute":
        if args.omniroute_verb == "setup":
            return _emit(args, *_do_setup(args.models_main, args.models_fast))
        if args.omniroute_verb == "connect":
            return _emit(args, *_do_connect_codex())
        return _emit(args, *_do_connect_key(args.provider, from_env_agents=args.from_env_agents,
                                            env_name=args.env_name))
    if args.command == "smoke":
        return _emit(args, *_do_smoke(args.model, args.tools, args.stream, args.corpus))
    if args.command == "doctor":
        home = home_dir()
        cfg = load_home_config(home)
        result = run_doctor_checks(home, cfg)
        return _emit(args, EXIT_OK if result["ok"] else EXIT_CHECK_FAILED, result,
                     "doctor OK" if result["ok"] else "doctor FAILED")
    if args.command == "install":
        return _emit(args, *_do_install_verify())
    if args.command == "attest":
        return _emit(args, *_do_attest())
    if args.command == "uninstall":
        return _emit(args, *_do_uninstall(purge=args.purge, assume_yes=args.yes))
    if args.command == "spillover":
        if args.spillover_verb == "mode":
            return _emit(args, *_do_mode(args.value))
        if args.spillover_verb == "enable-routing":
            return _emit(args, *_do_enable_routing(assume_yes=args.yes))
        if args.spillover_verb == "disable-routing":
            return _emit(args, *_do_disable_routing(remove=args.remove))
        if args.spillover_verb == "deny-repo":
            return _emit(args, *_do_deny_repo(args.path))
        if args.spillover_verb == "fault":
            if args.fault_verb == "set":
                return _emit(args, *_do_fault_set(args.mode, args.ttl))
            return _emit(args, *_do_fault_clear())
        if args.spillover_verb == "events":
            return _emit(args, *_do_events(args.tail))
        return _emit(args, *_do_status())

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
