"""Tests for scripts/spillover/supervisor.js (CONTRACT.md §10-11).

Everything runs against fakes on random loopback ports: a stub proxy worker (or the real
spillover_proxy.js when it exists), a fake OmniRoute, a fake lane_key.py and a fake spillover_alert.py.
No real OmniRoute, no quota, and nothing under %LOCALAPPDATA%/bravo-spillover is touched: every
supervisor runs with --test --state-dir <tmp>/home/state, so HOME_DIR is a temp dir.

Set SPILLOVER_SUPERVISOR_TEST_STUB=1 to force the stub worker even when the real proxy exists.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPILL = REPO / "scripts" / "spillover"
SUPERVISOR = SPILL / "supervisor.js"
REAL_PROXY = SPILL / "spillover_proxy.js"
NODE = shutil.which("node")
IS_WIN = os.name == "nt"
USE_REAL_PROXY = REAL_PROXY.exists() and os.environ.get("SPILLOVER_SUPERVISOR_TEST_STUB") != "1"

pytestmark = pytest.mark.skipif(NODE is None, reason="node not on PATH")

FAKE_STORAGE = "fake-storage-key-7f3a9c1e5b"
FAKE_PASSWORD = "fake-initial-pw-2d8e4b6a0c"
FAKE_JWT = "fake-jwt-secret-9c2f7a1d4e"
FAKE_APIKEY = "fake-api-key-secret-5b8e3f0a2c"
FAKE_LANE = "fake-lane-key-for-tests-only"
ALL_OMNI_SECRETS = {
    "STORAGE_ENCRYPTION_KEY": FAKE_STORAGE,
    "INITIAL_PASSWORD": FAKE_PASSWORD,
    "JWT_SECRET": FAKE_JWT,
    "API_KEY_SECRET": FAKE_APIKEY,
}

# Stub proxy worker: serves /__spillover/health and records its argv / execArgv / env names.
STUB_WORKER = r"""
"use strict";
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const argv = process.argv.slice(2);
const arg = (f) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : undefined; };
const port = Number(arg("--port"));
const stateDir = arg("--state-dir");
const instanceId = crypto.randomUUID();
fs.writeFileSync(path.join(stateDir, `worker-${process.pid}.json`),
  JSON.stringify({ pid: process.pid, argv, execArgv: process.execArgv, envNames: Object.keys(process.env) }));
http.createServer((req, res) => {
  if (req.url === "/__spillover/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, instance_id: instanceId, pid: process.pid, version: "stub",
      config_mode: "observe", mode: "direct", reset_at: null, fallback_healthy: true }));
    return;
  }
  res.writeHead(404);
  res.end();
}).listen(port, "127.0.0.1", () => console.log(`LISTENING ${port}`));
"""

# Fake OmniRoute (ESM). Records argv/env to RUNS/<pid>.json, echoes its secrets to stdout (the
# supervisor must redact them from omniroute.log), then listens on --port.
FAKE_OMNIROUTE = r"""
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
const RUNS = __RUNS__;
const argv = process.argv.slice(2);
const port = Number(argv[argv.indexOf("--port") + 1]);
fs.mkdirSync(RUNS, { recursive: true });
const rec = { pid: process.pid, argv: process.argv, execArgv: process.execArgv, cwd: process.cwd(), env: { ...process.env } };
const tmp = path.join(RUNS, `${process.pid}.tmp`);
fs.writeFileSync(tmp, JSON.stringify(rec));
fs.renameSync(tmp, path.join(RUNS, `${process.pid}.json`));
console.log(`fake omniroute up; storage=${process.env.STORAGE_ENCRYPTION_KEY || ""} pw=${process.env.INITIAL_PASSWORD || ""}`);
http.createServer((req, res) => { res.writeHead(200); res.end("fake-omniroute"); }).listen(port, "127.0.0.1");
"""

FAKE_LANE_KEY = r"""
import sys
VALUES = {
    "storage_encryption": __STORAGE__,
    "initial_password": __PASSWORD__,
    "jwt_secret": __JWT__,
    "api_key_secret": __APIKEY__,
}
MISSING = set(__MISSING__)
if len(sys.argv) == 3 and sys.argv[1] == "get" and sys.argv[2] in VALUES and sys.argv[2] not in MISSING:
    sys.stdout.write(VALUES[sys.argv[2]] + "\n")
    sys.exit(0)
