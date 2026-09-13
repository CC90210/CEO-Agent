"""Tests for scripts/integrations/omniroute_tool.py (CONTRACT.md — Claude Spillover).

Everything runs against temp dirs, a temp fake Claude settings file, and a fake
HTTP OmniRoute server on a random loopback port. Real, non-fake network calls
are limited to those the tests themselves intercept via monkeypatch (the
Codex device-flow test replaces `omniroute_tool.http_call`). Nothing under
%LOCALAPPDATA%/bravo-spillover or the real ~/.claude/settings.json is ever
touched: every test sets BRAVO_SPILLOVER_HOME / BRAVO_CLAUDE_SETTINGS /
BRAVO_IDE_SETTINGS to paths under pytest's tmp_path, and the Startup-folder
VBS path is monkeypatched away from the real Windows Startup folder too.

Secrets use the REAL lane_key.py (DPAPI on Windows) against the temp
HOME_DIR — no fake needed, and it exercises the real store/read path.
"""
from __future__ import annotations

import json
import os
import socket
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INTEGRATIONS = REPO / "scripts" / "integrations"
if str(INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS))

import omniroute_tool as ot  # noqa: E402

NODE = shutil.which("node")

# Captured at module import time, BEFORE any fixture monkeypatches the env —
# the real values, used only by the isolation guard test below.
_REAL_LOCALAPPDATA = os.environ.get("LOCALAPPDATA")
_REAL_APPDATA = os.environ.get("APPDATA")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_home_config(home: Path, *, proxy: dict | None = None, omniroute: dict | None = None,
                       extra: dict | None = None) -> dict:
    home.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(ot.REPO_CONFIG_PATH.read_text(encoding="utf-8"))
    if proxy:
        cfg["proxy"].update(proxy)
    if omniroute:
        cfg["omniroute"].update(omniroute)
    if extra:
        cfg.update(extra)
    (home / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return cfg


def store_secret(home: Path, name: str, value: str) -> None:
    ok = ot.lane_key_set_stdin(sys.executable, name, home, value)
    assert ok, f"failed to store secret {name!r} via the real lane_key.py"


@pytest.fixture(autouse=True)
def _isolate_environment(tmp_path, monkeypatch):
    """Defense in depth, active for EVERY test in this module — even one that
    forgets to request `home`. omniroute_tool resolves HOME_DIR and the Claude
    settings path from env vars at call time (never cached at import), so
    redirecting them here is sufficient; LOCALAPPDATA/APPDATA are redirected
    too so even the *default* fallback (used when BRAVO_SPILLOVER_HOME/
    BRAVO_IDE_SETTINGS are unset) can never resolve to the real profile.
    See test_never_touches_real_localappdata_bravo_spillover for the guard."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("BRAVO_CLAUDE_SETTINGS", str(tmp_path / "claude_settings.json"))
    monkeypatch.setenv("BRAVO_IDE_SETTINGS", str(tmp_path / "ide_settings.json"))
    # Never touch the real Windows Startup folder from a test.
    monkeypatch.setattr(ot, "startup_vbs_path", lambda: tmp_path / "Startup.vbs")
    yield


@pytest.fixture()
def home(tmp_path) -> Path:
    return tmp_path / "home"


# --------------------------------------------------------------------------- #
# Fake OmniRoute admin/API server
# --------------------------------------------------------------------------- #
class FakeOmniRouteHandler(BaseHTTPRequestHandler):
    server_version = "FakeOmniRoute/1"

    def log_message(self, *_a):  # keep test output quiet
        pass

    def _send_json(self, status, obj, set_cookie=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return {}

    def _authed(self):
        cookie = self.headers.get("Cookie") or ""
        return "auth_token=test-session" in cookie

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        state = self.server.state
        if self.path == "/api/auth/csrf":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, {"token": "csrf-abc", "expiresAt": "2099-01-01T00:00:00Z"})
        if self.path == "/api/providers":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, {"connections": state["connections"]})
        if self.path == "/api/combos":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, {"combos": state["combos"], "total": len(state["combos"])})
        if self.path.startswith("/v1/models"):
            auth = self.headers.get("Authorization") or ""
            if not auth:
                return self._send_json(401, {"error": "missing key"})
            expected = state.get("lane_key")
            if expected and auth == f"Bearer {expected}":
                return self._send_json(200, {"object": "list", "data": [{"id": "bravo-fallback"}]})
            return self._send_json(403, {"error": "invalid key"})
        if self.path == "/api/keys":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            listed = [{"id": k["id"], "name": k["body"].get("name")} for k in state["created_keys"]]
            return self._send_json(200, {"keys": listed + state.get("preexisting_keys", [])})
        if self.path == "/api/settings/require-login":
            return self._send_json(200, {"requireLogin": True})
        return self._send_json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        state = self.server.state
        if self.path == "/api/auth/login":
            body = self._read_json()
            if body.get("password") == state["password"]:
                return self._send_json(200, {"success": True}, set_cookie="auth_token=test-session; Path=/; HttpOnly")
            return self._send_json(401, {"error": "invalid password"})
        if self.path == "/api/combos":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            body = self._read_json()
            combo = dict(body)
            combo["id"] = f"combo-{len(state['combos']) + 1}"
            state["combos"].append(combo)
            return self._send_json(201, combo)
        if self.path == "/api/keys":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            body = self._read_json()
            key_id = "key-1"
            state["created_keys"].append({"id": key_id, "body": body})
            return self._send_json(201, {"id": key_id, "key": state["lane_key"], "name": body.get("name")})
        if self.path == "/api/providers":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            body = self._read_json()
            state["created_providers"].append(body)
            return self._send_json(201, {"id": "prov-1", "provider": body.get("provider")})
        if self.path in ("/api/system/version", "/api/settings/mitm", "/api/settings/require-login"):
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, {"ok": True})
        if self.path == "/v1/messages":
            handler = state.get("messages_handler")
            if handler:
                return handler(self)
            return self._send_json(200, {"content": []})
        if self.path == "/api/oauth/codex/device-complete":
            if not self._authed():
                return self._send_json(401, {"error": "unauthorized"})
            body = self._read_json()
            state["device_complete_body"] = body
            return self._send_json(200, {"success": True, "connection": {"id": "codex-1", "email": "cc@example.com"}})
        return self._send_json(404, {"error": "not found"})

    def do_PATCH(self):  # noqa: N802
        state = self.server.state
        if not self._authed():
            return self._send_json(401, {"error": "unauthorized"})
        if self.path.startswith("/api/providers/"):
            pid = self.path.rsplit("/", 1)[-1]
            body = self._read_json()
            state["provider_patches"].append((pid, body))
            return self._send_json(200, {"id": pid, **body})
        if self.path.startswith("/api/combos/"):
            cid = self.path.rsplit("/", 1)[-1]
            body = self._read_json()
            state["combo_patches"].append((cid, body))
            return self._send_json(200, {"id": cid, **body})
        if self.path.startswith("/api/keys/"):
            kid = self.path.rsplit("/", 1)[-1]
            body = self._read_json()
            state["key_patches"].append((kid, body))
            return self._send_json(200, {"id": kid, **body})
        return self._send_json(404, {"error": "not found"})

    def do_DELETE(self):  # noqa: N802
        state = self.server.state
        if not self._authed():
            return self._send_json(401, {"error": "unauthorized"})
        if self.path.startswith("/api/keys/"):
            state.setdefault("deleted_keys", []).append(self.path.rsplit("/", 1)[-1])
            return self._send_json(200, {"success": True})
        return self._send_json(404, {"error": "not found"})


@pytest.fixture()
def fake_omniroute():
    state = {
        "password": "test-init-pw", "lane_key": "sk-fake-lane-key-value",
        "connections": [], "combos": [],
        "created_keys": [], "created_providers": [],
        "provider_patches": [], "combo_patches": [], "key_patches": [],
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOmniRouteHandler)
    server.state = state
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, state
    finally:
        server.shutdown()
        thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# Governance metadata + real --help
# --------------------------------------------------------------------------- #
def test_capability_metadata_validates():
    sys.path.insert(0, str(REPO / "scripts"))
    from lib.capability_metadata import read_capability_meta, validate_capability_meta

    meta = read_capability_meta(INTEGRATIONS / "omniroute_tool.py")
    assert meta is not None
    assert validate_capability_meta(meta) == []


def test_real_help_subprocess():
    cp = subprocess.run(
        [sys.executable, str(INTEGRATIONS / "omniroute_tool.py"), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert cp.returncode == 0
    assert "omniroute_tool.py" in cp.stdout
    assert "spillover" in cp.stdout


def test_help_has_no_side_effects_on_home(home):
    # Constructing the parser and asking for --help must never touch HOME_DIR.
    with pytest.raises(SystemExit) as exc:
        ot.build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    assert not home.exists()


# --------------------------------------------------------------------------- #
# deploy
# --------------------------------------------------------------------------- #
def test_deploy_copies_files_and_seeds_config(home):
    code, payload, msg = ot._do_deploy()
    assert code == ot.EXIT_OK, msg

    for name in ot.APP_FILE_NAMES:
        assert (home / "app" / name).is_file(), name
    for name in ot.BIN_FILE_NAMES:
        assert (home / "bin" / name).is_file(), name
    assert (home / "app" / "VERSION").is_file()

    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["proxy"]["port"] == 20131
    for key, value in ot.DEFAULT_OMNIROUTE_LOG_ENV.items():
        assert cfg["omniroute"]["log_env"][key] == value

    assert payload["config_merged"] is False


def test_deploy_config_merge_preserves_local_values(home):
    home.mkdir(parents=True, exist_ok=True)
    local_cfg = {
        "proxy": {"port": 55555},
        "omniroute": {"log_env": {"APP_LOG_LEVEL": "debug"}},
        "custom_local_key": True,
    }
    (home / "config.json").write_text(json.dumps(local_cfg), encoding="utf-8")

    code, payload, msg = ot._do_deploy()
    assert code == ot.EXIT_OK, msg
    assert payload["config_merged"] is True

    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["proxy"]["port"] == 55555  # local value preserved, not overwritten
    assert cfg["omniroute"]["log_env"]["APP_LOG_LEVEL"] == "debug"  # local value preserved
    assert cfg["omniroute"]["log_env"]["CALL_LOG_RETENTION_DAYS"] == "1"  # new default filled in
    assert cfg["custom_local_key"] is True
    assert cfg["min_claude_code"] == "2.1.268"  # repo default filled in


def test_deploy_fails_cleanly_when_source_missing(home, monkeypatch):
    monkeypatch.setattr(ot, "SPILLOVER_SRC", home / "does-not-exist")
    code, payload, msg = ot._do_deploy()
    assert code == ot.EXIT_USAGE


def test_repo_config_carries_no_machine_specific_python_exe():
    repo_cfg = json.loads(ot.REPO_CONFIG_PATH.read_text(encoding="utf-8"))
    assert "python_exe" not in repo_cfg


def test_deploy_resolves_python_exe_on_this_machine(home):
    code, payload, msg = ot._do_deploy()
    assert code == ot.EXIT_OK, msg
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["python_exe"] == Path(sys.executable).as_posix()


def test_deploy_replaces_a_python_exe_that_no_longer_exists(home, tmp_path):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({"python_exe": str(tmp_path / "gone" / "python.exe")}), encoding="utf-8")
    code, payload, msg = ot._do_deploy()
    assert code == ot.EXIT_OK, msg
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["python_exe"] == Path(sys.executable).as_posix()


def test_deploy_keeps_a_configured_python_exe_that_exists(home, tmp_path):
    other = tmp_path / "other-python.exe"
    other.write_bytes(b"")
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({"python_exe": str(other)}), encoding="utf-8")
    code, payload, msg = ot._do_deploy()
    assert code == ot.EXIT_OK, msg
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["python_exe"] == str(other)


# --------------------------------------------------------------------------- #
# start / stop against a stub supervisor (real node, config-driven port)
# --------------------------------------------------------------------------- #
STUB_SUPERVISOR_JS = r"""
"use strict";
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const appDir = __dirname;
const homeDir = path.dirname(appDir);
const stateDir = path.join(homeDir, "state");
fs.mkdirSync(stateDir, { recursive: true });
fs.writeFileSync(path.join(stateDir, "supervisor.pid"), String(process.pid));
const cfg = JSON.parse(fs.readFileSync(path.join(homeDir, "config.json"), "utf8"));
const port = cfg.proxy.port;
const server = http.createServer((req, res) => {
  if (req.url === "/__spillover/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, instance_id: "stub", pid: process.pid, version: "stub",
      config_mode: "observe", mode: "direct", reset_at: null, fallback_healthy: true }));
    return;
  }
  res.writeHead(404);
  res.end();
});
server.listen(port, "127.0.0.1");
const stopFile = path.join(stateDir, "supervisor.stop");
const timer = setInterval(() => {
  if (fs.existsSync(stopFile)) {
    clearInterval(timer);
    server.close(() => process.exit(0));
  }
}, 100);
"""


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_start_stop_against_stub_supervisor(home):
    port = free_port()
    write_home_config(home, proxy={"port": port})
    app_dir = home / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "supervisor.js").write_text(STUB_SUPERVISOR_JS, encoding="utf-8")

    code, payload, msg = ot._do_start()
    assert code == ot.EXIT_OK, msg
    assert payload["health"]["ok"] is True

    code2, payload2, msg2 = ot._do_stop()
    assert code2 == ot.EXIT_OK, msg2

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and ot.proxy_health("127.0.0.1", port, timeout=0.3):
        time.sleep(0.1)
    assert ot.proxy_health("127.0.0.1", port, timeout=0.3) is None


def test_start_fails_when_not_deployed(home):
    write_home_config(home, proxy={"port": free_port()})
    code, payload, msg = ot._do_start()
    assert code == ot.EXIT_UNREACHABLE
    assert "not deployed" in msg


# --------------------------------------------------------------------------- #
# spillover mode
# --------------------------------------------------------------------------- #
def test_mode_atomic_edit(home):
    write_home_config(home)
    code, payload, msg = ot._do_mode("observe")
    assert code == ot.EXIT_OK
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["proxy"]["mode"] == "observe"


def test_mode_rejects_unknown_value(home):
    write_home_config(home)
    code, payload, msg = ot._do_mode("bogus")
    assert code == ot.EXIT_USAGE


def test_spill_mode_refuses_without_attestation(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "run_doctor_checks", lambda h, c: {"ok": True, "checks": []})
    code, payload, msg = ot._do_mode("spill")
    assert code == ot.EXIT_REFUSED
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("proxy", {}).get("mode") != "spill"


def test_spill_mode_refuses_on_failing_doctor(home, monkeypatch):
    write_home_config(home)
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "state" / "attestations.json").write_text(
        json.dumps({"chatgpt_training_off": {"attested": True}}), encoding="utf-8")
    monkeypatch.setattr(ot, "run_doctor_checks",
                         lambda h, c: {"ok": False, "checks": [{"name": "x", "ok": False, "detail": ""}]})
    code, payload, msg = ot._do_mode("spill")
    assert code == ot.EXIT_REFUSED


def test_spill_mode_succeeds_with_attestation_and_passing_doctor(home, monkeypatch):
    write_home_config(home)
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "state" / "attestations.json").write_text(
        json.dumps({"chatgpt_training_off": {"attested": True}}), encoding="utf-8")
    monkeypatch.setattr(ot, "run_doctor_checks", lambda h, c: {"ok": True, "checks": []})
    code, payload, msg = ot._do_mode("spill")
    assert code == ot.EXIT_OK
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["proxy"]["mode"] == "spill"


# --------------------------------------------------------------------------- #
# enable-routing / disable-routing / rollback
# --------------------------------------------------------------------------- #
def test_enable_routing_refuses_when_proxy_unhealthy(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: None)
    code, payload, msg = ot._do_enable_routing(assume_yes=True)
    assert code == ot.EXIT_REFUSED
    assert "not healthy" in msg


def test_enable_routing_refuses_on_denied_running_version(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    monkeypatch.setattr(ot, "get_running_claude_versions", lambda: ["2.1.265"])
    monkeypatch.setattr(ot, "get_cli_claude_version", lambda: None)
    code, payload, msg = ot._do_enable_routing(assume_yes=True)
    assert code == ot.EXIT_REFUSED
    assert "version" in msg.lower()


def test_enable_routing_refuses_on_below_min_version(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    monkeypatch.setattr(ot, "get_running_claude_versions", lambda: [])
    monkeypatch.setattr(ot, "get_cli_claude_version", lambda: "2.0.0")
    code, payload, msg = ot._do_enable_routing(assume_yes=True)
    assert code == ot.EXIT_REFUSED


def test_enable_routing_refuses_on_existing_credential_keys(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    monkeypatch.setattr(ot, "get_running_claude_versions", lambda: [])
    monkeypatch.setattr(ot, "get_cli_claude_version", lambda: "2.1.268")
    settings_path = ot.claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "sk-x"}}), encoding="utf-8")

    code, payload, msg = ot._do_enable_routing(assume_yes=True)
    assert code == ot.EXIT_REFUSED
    assert "ANTHROPIC_API_KEY" in msg


def test_enable_routing_writes_only_owned_keys_preserves_hooks_and_order(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    monkeypatch.setattr(ot, "get_running_claude_versions", lambda: [])
    monkeypatch.setattr(ot, "get_cli_claude_version", lambda: "2.1.268")

    settings_path = ot.claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing_hook = {"matcher": "", "hooks": [{"type": "command", "command": "pre-existing"}]}
    original = {"env": {"SOME_OTHER": "x"}, "hooks": {"SessionStart": [existing_hook]}}
    settings_path.write_text(json.dumps(original), encoding="utf-8")

    code, payload, msg = ot._do_enable_routing(assume_yes=True)
    assert code == ot.EXIT_OK, msg
    assert payload["diff"]  # the diff was produced

    new_settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert new_settings["env"]["SOME_OTHER"] == "x"
    assert new_settings["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:20131"
    assert new_settings["env"]["ENABLE_TOOL_SEARCH"] is True

    session_start = new_settings["hooks"]["SessionStart"]
    assert len(session_start) == 2
    assert session_start[0] == existing_hook  # never replaced or reordered
    assert "ensure_spillover.py" in session_start[1]["hooks"][0]["command"]
    assert "statusline.py" in new_settings["statusLine"]["command"]
    assert new_settings["statusLine"]["refreshInterval"] == 5

    backups = list(settings_path.parent.glob(f"{settings_path.name}.backup-spillover-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original

    owned = json.loads((home / "state" / "owned_settings.json").read_text(encoding="utf-8"))
    assert owned["env_keys"] == ["ANTHROPIC_BASE_URL", "ENABLE_TOOL_SEARCH"]
    assert owned["session_start_hook"] == session_start[1]


def test_enable_routing_refuses_noninteractive_without_yes(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    monkeypatch.setattr(ot, "get_running_claude_versions", lambda: [])
    monkeypatch.setattr(ot, "get_cli_claude_version", lambda: "2.1.268")
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: False)
    code, payload, msg = ot._do_enable_routing(assume_yes=False)
    assert code == ot.EXIT_REFUSED
    assert not ot.claude_settings_path().exists() or "ANTHROPIC_BASE_URL" not in json.loads(
        ot.claude_settings_path().read_text(encoding="utf-8")).get("env", {})


def test_disable_routing_sets_api_anthropic_first(home):
    settings_path = ot.claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:20131"}}), encoding="utf-8")

    code, payload, msg = ot._do_disable_routing(remove=False)
    assert code == ot.EXIT_OK
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com"


def test_disable_routing_remove_deletes_only_owned_keys(home):
    settings_path = ot.claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    hook_entry = {"matcher": "", "hooks": [{"type": "command", "command": "ensure"}]}
    other_hook = {"matcher": "", "hooks": [{"type": "command", "command": "other"}]}
    settings_path.write_text(json.dumps({
        "env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:20131", "ENABLE_TOOL_SEARCH": True, "KEEP_ME": 1},
        "statusLine": {"type": "command", "command": "x"},
        "hooks": {"SessionStart": [other_hook, hook_entry]},
    }), encoding="utf-8")
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "state" / "owned_settings.json").write_text(json.dumps({
        "settings_path": str(settings_path),
        "env_keys": ["ANTHROPIC_BASE_URL", "ENABLE_TOOL_SEARCH"],
        "status_line": True,
        "session_start_hook": hook_entry,
    }), encoding="utf-8")

    code, payload, msg = ot._do_disable_routing(remove=True)
    assert code == ot.EXIT_OK

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "ANTHROPIC_BASE_URL" not in settings["env"]
    assert "ENABLE_TOOL_SEARCH" not in settings["env"]
    assert settings["env"]["KEEP_ME"] == 1
    assert "statusLine" not in settings
    assert settings["hooks"]["SessionStart"] == [other_hook]


def _routing_ready(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    monkeypatch.setattr(ot, "get_running_claude_versions", lambda: [])
    monkeypatch.setattr(ot, "get_cli_claude_version", lambda: "2.1.268")


def test_enable_routing_twice_registers_the_ensure_hook_once(home, monkeypatch):
    _routing_ready(home, monkeypatch)
    settings_path = ot.claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"env": {}}), encoding="utf-8")

    assert ot._do_enable_routing(assume_yes=True)[0] == ot.EXIT_OK
    assert ot._do_enable_routing(assume_yes=True)[0] == ot.EXIT_OK
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert len([e for e in settings["hooks"]["SessionStart"] if ot._is_spillover_hook(e)]) == 1

    assert ot._do_disable_routing(remove=True)[0] == ot.EXIT_OK
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert not [e for e in settings.get("hooks", {}).get("SessionStart", []) if ot._is_spillover_hook(e)]


def test_disable_routing_remove_restores_preexisting_values(home, monkeypatch):
    _routing_ready(home, monkeypatch)
    settings_path = ot.claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    own_status = {"type": "command", "command": "my-own-statusline"}
    settings_path.write_text(json.dumps({"env": {"ENABLE_TOOL_SEARCH": "auto"}, "statusLine": own_status}),
                             encoding="utf-8")

    assert ot._do_enable_routing(assume_yes=True)[0] == ot.EXIT_OK
    # The second run sees our own values live; it must keep the first record, not overwrite it.
    assert ot._do_enable_routing(assume_yes=True)[0] == ot.EXIT_OK
    assert ot._do_disable_routing(remove=True)[0] == ot.EXIT_OK

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["env"]["ENABLE_TOOL_SEARCH"] == "auto"
    assert "ANTHROPIC_BASE_URL" not in settings["env"]
    assert settings["statusLine"] == own_status
    assert not (home / "state" / "owned_settings.json").exists()


def test_rollback_runs_in_order(home, monkeypatch):
    order = []

    def fake_disable(*, remove):
        order.append(("disable", remove))
        return ot.EXIT_OK, {}, "disabled"

    def fake_stop():
        order.append(("stop",))
        return ot.EXIT_OK, {}, "stopped"

    monkeypatch.setattr(ot, "_do_disable_routing", fake_disable)
    monkeypatch.setattr(ot, "_do_stop", fake_stop)
    vbs = ot.startup_vbs_path()
    vbs.parent.mkdir(parents=True, exist_ok=True)
    vbs.write_text("x", encoding="utf-8")

    code, payload, msg = ot._do_rollback(all_=True)
    assert code == ot.EXIT_OK
    assert order == [("disable", True), ("stop",)]
    assert not vbs.exists()


# --------------------------------------------------------------------------- #
# deny-repo
# --------------------------------------------------------------------------- #
def test_deny_repo_merges_correctly(tmp_path):
    target_repo = tmp_path / "some-repo"
    target_repo.mkdir()

    code, payload, msg = ot._do_deny_repo(str(target_repo))
    assert code == ot.EXIT_OK
    settings_file = target_repo / ".claude" / "settings.local.json"
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings["env"]["ANTHROPIC_CUSTOM_HEADERS"] == "X-Bravo-Spill: deny"

    code2, payload2, msg2 = ot._do_deny_repo(str(target_repo))
    assert code2 == ot.EXIT_OK
    settings2 = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings2["env"]["ANTHROPIC_CUSTOM_HEADERS"].count("X-Bravo-Spill: deny") == 1
    backups = list((target_repo / ".claude").glob("settings.local.json.backup-*"))
    assert len(backups) == 1  # only the second write had something to back up


def test_deny_repo_preserves_other_env_keys(tmp_path):
    target_repo = tmp_path / "other-repo"
    settings_file = target_repo / ".claude" / "settings.local.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(json.dumps({"env": {"KEEP": "me"}}), encoding="utf-8")

    code, payload, msg = ot._do_deny_repo(str(target_repo))
    assert code == ot.EXIT_OK
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings["env"]["KEEP"] == "me"
    assert "X-Bravo-Spill: deny" in settings["env"]["ANTHROPIC_CUSTOM_HEADERS"]


# --------------------------------------------------------------------------- #
# fault set / clear
# --------------------------------------------------------------------------- #
def test_fault_set_refuses_without_tty(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: False)
    code, payload, msg = ot._do_fault_set("force_limit", 60)
    assert code == ot.EXIT_REFUSED
    assert not (home / "state" / "fault.json").exists()


def test_fault_set_refuses_bad_mode(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: True)
    code, payload, msg = ot._do_fault_set("not-a-mode", 60)
    assert code == ot.EXIT_USAGE


def test_fault_set_and_clear_with_confirmation(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(ot, "spawn_detached", lambda *a, **k: None)

    code, payload, msg = ot._do_fault_set("force_limit", 60)
    assert code == ot.EXIT_OK
    fault = json.loads((home / "state" / "fault.json").read_text(encoding="utf-8"))
    assert fault["mode"] == "force_limit"
    cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg["proxy"]["allow_fault_injection"] is True

    code2, payload2, msg2 = ot._do_fault_clear()
    assert code2 == ot.EXIT_OK
    assert json.loads((home / "state" / "fault.json").read_text(encoding="utf-8")) == {}
    cfg2 = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert cfg2["proxy"]["allow_fault_injection"] is False


def test_fault_set_aborted_by_operator(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    code, payload, msg = ot._do_fault_set("force_reset", 30)
    assert code == ot.EXIT_REFUSED
    assert not (home / "state" / "fault.json").exists()


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def test_doctor_aggregates_and_fails(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: None)
    monkeypatch.setattr(ot, "admin_session", lambda cfg, home: (None, "no session"))
    monkeypatch.setattr(ot, "check_claude_code_versions", lambda cfg, **kw: {"ok": True, "versions": [], "bad": []})

    def raise_unreachable(*_a, **_k):
        raise ot.ApiUnreachable("no server on this port")

    monkeypatch.setattr(ot, "http_call", raise_unreachable)

    result = ot.run_doctor_checks(home, ot.load_home_config(home))
    assert result["ok"] is False
    names = {c["name"] for c in result["checks"]}
    assert "proxy health" in names
    assert any(not c["ok"] for c in result["checks"])


def test_doctor_cli_exit_code_three(home, monkeypatch):
    write_home_config(home)
    monkeypatch.setattr(ot, "run_doctor_checks",
                         lambda h, c: {"ok": False, "checks": [{"name": "x", "ok": False, "detail": ""}]})
    code = ot.main(["doctor", "--json"])
    assert code == ot.EXIT_CHECK_FAILED


def _healthy_doctor_setup(home, monkeypatch, *, rebinding_status=401):
    write_home_config(home, omniroute={"log_env": dict(ot.DEFAULT_OMNIROUTE_LOG_ENV)})
    monkeypatch.setattr(ot, "_check_listen_loopback_only", lambda port: (True, "ok"))
    monkeypatch.setattr(ot, "_check_no_tunnel_process", lambda: (True, "ok"))
    monkeypatch.setattr(ot, "check_claude_code_versions", lambda cfg, **kw: {"ok": True, "versions": [], "bad": []})
    monkeypatch.setattr(ot, "proxy_health", lambda h, p, timeout=2.0: {"ok": True})
    (home / "state").mkdir(parents=True, exist_ok=True)
    (home / "state" / "attestations.json").write_text(
        json.dumps({"chatgpt_training_off": {"attested": True}}), encoding="utf-8")

    class FakeSession:
        def get(self, path):
            if path == "/api/providers":
                return 200, {"connections": []}, b""
            return 404, {}, b""

    monkeypatch.setattr(ot, "admin_session", lambda cfg, home: (FakeSession(), None))

    def fake_http_call(url, *, method="GET", headers=None, json_body=None, raw_body=None, timeout=10, opener=None):
        if url.endswith("/v1/models"):
            return 401, {"error": "no key"}, b""
        if url.endswith("/api/settings/require-login") and method == "GET":
            return 200, {"requireLogin": True}, b""
        if (headers or {}).get("Host") == "evil.example":
            # OmniRoute has no Host allowlist; its auth is what refuses a DNS-rebinding page.
            return rebinding_status, {}, b""
        if method == "POST":
            return 401, {"error": "unauthorized"}, b""
        return 403, {}, b""

    monkeypatch.setattr(ot, "http_call", fake_http_call)

    runtime = home / "omniroute-src"
    (runtime / "dist" / "node_modules" / "next").mkdir(parents=True, exist_ok=True)
    (runtime / "dist" / "node_modules" / "next" / "package.json").write_text(
        json.dumps({"version": "16.3.3"}), encoding="utf-8")
    (runtime / "package.json").write_text(json.dumps({"version": "3.9.0"}), encoding="utf-8")


def test_doctor_passes_when_everything_is_healthy(home, monkeypatch):
    _healthy_doctor_setup(home, monkeypatch)
    result = ot.run_doctor_checks(home, ot.load_home_config(home))
    failing = [c for c in result["checks"] if not c["ok"]]
    assert not failing, failing
    assert result["ok"] is True


def test_doctor_fails_when_a_rebinding_host_reaches_a_route(home, monkeypatch):
    _healthy_doctor_setup(home, monkeypatch, rebinding_status=200)
    result = ot.run_doctor_checks(home, ot.load_home_config(home))
    failing = {c["name"] for c in result["checks"] if not c["ok"]}
    assert "rebinding Host/Origin probe refused on POST /v1/messages" in failing
    assert "rebinding Host/Origin probe refused on GET /api/providers" in failing
    assert result["ok"] is False


def test_http_call_does_not_identify_as_python_urllib():
    # auth.openai.com's edge answers "Python-urllib/x" with a 530 (live 2026-09-13), which is what broke
    # `omniroute connect codex`; a descriptive User-Agent gets through.
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["ua"] = self.headers.get("User-Agent")
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ot.http_call(f"http://127.0.0.1:{server.server_address[1]}/", timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    assert seen["ua"] == ot.HTTP_USER_AGENT


# --------------------------------------------------------------------------- #
# omniroute setup (against the fake OmniRoute)
# --------------------------------------------------------------------------- #
def test_setup_revokes_only_its_own_earlier_lane_keys(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    state["preexisting_keys"] = [{"id": "key-old", "name": "bravo-omniroute-lane"},
                                 {"id": "key-other", "name": "someone-elses-key"}]

    code, payload, msg = ot._do_setup(None, None)
    assert code == ot.EXIT_OK, msg
    assert state.get("deleted_keys") == ["key-old"]  # never the new key, never a foreign one
    assert payload["revoked_old_keys"] == ["key-old"]
    assert payload["revoke_errors"] == []


def test_setup_creates_combos_and_scoped_key_never_leaks(home, fake_omniroute, capsys):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    capsys.readouterr()
    exit_code = ot.main(["omniroute", "setup", "--json"])
    captured = capsys.readouterr()
    assert exit_code == ot.EXIT_OK, captured.out

    created_names = {c.get("name") for c in state["combos"]}
    assert {ot.COMBO_MAIN, ot.COMBO_FAST} <= created_names
    for combo in state["combos"]:
        if combo["name"] in (ot.COMBO_MAIN, ot.COMBO_FAST):
            assert combo["strategy"] == "priority"
            assert combo["config"]["compressionMode"] == "off"

    assert len(state["created_keys"]) == 1
    key_body = state["created_keys"][0]["body"]
    assert key_body["allowedCombos"] == [ot.COMBO_MAIN, ot.COMBO_FAST]
    assert key_body["scopes"] == []
    assert "manage" not in key_body["scopes"]

    assert len(state["key_patches"]) == 1
    _kid, patch_body = state["key_patches"][0]
    # OmniRoute endpoint CATEGORY ids; the paths used before matched nothing and every call got 403.
    assert patch_body["allowedEndpoints"] == ["chat", "models"]
    assert patch_body["compressionEnabled"] is False

    # the key must never appear in our own stdout/stderr or the JSON payload
    assert state["lane_key"] not in captured.out
    assert state["lane_key"] not in captured.err
    parsed_output = json.loads(captured.out)
    assert state["lane_key"] not in json.dumps(parsed_output)

    # ...but it IS stored locally, matching what the fake server issued
    assert ot.lane_key_get(sys.executable, "omniroute_lane", home) == state["lane_key"]


def test_setup_disables_opencode_and_auto_combo(home, fake_omniroute):
    port, state = fake_omniroute
    state["connections"] = [{"id": "oc-1", "provider": "opencode", "isActive": True}]
    state["combos"] = [{"id": "auto-1", "name": "auto", "isActive": True, "models": []}]
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    code, payload, msg = ot._do_setup(None, None)
    assert code == ot.EXIT_OK, msg
    assert payload["auto_combo_disabled"] is True
    assert payload["disabled_providers"][0] == {"provider": "opencode", "id": "oc-1", "ok": True}
    assert ("oc-1", {"isActive": False}) in state["provider_patches"]
    assert ("auto-1", {"isActive": False}) in state["combo_patches"]


def test_setup_refuses_on_forbidden_connected_provider(home, fake_omniroute):
    port, state = fake_omniroute
    state["connections"] = [{"id": "c1", "provider": "groq", "isActive": True}]  # "groq/" is forbidden
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    code, payload, msg = ot._do_setup(None, None)
    assert code != ot.EXIT_OK
    assert "groq" in str(payload.get("forbidden"))
    assert not state["combos"]  # refused before creating anything


def test_setup_refuses_on_forbidden_combo_model(home, fake_omniroute):
    port, state = fake_omniroute
    state["combos"] = [{"id": "x", "name": "some-combo", "isActive": True,
                         "models": [{"model": "claude/opus-4"}]}]
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    code, payload, msg = ot._do_setup(None, None)
    assert code != ot.EXIT_OK
    assert "claude/opus-4" in str(payload.get("forbidden"))


def test_setup_accepts_custom_models(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    code, payload, msg = ot._do_setup(["cx/custom-main"], ["cx/custom-fast"])
    assert code == ot.EXIT_OK, msg
    main_combo = next(c for c in state["combos"] if c["name"] == ot.COMBO_MAIN)
    assert main_combo["models"] == [{"model": "cx/custom-main", "priority": 1}]


def test_setup_fails_when_initial_password_missing(home, fake_omniroute):
    port, _state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    code, payload, msg = ot._do_setup(None, None)
    assert code == ot.EXIT_UNREACHABLE
    assert "initial_password" in msg


# --------------------------------------------------------------------------- #
# omniroute connect codex (fake device flow)
# --------------------------------------------------------------------------- #
def test_connect_codex_polls_fake_device_flow_and_never_prints_tokens(home, fake_omniroute, monkeypatch, capsys):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    real_http_call = ot.http_call
    poll_calls = {"n": 0}

    def fake_http_call(url, *, method="GET", headers=None, json_body=None, raw_body=None, timeout=10, opener=None):
        if url.startswith(ot.CODEX_API_BASE + "/deviceauth/usercode"):
            return 200, {"device_auth_id": "dev-1", "user_code": "ABCD-1234", "interval": 0.05}, b""
        if url.startswith(ot.CODEX_API_BASE + "/deviceauth/token"):
            poll_calls["n"] += 1
            if poll_calls["n"] < 2:
                return 403, {}, b""
            return 200, {"authorization_code": "authcode123", "code_verifier": "verifier123"}, b""
        if url.startswith(ot.CODEX_BASE + "/oauth/token"):
            return 200, {"access_token": "at-secret-value", "refresh_token": "rt-secret-value",
                         "id_token": "idt-secret-value", "expires_in": 3600}, b""
        return real_http_call(url, method=method, headers=headers, json_body=json_body, raw_body=raw_body,
                               timeout=timeout, opener=opener)

    monkeypatch.setattr(ot, "http_call", fake_http_call)

    capsys.readouterr()
    code, payload, msg = ot._do_connect_codex()
    captured = capsys.readouterr()

    assert code == ot.EXIT_OK, msg
    assert "ABCD-1234" in captured.out
    assert ot.CODEX_VERIFICATION_URI in captured.out
    assert poll_calls["n"] >= 2
    assert payload["connection"]["email"] == "cc@example.com"
    assert state["device_complete_body"]["access_token"] == "at-secret-value"

    for secret in ("at-secret-value", "rt-secret-value", "idt-secret-value"):
        assert secret not in captured.out
        assert secret not in captured.err


def test_connect_codex_reports_device_disabled(home, fake_omniroute, monkeypatch):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])

    real_http_call = ot.http_call

    def fake_http_call(url, *, method="GET", headers=None, json_body=None, raw_body=None, timeout=10, opener=None):
        if url.startswith(ot.CODEX_API_BASE + "/deviceauth/usercode"):
            return 404, {}, b""
        return real_http_call(url, method=method, headers=headers, json_body=json_body, raw_body=raw_body,
                               timeout=timeout, opener=opener)

    monkeypatch.setattr(ot, "http_call", fake_http_call)
    code, payload, msg = ot._do_connect_codex()
    assert code == ot.EXIT_UNREACHABLE
    assert "not enabled" in msg


# --------------------------------------------------------------------------- #
# omniroute connect-key
# --------------------------------------------------------------------------- #
def test_connect_key_never_echoes(home, fake_omniroute, monkeypatch, capsys):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(ot.getpass, "getpass", lambda prompt="": "super-secret-cerebras-key")

    capsys.readouterr()
    exit_code = ot.main(["omniroute", "connect-key", "cerebras", "--json"])
    captured = capsys.readouterr()

    assert exit_code == ot.EXIT_OK, captured.out
    assert "super-secret-cerebras-key" not in captured.out
    assert "super-secret-cerebras-key" not in captured.err
    assert state["created_providers"][0]["provider"] == "cerebras"
    assert state["created_providers"][0]["apiKey"] == "super-secret-cerebras-key"


def test_connect_key_refuses_noninteractive(home, fake_omniroute, monkeypatch):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: False)
    code, payload, msg = ot._do_connect_key("cerebras")
    assert code == ot.EXIT_USAGE
    assert not state["created_providers"]


def test_connect_key_rejects_unknown_provider(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    code, payload, msg = ot._do_connect_key("glm-cn")
    assert code == ot.EXIT_USAGE
    # CC 2026-09-13: Z.AI is not part of the chain.
    assert ot._do_connect_key("zai")[0] == ot.EXIT_USAGE


class _FakeSecretLoader:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def load_env(self, required=None):
        return dict(self.values)


def test_connect_key_from_env_agents_needs_no_tty_and_never_echoes(home, fake_omniroute, monkeypatch, capsys):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: False)
    monkeypatch.setattr(ot, "_secret_loader_module", lambda: _FakeSecretLoader({"CEREBRAS_API_KEY": "env-secret-cerebras"}))

    capsys.readouterr()
    exit_code = ot.main(["omniroute", "connect-key", "cerebras", "--from-env-agents", "--json"])
    captured = capsys.readouterr()

    assert exit_code == ot.EXIT_OK, captured.out
    assert "env-secret-cerebras" not in captured.out + captured.err
    assert state["created_providers"][0]["provider"] == "cerebras"
    assert state["created_providers"][0]["apiKey"] == "env-secret-cerebras"


def test_connect_key_from_env_agents_missing_name_points_at_similar_names(home, fake_omniroute, monkeypatch):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_secret_loader_module", lambda: _FakeSecretLoader({"CEREBRAS_KEY": "value-must-not-leak"}))

    code, payload, msg = ot._do_connect_key("cerebras", from_env_agents=True)
    assert code == ot.EXIT_USAGE
    assert "CEREBRAS_API_KEY" in msg and "CEREBRAS_KEY" in msg
    assert "value-must-not-leak" not in msg + json.dumps(payload)
    assert not state["created_providers"]


def test_connect_key_from_env_agents_honours_env_name(home, fake_omniroute, monkeypatch):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_secret_loader_module", lambda: _FakeSecretLoader({"MY_CEREBRAS": "cerebras-secret"}))

    code, payload, msg = ot._do_connect_key("cerebras", from_env_agents=True, env_name="MY_CEREBRAS")
    assert code == ot.EXIT_OK, msg
    assert state["created_providers"][0]["apiKey"] == "cerebras-secret"


def test_connect_key_cloudflare_sends_the_account_id(home, fake_omniroute, monkeypatch):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_secret_loader_module", lambda: _FakeSecretLoader({"CLOUDFLARE_API_TOKEN": "cf-secret"}))

    code, payload, msg = ot._do_connect_key("cloudflare", from_env_agents=True, account_id="acct-synthetic")
    assert code == ot.EXIT_OK, msg
    created = state["created_providers"][0]
    assert created["provider"] == "cloudflare-ai"
    assert created["providerSpecificData"] == {"accountId": "acct-synthetic"}


def test_connect_key_cloudflare_requires_an_account_id(home, fake_omniroute, monkeypatch):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "initial_password", state["password"])
    monkeypatch.setattr(ot, "_secret_loader_module", lambda: _FakeSecretLoader({"CLOUDFLARE_API_TOKEN": "cf-secret"}))

    code, payload, msg = ot._do_connect_key("cloudflare", from_env_agents=True)
    assert code == ot.EXIT_USAGE
    assert not state["created_providers"]


# --------------------------------------------------------------------------- #
# key set / key check
# --------------------------------------------------------------------------- #
def test_key_set_invokes_lane_key_interactively(home, monkeypatch):
    calls = []

    class Result:
        returncode = 0

    def fake_run_interactive(cmd, **kwargs):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(ot, "run_interactive", fake_run_interactive)
    code, payload, msg = ot._do_key_set()
    assert code == ot.EXIT_OK
    assert calls
    assert "set" in calls[0] and "omniroute_lane" in calls[0]


def test_key_check_accepts_and_lists_models(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", state["lane_key"])

    code, payload, msg = ot._do_key_check()
    assert code == ot.EXIT_OK
    assert payload == {"stored": True, "accepted": True, "models": ["bravo-fallback"]}


def test_key_check_rejects_wrong_key(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", "wrong-key-value")

    code, payload, msg = ot._do_key_check()
    assert code == ot.EXIT_UNREACHABLE
    assert payload["accepted"] is False


def test_key_check_reports_not_stored(home):
    write_home_config(home)
    code, payload, msg = ot._do_key_check()
    assert code == ot.EXIT_UNREACHABLE
    assert payload["stored"] is False


# --------------------------------------------------------------------------- #
# secrets init
# --------------------------------------------------------------------------- #
def test_secrets_init_generates_all_four_and_is_idempotent(home):
    code, payload, msg = ot._do_secrets_init()
    assert code == ot.EXIT_OK
    assert set(payload["secrets"]) == {name for name, _ in ot.SECRET_SPECS}
    assert all(v == "generated" for v in payload["secrets"].values())
    for name, _nbytes in ot.SECRET_SPECS:
        assert ot.lane_key_exists(sys.executable, name, home)

    before = ot.lane_key_get(sys.executable, "jwt_secret", home)
    code2, payload2, msg2 = ot._do_secrets_init()
    assert code2 == ot.EXIT_OK
    assert payload2["secrets"]["jwt_secret"] == "already-present"
    assert ot.lane_key_get(sys.executable, "jwt_secret", home) == before  # never regenerated


# --------------------------------------------------------------------------- #
# smoke (against the fake OmniRoute)
# --------------------------------------------------------------------------- #
def test_smoke_passes_plain_text(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", state["lane_key"])
    state["messages_handler"] = lambda h: h._send_json(200, {"content": [{"type": "text", "text": "OK"}]})

    code, payload, msg = ot._do_smoke(None, False, False, None)
    assert code == ot.EXIT_OK, payload
    assert payload["cases"] and all(c["ok"] for c in payload["cases"])


def test_smoke_fails_on_error_status(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", state["lane_key"])
    state["messages_handler"] = lambda h: h._send_json(500, {"error": "boom"})

    code, payload, msg = ot._do_smoke(None, False, False, None)
    assert code == ot.EXIT_CHECK_FAILED
    assert not all(c["ok"] for c in payload["cases"])


def test_smoke_tool_name_case_preserved(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", state["lane_key"])

    def handler(h):
        body = h._read_json()
        if body.get("tools"):
            return h._send_json(200, {"content": [{"type": "tool_use", "id": "t1", "name": "Get_Weather",
                                                     "input": {"city": "Denver"}}]})
        return h._send_json(200, {"content": [{"type": "text", "text": "OK"}]})

    state["messages_handler"] = handler
    code, payload, msg = ot._do_smoke(None, True, False, None)
    assert code == ot.EXIT_OK, payload
    case = next(c for c in payload["cases"] if c["name"] == "tool-name-case")
    assert case["ok"] is True


def test_smoke_flags_lowercased_tool_name(home, fake_omniroute):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", state["lane_key"])

    def handler(h):
        body = h._read_json()
        if body.get("tools"):
            return h._send_json(200, {"content": [{"type": "tool_use", "id": "t1", "name": "get_weather",
                                                     "input": {}}]})
        return h._send_json(200, {"content": [{"type": "text", "text": "OK"}]})

    state["messages_handler"] = handler
    code, payload, msg = ot._do_smoke(None, True, False, None)
    assert code == ot.EXIT_CHECK_FAILED
    case = next(c for c in payload["cases"] if c["name"] == "tool-name-case")
    assert case["ok"] is False


def test_smoke_corpus_replays_json_bodies(home, fake_omniroute, tmp_path):
    port, state = fake_omniroute
    write_home_config(home, proxy={"omniroute_base": f"http://127.0.0.1:{port}"})
    store_secret(home, "omniroute_lane", state["lane_key"])
    state["messages_handler"] = lambda h: h._send_json(200, {"content": []})

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "case1.json").write_text(json.dumps({"model": "bravo-fallback", "max_tokens": 8,
                                                     "messages": [{"role": "user", "content": "hi"}]}),
                                        encoding="utf-8")

    code, payload, msg = ot._do_smoke(None, False, False, str(corpus))
    assert code == ot.EXIT_OK, payload
    assert any(c["name"] == "case1.json" for c in payload["cases"])


def test_smoke_fails_without_stored_lane_key(home):
    write_home_config(home)
    code, payload, msg = ot._do_smoke(None, False, False, None)
    assert code == ot.EXIT_UNREACHABLE


# --------------------------------------------------------------------------- #
# install --verify
# --------------------------------------------------------------------------- #
def test_install_verify_passes(home):
    runtime = home / "omniroute-src"
    (runtime / "bin").mkdir(parents=True, exist_ok=True)
    (runtime / "dist" / "node_modules" / "next").mkdir(parents=True, exist_ok=True)
    (runtime / "bin" / "omniroute.mjs").write_text("", encoding="utf-8")
    (runtime / "dist" / "server.js").write_text("", encoding="utf-8")
    (runtime / "package.json").write_text(json.dumps({"version": "3.9.0"}), encoding="utf-8")
    (runtime / "dist" / "node_modules" / "next" / "package.json").write_text(
        json.dumps({"version": "16.3.3"}), encoding="utf-8")
    write_home_config(home)

    code, payload, msg = ot._do_install_verify()
    checks = {c["name"]: c for c in payload["checks"]}
    assert checks["bin/omniroute.mjs present"]["ok"] is True
    assert checks["dist/server.js present"]["ok"] is True
    assert checks["bundled next >= min_next"]["ok"] is True
    assert checks["HEAD matches config git_sha"]["ok"] is True  # not a git checkout -> skipped as ok


def test_install_verify_fails_when_runtime_missing(home):
    write_home_config(home)
    code, payload, msg = ot._do_install_verify()
    assert code == ot.EXIT_CHECK_FAILED
    assert not all(c["ok"] for c in payload["checks"])


def test_install_verify_flags_old_next(home):
    runtime = home / "omniroute-src"
    (runtime / "bin").mkdir(parents=True, exist_ok=True)
    (runtime / "dist" / "node_modules" / "next").mkdir(parents=True, exist_ok=True)
    (runtime / "bin" / "omniroute.mjs").write_text("", encoding="utf-8")
    (runtime / "dist" / "server.js").write_text("", encoding="utf-8")
    (runtime / "dist" / "node_modules" / "next" / "package.json").write_text(
        json.dumps({"version": "14.0.0"}), encoding="utf-8")
    write_home_config(home)

    code, payload, msg = ot._do_install_verify()
    assert code == ot.EXIT_CHECK_FAILED
    checks = {c["name"]: c for c in payload["checks"]}
    assert checks["bundled next >= min_next"]["ok"] is False


# --------------------------------------------------------------------------- #
# attest
# --------------------------------------------------------------------------- #
def test_attest_records_with_confirmation(home, monkeypatch):
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    code, payload, msg = ot._do_attest()
    assert code == ot.EXIT_OK
    data = json.loads((home / "state" / "attestations.json").read_text(encoding="utf-8"))
    assert data["chatgpt_training_off"]["attested"] is True


def test_attest_refuses_noninteractive(home, monkeypatch):
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: False)
    code, payload, msg = ot._do_attest()
    assert code == ot.EXIT_USAGE
    assert not (home / "state" / "attestations.json").exists()


def test_attest_declined(home, monkeypatch):
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    code, payload, msg = ot._do_attest()
    assert code == ot.EXIT_REFUSED


# --------------------------------------------------------------------------- #
# events / status / uninstall
# --------------------------------------------------------------------------- #
def test_events_tail(home):
    state_dir = home / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"i": i}) for i in range(5)]
    (state_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    code, payload, msg = ot._do_events(2)
    assert code == ot.EXIT_OK
    assert [e["i"] for e in payload["events"]] == [3, 4]


def test_events_empty_when_no_file(home):
    code, payload, msg = ot._do_events(20)
    assert code == ot.EXIT_OK
    assert payload["events"] == []


def test_status_reports_down_when_no_proxy(home):
    write_home_config(home, proxy={"port": free_port()})
    code, payload, msg = ot._do_status()
    assert code == ot.EXIT_OK
    assert payload["healthy"] is False


def test_uninstall_removes_app_dir_only(home):
    (home / "app").mkdir(parents=True, exist_ok=True)
    (home / "app" / "x.js").write_text("x", encoding="utf-8")
    (home / "omniroute-data").mkdir(parents=True, exist_ok=True)

    code, payload, msg = ot._do_uninstall(purge=False, assume_yes=True)
    assert code == ot.EXIT_OK
    assert not (home / "app").exists()
    assert (home / "omniroute-data").exists()


def test_uninstall_purge_removes_data_and_secrets(home):
    (home / "app").mkdir(parents=True, exist_ok=True)
    (home / "omniroute-data").mkdir(parents=True, exist_ok=True)
    (home / "secrets").mkdir(parents=True, exist_ok=True)

    code, payload, msg = ot._do_uninstall(purge=True, assume_yes=True)
    assert code == ot.EXIT_OK
    assert not (home / "omniroute-data").exists()
    assert not (home / "secrets").exists()


def test_uninstall_refuses_noninteractive_without_yes(home, monkeypatch):
    (home / "app").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ot, "_stdin_is_tty", lambda: False)
    code, payload, msg = ot._do_uninstall(purge=False, assume_yes=False)
    assert code == ot.EXIT_REFUSED
    assert (home / "app").exists()


# --------------------------------------------------------------------------- #
# CLI argument wiring smoke tests
# --------------------------------------------------------------------------- #
def test_main_with_no_command_prints_help_and_exits_usage(capsys):
    code = ot.main([])
    assert code == ot.EXIT_USAGE
    assert "omniroute_tool.py" in capsys.readouterr().out


def test_main_rejects_unknown_spillover_verb():
    with pytest.raises(SystemExit):
        ot.build_parser().parse_args(["spillover", "not-a-verb"])


# --------------------------------------------------------------------------- #
# Isolation guard — proves the autouse fixture actually works
# --------------------------------------------------------------------------- #
def test_never_touches_real_localappdata_bravo_spillover(home, monkeypatch):
    """A representative sweep of mutating verbs must never write under the
    REAL %LOCALAPPDATA%/bravo-spillover (or ~/.claude/settings.json), even
    though the autouse `_isolate_environment` fixture is active for every
    test — this test independently re-verifies it by comparing against the
    real path captured at module import, before any monkeypatching."""
    assert _REAL_LOCALAPPDATA, "LOCALAPPDATA must be set on this machine for the guard to mean anything"
    real_home = Path(_REAL_LOCALAPPDATA) / "bravo-spillover"

    # A running install rewrites these on its own at any moment (OmniRoute's database, the proxy's
    # state and logs), so comparing them would flag the live service rather than a test.
    def written_by_live_service(rel: Path) -> bool:
        if rel.parts[0] == "omniroute-data":
            return True
        if rel.parts[0] != "state":
            return False
        name = rel.parts[-1]
        return (rel.parts[1:2] in (("logs",), ("captured",)) or name == "supervisor.pid"
                or name.startswith("state.json") or name.startswith("events.jsonl"))

    def snapshot():
        if not real_home.exists():
            return None
        return {str(p): p.stat().st_mtime for p in real_home.rglob("*")
                if p.is_file() and not written_by_live_service(p.relative_to(real_home))}

    before = snapshot()

    # home_dir() must resolve under tmp_path right now, not the real profile.
    assert str(ot.home_dir()) != str(real_home)
    assert Path(os.environ["LOCALAPPDATA"]) != Path(_REAL_LOCALAPPDATA)

    ot._do_deploy()
    ot._do_mode("observe")
    ot._do_fault_clear()
    ot._do_events(5)
    ot._do_disable_routing(remove=True)
    ot._do_uninstall(purge=True, assume_yes=True)

    after = snapshot()
    assert after == before, "a verb touched the REAL %LOCALAPPDATA%/bravo-spillover directory"