sys.stderr.write("no such key\n")
sys.exit(1)
"""

FAKE_ALERT = r"""
import json, pathlib, sys
out = pathlib.Path(__file__).resolve().parent.parent / "alerts.jsonl"
with open(out, "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
"""


# ---------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(pred, timeout: float, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while True:
        value = pred()
        if value:
            return value
        if time.monotonic() >= deadline:
            return value
        time.sleep(interval)


def health(port: int, timeout: float = 1.0):
    """GET /__spillover/health -> parsed JSON on 200, else None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__spillover/health", timeout=timeout) as r:
            if r.status != 200:
                return None
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    if IS_WIN:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_tree(pid: int) -> None:
    if not pid_alive(pid):
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def render_lane_key(missing: tuple[str, ...] = ()) -> str:
    """Fills in FAKE_LANE_KEY's placeholders. `missing` names secrets that should look absent."""
    src = FAKE_LANE_KEY
    src = src.replace("__STORAGE__", json.dumps(FAKE_STORAGE))
    src = src.replace("__PASSWORD__", json.dumps(FAKE_PASSWORD))
    src = src.replace("__JWT__", json.dumps(FAKE_JWT))
    src = src.replace("__APIKEY__", json.dumps(FAKE_APIKEY))
    src = src.replace("__MISSING__", json.dumps(list(missing)))
    return src


def render_fake_omniroute(runs_dir: Path) -> str:
    return FAKE_OMNIROUTE.replace("__RUNS__", json.dumps(str(runs_dir)))


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _health_with_new_pid(port: int, old_pid: int):
    h = health(port)
    return h if (h and h.get("pid") != old_pid) else None


# A plain, non-spillover HTTP listener: what "a foreign plain HTTP listener holds the port" means in
# CONTRACT.md §10. It never answers /__spillover/health with ok:true, so the supervisor must treat it
# as foreign. Run as a real node subprocess (not Python) -- on this Windows box two separate node
# processes reliably contend for a port (confirmed: the second bind gets EADDRINUSE), which is exactly
# what CONTRACT.md's single-instance check depends on.
FOREIGN_LISTENER_JS = r"""
"use strict";
const http = require("node:http");
const port = Number(process.argv[2]);
http.createServer((req, res) => { res.writeHead(404); res.end(); }).listen(port, "127.0.0.1", () => {
  console.log(`FOREIGN LISTENING ${port}`);
});
"""


class SupervisorHandle:
    """A running `node supervisor.js --test ...` subprocess, its paths, and safe teardown."""

    def __init__(self, proc: subprocess.Popen, home: Path, port: int):
        self.proc = proc
        self.home = home
        self.port = port
        self.state_dir = home / "state"
        self.pidfile = self.state_dir / "supervisor.pid"
        self.stopfile = self.state_dir / "supervisor.stop"
        self._lines: list[str] = []
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

    def _drain(self) -> None:
        # Must keep draining stdout/stderr continuously: an unread pipe can fill and block the child,
        # which would otherwise hang the whole test.
        try:
            for line in self.proc.stdout:
                self._lines.append(line.rstrip("\n"))
        except (ValueError, OSError):
            pass

    def output(self) -> str:
        return "\n".join(self._lines)

    def wait_health(self, timeout: float = 8.0):
        return wait_until(lambda: health(self.port), timeout)

    def wait_exit(self, timeout: float = 10.0):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def stop(self, timeout: float = 10.0) -> None:
        """Graceful stop-file shutdown, escalating to a full taskkill of the process tree.

        Idempotent and safe to call on an already-exited process (the common case when a test already
        drove its own shutdown and asserted on it).
        """
        if self.proc.poll() is None:
            try:
                self.stopfile.write_text("", encoding="utf-8")
            except OSError:
                pass
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass
        if self.proc.poll() is None:
            kill_tree(self.proc.pid)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self._reader.join(timeout=2)


def _spawn_supervisor(
    tmp_path: Path,
    *,
    name: str = "home",
    port: int | None = None,
    config: dict | None = None,
    bin_files: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
) -> SupervisorHandle:
    """Stages a fresh HOME_DIR under tmp_path and launches `node supervisor.js --test ...` against it.

    HOME_DIR/app/spillover_proxy.js is always the STUB_WORKER (never the real spillover_proxy.js next to
    supervisor.js): --test mode makes HOME_DIR = parent of --state-dir precisely so a test can stage
    whichever worker it wants at HOME_DIR/app. These tests exercise supervisor.js's own mechanics --
    single instance, worker respawn, the OmniRoute child lifecycle, shutdown -- which do not depend on
    the proxy's own HTTP behaviour (that is test_spillover_proxy.py's job); using the stub keeps them
    fast and independent of the real proxy's config schema.
    """
    home = tmp_path / name
    state_dir = home / "state"
    app_dir = home / "app"
    bin_dir = home / "bin"
    for d in (state_dir, app_dir, bin_dir):
        d.mkdir(parents=True, exist_ok=True)

    (app_dir / "spillover_proxy.js").write_text(STUB_WORKER, encoding="utf-8")
    for fname, content in (bin_files or {}).items():
        (bin_dir / fname).write_text(content, encoding="utf-8")
    if config is not None:
        (home / "config.json").write_text(json.dumps(config), encoding="utf-8")

    if port is None:
        port = free_port()
    args = [NODE, str(SUPERVISOR), "--test", "--state-dir", str(state_dir), "--port", str(port)]
    args += extra_args or []

    proc = subprocess.Popen(args, cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return SupervisorHandle(proc, home, port)


@pytest.fixture
def supervisors():
    """Factory fixture: start(tmp_path, **kw) -> SupervisorHandle. Every handle is stopped at teardown.

    RAM is tight on this box, so nothing here may leak a node.exe: each handle is stopped (stop file,
    then a full taskkill of its tree if that does not land in time) whether the test passed or failed.
    """
    handles: list[SupervisorHandle] = []

    def start(tmp_path: Path, **kwargs) -> SupervisorHandle:
        h = _spawn_supervisor(tmp_path, **kwargs)
        handles.append(h)
        return h

    yield start

    for h in reversed(handles):
        try:
            h.stop()
        except Exception:
            pass


@pytest.fixture
def foreign_process(tmp_path):
    """Factory fixture: start(port) -> Popen of a plain node HTTP listener on 127.0.0.1:port."""
    script_path = tmp_path / "foreign_listener.js"
    script_path.write_text(FOREIGN_LISTENER_JS, encoding="utf-8")
    procs: list[subprocess.Popen] = []

    def start(port: int) -> subprocess.Popen:
        proc = subprocess.Popen(
            [NODE, str(script_path), str(port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        procs.append(proc)
        return proc

    yield start

    for p in procs:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                kill_tree(p.pid)
        if p.poll() is None:
            kill_tree(p.pid)


def _select_stale_owner(rows, port: int, src_dir: str):
    """Calls supervisor.js's exported, pure `selectStaleOmniOwner` in a child node process."""
    script = (
        "const {selectStaleOmniOwner} = require(process.argv[1]);"
        "const rows = JSON.parse(process.argv[2]);"
        "const port = Number(process.argv[3]);"
        "const src = process.argv[4];"
        "process.stdout.write(JSON.stringify(selectStaleOmniOwner(rows, port, src)));"
    )
    result = subprocess.run(
        [NODE, "-e", script, str(SUPERVISOR), json.dumps(rows), str(port), src_dir],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"node -e failed (code {result.returncode}): {result.stderr}"
    return json.loads(result.stdout.strip())


# ---------------------------------------------------------------------------------------------------------
# Single instance (CONTRACT §10-11)
# ---------------------------------------------------------------------------------------------------------


def test_single_instance_second_exits_zero(tmp_path, supervisors):
    h1 = supervisors(tmp_path, name="home-a")
    assert h1.wait_health(timeout=10.0), f"first supervisor never became healthy\n{h1.output()}"

    h2 = supervisors(tmp_path, name="home-b", port=h1.port)
    code = h2.wait_exit(timeout=10.0)
    assert code == 0, f"expected exit 0 when our own instance already serves the port, got {code}\n{h2.output()}"


def test_single_instance_foreign_listener_exits_three(tmp_path, supervisors, foreign_process):
    port = free_port()
    foreign_process(port)
    assert wait_until(lambda: _port_open(port), 5.0), "foreign listener never came up"

    h = supervisors(tmp_path, port=port)
    code = h.wait_exit(timeout=10.0)
    assert code == 3, f"expected exit 3 against a foreign listener, got {code}\n{h.output()}"


# ---------------------------------------------------------------------------------------------------------
# Worker respawn (CONTRACT §10)
# ---------------------------------------------------------------------------------------------------------


def test_worker_crash_respawns_and_serves_health_again(tmp_path, supervisors):
    h = supervisors(tmp_path)
    first = h.wait_health(timeout=10.0)
    assert first, f"worker never became healthy\n{h.output()}"
    old_pid = first["pid"]

    kill_tree(old_pid)

    # Design target is WORKER_RESPAWN_MS (250ms) plus node startup, i.e. "within ~1s"; this box can be
    # busy with sibling agents, so the bound below has slack without being a no-op assertion.
    second = wait_until(lambda: _health_with_new_pid(h.port, old_pid), 5.0)
    assert second, f"worker did not respawn with a new pid within 5s\n{h.output()}"
    assert second["pid"] != old_pid
    assert not pid_alive(old_pid)


# ---------------------------------------------------------------------------------------------------------
# OmniRoute child (CONTRACT §10, §16)
# ---------------------------------------------------------------------------------------------------------


def test_omniroute_env_secrets_and_log_redaction(tmp_path, supervisors):
    runs_dir = tmp_path / "omni-runs"
    omni_src = tmp_path / "omni-src"
    omni_src.mkdir()
    fake_cmd = omni_src / "fake_omniroute.mjs"
    fake_cmd.write_text(render_fake_omniroute(runs_dir), encoding="utf-8")

    omni_port = free_port()
    # runtime_dir must point at wherever the fake omniroute-cmd script actually lives: the supervisor
    # spawns it with that directory as cwd, and a missing cwd fails the spawn (CONTRACT's default,
    # HOME_DIR/omniroute-src, is not where these tests put it).
    config = {"python_exe": sys.executable, "omniroute": {"memory_mb": 256, "runtime_dir": str(omni_src)}}
    bin_files = {"lane_key.py": render_lane_key(), "spillover_alert.py": FAKE_ALERT}

    h = supervisors(
        tmp_path,
        config=config,
        bin_files=bin_files,
        extra_args=["--omniroute-base", f"http://127.0.0.1:{omni_port}", "--omniroute-cmd", str(fake_cmd)],
    )
    assert h.wait_health(timeout=10.0), f"worker never became healthy\n{h.output()}"

    # The Windows stale-listener probe (a PowerShell + WMI query) plus four sequential secret fetches
    # can take several seconds on a loaded box -- generous timeout rather than tuning to the happy path.
    run_file = wait_until(
        lambda: (sorted(runs_dir.glob("*.json")) or [None])[0] if runs_dir.exists() else None,
        timeout=30.0,
    )
    assert run_file, f"omniroute never started\n{h.output()}"
    rec = json.loads(run_file.read_text(encoding="utf-8"))
    env = rec["env"]

    assert not any(k.upper().startswith(("ANTHROPIC_", "OPENAI_", "CLAUDE_")) for k in env), sorted(env)
    for key in ("PORT", "API_PORT", "DASHBOARD_PORT", "REQUIRE_API_KEY", "OMNIROUTE_SERVER_HOST", "DATA_DIR"):
        assert key in env, f"{key} missing from omniroute env: {sorted(env)}"
    assert env["PORT"] == env["API_PORT"] == env["DASHBOARD_PORT"] == str(omni_port)
    assert env["REQUIRE_API_KEY"] == "true"
    assert env["OMNIROUTE_SERVER_HOST"] == "127.0.0.1"

    for env_name, value in ALL_OMNI_SECRETS.items():
        assert env.get(env_name) == value, f"{env_name} missing or wrong in omniroute env"

    argv_text = json.dumps(rec["argv"])
    for value in ALL_OMNI_SECRETS.values():
        assert value not in argv_text, f"secret leaked into argv: {argv_text}"

    log_file = h.state_dir / "logs" / "omniroute.log"
    log_text = (
        wait_until(
            lambda: log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else None,
            timeout=10.0,
        )
        or ""
    )
    assert "fake omniroute up" in log_text, f"omniroute.log missing the expected line: {log_text!r}"
    for value in ALL_OMNI_SECRETS.values():
        assert value not in log_text, f"secret leaked into omniroute.log: {log_text!r}"
    assert "<redacted>" in log_text


def test_omniroute_missing_secret_prevents_start(tmp_path, supervisors):
    runs_dir = tmp_path / "omni-runs"
    omni_src = tmp_path / "omni-src"
    omni_src.mkdir()
    fake_cmd = omni_src / "fake_omniroute.mjs"
    fake_cmd.write_text(render_fake_omniroute(runs_dir), encoding="utf-8")

    omni_port = free_port()
    # runtime_dir must point at wherever the fake omniroute-cmd script actually lives: the supervisor
    # spawns it with that directory as cwd, and a missing cwd fails the spawn (CONTRACT's default,
    # HOME_DIR/omniroute-src, is not where these tests put it).
    config = {"python_exe": sys.executable, "omniroute": {"memory_mb": 256, "runtime_dir": str(omni_src)}}
    bin_files = {
        "lane_key.py": render_lane_key(missing=("jwt_secret",)),
        "spillover_alert.py": FAKE_ALERT,
    }

    h = supervisors(
        tmp_path,
        config=config,
        bin_files=bin_files,
        extra_args=["--omniroute-base", f"http://127.0.0.1:{omni_port}", "--omniroute-cmd", str(fake_cmd)],
    )
    assert h.wait_health(timeout=10.0), f"worker never became healthy\n{h.output()}"

    alerts_file = h.home / "alerts.jsonl"
    fired = wait_until(
        lambda: alerts_file.read_text(encoding="utf-8") if alerts_file.exists() else None,
        timeout=30.0,
    )
    assert fired, f"omniroute_secrets_missing alert never fired\n{h.output()}"
    assert "omniroute_secrets_missing" in fired

    assert not runs_dir.exists() or not list(runs_dir.glob("*.json")), "omniroute started despite a missing secret"


# ---------------------------------------------------------------------------------------------------------
# Shutdown (CONTRACT §10)
# ---------------------------------------------------------------------------------------------------------


def test_stop_file_shuts_down_worker_and_omniroute(tmp_path, supervisors):
    runs_dir = tmp_path / "omni-runs"
    omni_src = tmp_path / "omni-src"
    omni_src.mkdir()
    fake_cmd = omni_src / "fake_omniroute.mjs"
    fake_cmd.write_text(render_fake_omniroute(runs_dir), encoding="utf-8")

    omni_port = free_port()
    # runtime_dir must point at wherever the fake omniroute-cmd script actually lives: the supervisor
    # spawns it with that directory as cwd, and a missing cwd fails the spawn (CONTRACT's default,
    # HOME_DIR/omniroute-src, is not where these tests put it).
    config = {"python_exe": sys.executable, "omniroute": {"memory_mb": 256, "runtime_dir": str(omni_src)}}
    bin_files = {"lane_key.py": render_lane_key(), "spillover_alert.py": FAKE_ALERT}

    h = supervisors(
        tmp_path,
        config=config,
        bin_files=bin_files,
        extra_args=["--omniroute-base", f"http://127.0.0.1:{omni_port}", "--omniroute-cmd", str(fake_cmd)],
    )
    hh = h.wait_health(timeout=10.0)
    assert hh, f"worker never became healthy\n{h.output()}"
    worker_pid = hh["pid"]

    run_file = wait_until(
        lambda: (sorted(runs_dir.glob("*.json")) or [None])[0] if runs_dir.exists() else None,
        timeout=30.0,
    )
    assert run_file, f"omniroute never started\n{h.output()}"
    omni_pid = json.loads(run_file.read_text(encoding="utf-8"))["pid"]

    assert h.pidfile.exists()
    supervisor_pid = int(h.pidfile.read_text(encoding="utf-8").strip())

    h.stopfile.write_text("", encoding="utf-8")
    code = h.wait_exit(timeout=15.0)
    assert code == 0, f"expected a clean exit 0 from the stop file, got {code}\n{h.output()}"

    assert not h.pidfile.exists(), "pid file was not removed on shutdown"
    assert not h.stopfile.exists(), "stop file was not removed on shutdown"
    assert not pid_alive(worker_pid), "proxy worker survived shutdown"
    assert not pid_alive(omni_pid), "omniroute child survived shutdown"
    assert not pid_alive(supervisor_pid), "supervisor process survived its own shutdown"


# ---------------------------------------------------------------------------------------------------------
# Stale OmniRoute listener selection: a pure function of a process table (CONTRACT §10), unit-tested
# directly (through supervisor.js's module.exports) with a fabricated table -- no real netstat/PowerShell
# involved.
# ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "port", "src_dir", "expected"),
    [
        pytest.param(
            [{"pid": 111, "port": 20128, "state": "LISTENING", "commandLine": r"node C:\home\omniroute-src\bin\omniroute.mjs serve"}],
            20128,
            r"C:\home\omniroute-src",
            111,
            id="match",
        ),
        pytest.param(
            [{"pid": 111, "port": 20128, "state": "ESTABLISHED", "commandLine": r"node C:\home\omniroute-src\bin\omniroute.mjs serve"}],
            20128,
            r"C:\home\omniroute-src",
            None,
            id="not-listening",
        ),
        pytest.param(
            [{"pid": 111, "port": 9999, "state": "LISTENING", "commandLine": r"node C:\home\omniroute-src\bin\omniroute.mjs serve"}],
            20128,
            r"C:\home\omniroute-src",
            None,
            id="wrong-port",
        ),
        pytest.param(
            [{"pid": 111, "port": 20128, "state": "LISTENING", "commandLine": r"C:\chrome.exe --profile"}],
            20128,
            r"C:\home\omniroute-src",
            None,
            id="different-process-owns-the-port",
        ),
        pytest.param(
            [
                {"pid": 111, "port": 20128, "state": "LISTENING", "commandLine": "unrelated.exe"},
                {"pid": 222, "port": 20128, "state": "LISTENING", "commandLine": r"node C:\home\omniroute-src\bin\omniroute.mjs serve"},
            ],
            20128,
            r"C:\home\omniroute-src",
            222,
            id="second-row-matches",
        ),
        pytest.param([], 20128, r"C:\home\omniroute-src", None, id="empty-table"),
        pytest.param(
            [{"pid": 1, "port": 20128, "state": "LISTENING", "commandLine": "anything"}],
            20128,
            "",
            None,
            id="no-src-dir-never-matches",
        ),
    ],
)
def test_select_stale_omni_owner_pure_function(rows, port, src_dir, expected):
    assert _select_stale_owner(rows, port, src_dir) == expected
