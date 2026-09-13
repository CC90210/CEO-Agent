"""Tests for scripts/spillover/ensure_spillover.py, the user SessionStart hook
(CONTRACT.md sections 10 and 12).

All three documented outcomes (healthy+direct / spilling / down) are covered
with probe_health and spawn_supervisor monkeypatched: this file never makes a
real network probe against a live proxy and never spawns a real process.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess as real_subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENSURE = REPO_ROOT / "scripts" / "spillover" / "ensure_spillover.py"
PYTHON = sys.executable

# The REAL install (never touched by this suite - see the isolation guard below).
_REAL_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
_REAL_BRAVO_SPILLOVER_HOME = _REAL_LOCALAPPDATA / "bravo-spillover"


# Only the subpaths this feature's own tools ever write to (CONTRACT.md
# section 2: secrets/, state/, bin/, app/, config.json). NEVER walk the whole
# HOME_DIR - omniroute-src/ and omniroute-npm/ are a full git checkout + a
# built Next.js app + node_modules (hundreds of thousands of files, another
# agent's live build in this same session); rglob("*") over the whole tree
# hung for minutes and would have raced that build for no reason - nothing
# in lane_key.py/statusline.py/ensure_spillover.py/spillover_alert.py ever
# touches those two directories.
_WATCHED_SUBPATHS = ("secrets", "state", "bin", "app", "config.json")


def _snapshot(root: Path):
    """None if root doesn't exist; otherwise a sorted list of every relative
    path under the watched subpaths. Two snapshots differing is proof one of
    THESE tools wrote there."""
    if not root.exists():
        return None
    paths: list[str] = []
    for name in _WATCHED_SUBPATHS:
        sub = root / name
        if sub.is_file():
            paths.append(name)
        elif sub.is_dir():
            paths.extend(str(p.relative_to(root)) for p in sub.rglob("*"))
    return sorted(paths)


@pytest.fixture(autouse=True)
def _isolated_spillover_home(tmp_path, monkeypatch):
    """home_dir() in lane_key/statusline/ensure_spillover/spillover_alert all
    resolve HOME_DIR at CALL time from BRAVO_SPILLOVER_HOME (verified by
    reading each of the four files) - the isolation gap was never that env
    var not being honoured, it was tests (here, run()/main() calls) not
    SETTING it. This makes every test in this file set both BRAVO_SPILLOVER_HOME
    and LOCALAPPDATA to a fresh tmp_path before it runs, so a spec function
    that forgets to pass a home explicitly still can't reach the real install."""
    home = tmp_path / "bravo-spillover"
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData-Local"))
    return home


@pytest.fixture(scope="session", autouse=True)
def _guard_real_bravo_spillover_untouched():
    """Session-wide proof, not just per-test hope: snapshot the REAL
    %LOCALAPPDATA%/bravo-spillover before this file's tests run and assert it
    is byte-for-byte the same set of paths afterward. Any test that leaks
    through to the real install (missing an env override, a bug in home_dir()
    resolution, or a future test that forgets isolation) fails this loudly
    instead of leaving a silent artifact for CC to find during deploy."""
    before = _snapshot(_REAL_BRAVO_SPILLOVER_HOME)
    yield
    after = _snapshot(_REAL_BRAVO_SPILLOVER_HOME)
    assert after == before, (
        f"a test touched the REAL {_REAL_BRAVO_SPILLOVER_HOME} "
        f"(before={before!r}, after={after!r})"
    )


def _load_module():
    spec = importlib.util.spec_from_file_location("ensure_spillover_probe", ENSURE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def es():
    """A fresh module per test - module-level constants get monkeypatched
    per-test (e.g. RESTART_WAIT_S) and must not leak between tests."""
    return _load_module()


def _healthy(mode="direct", reset_at=None, fallback_healthy=True, instance_id="abc-123"):
    return {"ok": True, "instance_id": instance_id, "pid": 4242, "version": "deadbeef",
            "config_mode": "spill", "mode": mode, "reset_at": reset_at,
            "fallback_healthy": fallback_healthy}


class _NonTTYStdin:
    """A stand-in for sys.stdin that reports non-interactive without needing
    a real pipe - main()'s isatty()==True fast path never touches .buffer."""
    def isatty(self):
        return True


# -------------------------------------------------------- case 1: healthy/direct ---

def test_healthy_direct_returns_none_and_never_spawns(es, monkeypatch):
    monkeypatch.setattr(es, "probe_health", lambda host, port: _healthy(mode="direct"))

    def boom(*_a, **_k):
        raise AssertionError("spawn_supervisor must not be called when healthy")
    monkeypatch.setattr(es, "spawn_supervisor", boom)
    assert es.run() is None


def test_healthy_direct_main_prints_nothing(es, monkeypatch, capsys):
    monkeypatch.setattr(es, "probe_health", lambda host, port: _healthy(mode="direct"))
    monkeypatch.setattr(es, "spawn_supervisor",
                        lambda home: (_ for _ in ()).throw(AssertionError("no spawn expected")))
    monkeypatch.setattr(sys, "stdin", _NonTTYStdin())
    rc = es.main()
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_healthy_direct_is_fast(es, monkeypatch):
    """Under 150ms (CONTRACT: 'healthy, direct: silent, under 150 ms').
    Measured in-process with the network probe stubbed to something
    instantaneous, isolating the hook's own logic from real socket I/O."""
    monkeypatch.setattr(es, "probe_health", lambda host, port: _healthy(mode="direct"))
    start = time.perf_counter()
    for _ in range(50):
        es.run()
    elapsed = time.perf_counter() - start
    per_call = elapsed / 50
    assert per_call < 0.15, f"average run() took {per_call * 1000:.2f}ms (budget 150ms)"


# ------------------------------------------------------------ case 2: spilling ---

def test_spilling_healthy_fallback_returns_context(es, monkeypatch):
    reset_at = time.time() + 1800
    monkeypatch.setattr(es, "probe_health",
                        lambda host, port: _healthy(mode="spilling", reset_at=reset_at, fallback_healthy=True))
    ctx = es.run()
    assert ctx is not None
    assert ctx.startswith("FALLBACK active until ")
    assert "GPT" in ctx


def test_spilling_down_fallback_returns_down_context(es, monkeypatch):
    reset_at = time.time() + 1800
    monkeypatch.setattr(es, "probe_health",
                        lambda host, port: _healthy(mode="spilling", reset_at=reset_at, fallback_healthy=False))
    ctx = es.run()
    assert ctx is not None
    assert "fallback is DOWN" in ctx
    assert "doctor" in ctx


def test_spilling_with_no_reset_says_the_limit_resets(es, monkeypatch):
    monkeypatch.setattr(es, "probe_health", lambda host, port: _healthy(mode="spilling", reset_at=None))
    ctx = es.run()
    assert "the limit resets" in ctx


def test_spilling_emits_session_start_hook_json(es, monkeypatch, capsys):
    reset_at = time.time() + 1800
    monkeypatch.setattr(es, "probe_health", lambda host, port: _healthy(mode="spilling", reset_at=reset_at))
    monkeypatch.setattr(sys, "stdin", _NonTTYStdin())
    rc = es.main()
    assert rc == 0
    out = capsys.readouterr().out.strip()
    doc = json.loads(out)
    assert doc["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    ctx = doc["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("## Claude Spillover\n")
    assert "FALLBACK active until" in ctx


def test_context_for_healthy_direct_is_none(es):
    assert es.context_for(_healthy(mode="direct")) is None


# ------------------------------------------------------------------ case 3: down ---

def test_down_with_spawn_error_reports_immediately_without_waiting(es, monkeypatch):
    monkeypatch.setattr(es, "probe_health", lambda host, port: None)
    calls = []

    def fake_spawn(home):
        calls.append(home)
        return "supervisor.js is not deployed"
    monkeypatch.setattr(es, "spawn_supervisor", fake_spawn)

    start = time.perf_counter()
    ctx = es.run()
    elapsed = time.perf_counter() - start

    assert calls, "spawn_supervisor should have been called exactly once"
    assert ctx == f"proxy DOWN (supervisor.js is not deployed) - {es.DOWN_ADVICE}"
    assert elapsed < 1.0, "an immediate spawn error must not enter the retry-wait loop"


def test_down_then_recovers_after_spawn(es, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_probe(host, port):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the initial probe: down
        return _healthy(mode="direct")  # recovered after the (fake) spawn

    monkeypatch.setattr(es, "probe_health", fake_probe)
    monkeypatch.setattr(es, "spawn_supervisor", lambda home: None)  # "started" successfully
    assert es.run() == "proxy restarted"


def test_down_stays_down_after_the_wait_window(es, monkeypatch):
    monkeypatch.setattr(es, "RESTART_WAIT_S", 0.05)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(es, "probe_health", lambda host, port: None)
    monkeypatch.setattr(es, "spawn_supervisor", lambda home: None)
    assert es.run() == f"proxy DOWN - {es.DOWN_ADVICE}"


def test_down_recovery_also_carries_spilling_context(es, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    reset_at = time.time() + 900
    calls = {"n": 0}

    def fake_probe(host, port):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return _healthy(mode="spilling", reset_at=reset_at)

    monkeypatch.setattr(es, "probe_health", fake_probe)
    monkeypatch.setattr(es, "spawn_supervisor", lambda home: None)
    ctx = es.run()
    assert ctx.startswith("proxy restarted. FALLBACK active until")


def test_down_main_emits_the_down_advice_as_context(es, monkeypatch, capsys):
    monkeypatch.setattr(es, "RESTART_WAIT_S", 0.02)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(es, "probe_health", lambda host, port: None)
    monkeypatch.setattr(es, "spawn_supervisor", lambda home: None)
    monkeypatch.setattr(sys, "stdin", _NonTTYStdin())
    rc = es.main()
    assert rc == 0
    doc = json.loads(capsys.readouterr().out.strip())
    assert "DOWN" in doc["hookSpecificOutput"]["additionalContext"]


# ------------------------------------------------------ spawn_supervisor itself ---

def test_spawn_supervisor_missing_file_is_reported(es, tmp_path):
    err = es.spawn_supervisor(str(tmp_path))
    assert err == "supervisor.js is not deployed"


def test_spawn_supervisor_missing_node_is_reported(es, tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    (app / "supervisor.js").write_text("// stub", encoding="utf-8")
    import shutil as real_shutil
    monkeypatch.setattr(real_shutil, "which", lambda name: None)
    err = es.spawn_supervisor(str(tmp_path))
    assert err == "node is not on PATH"


def test_spawn_supervisor_builds_the_documented_command_and_never_really_spawns(es, tmp_path, monkeypatch):
    """CONTRACT section 10: 'spawn node --use-system-ca HOME_DIR/app/supervisor.js
    detached and windowless'. Popen itself is replaced so this test NEVER
    starts a real process."""
    app = tmp_path / "app"
    app.mkdir()
    supervisor_path = app / "supervisor.js"
    supervisor_path.write_text("// stub", encoding="utf-8")

    import shutil as real_shutil
    monkeypatch.setattr(real_shutil, "which", lambda name: "C:/fake/node.exe" if name == "node" else None)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-inherited")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-also-should-not-be-inherited")
    monkeypatch.setenv("CLAUDE_SOMETHING", "also-scrubbed")

    captured = {}

    class FakeProc:
        pid = 999999

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(real_subprocess, "Popen", fake_popen)

    err = es.spawn_supervisor(str(tmp_path))
    assert err is None
    assert "argv" in captured, "Popen was never called"

    argv = captured["argv"]
    assert argv == ["C:/fake/node.exe", "--use-system-ca", str(supervisor_path)]

    kwargs = captured["kwargs"]
    assert kwargs["stdin"] == real_subprocess.DEVNULL
    assert kwargs["stdout"] == real_subprocess.DEVNULL
    assert kwargs["stderr"] == real_subprocess.DEVNULL
    assert kwargs["cwd"] == str(app)
    assert kwargs["close_fds"] is True

    if os.name == "nt":
        flags = kwargs.get("creationflags", 0)
        assert flags & es.CREATE_NO_WINDOW
        assert flags & es.DETACHED_PROCESS

    env = kwargs["env"]
    for scrubbed in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_SOMETHING"):
        assert scrubbed not in env, f"{scrubbed} leaked into the supervisor's spawn env"


def test_spawn_supervisor_reports_popen_failure(es, tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    (app / "supervisor.js").write_text("// stub", encoding="utf-8")
    import shutil as real_shutil
    monkeypatch.setattr(real_shutil, "which", lambda name: "node")

    def fake_popen(*_a, **_k):
        raise OSError(2, "No such file or directory")
    monkeypatch.setattr(real_subprocess, "Popen", fake_popen)

    err = es.spawn_supervisor(str(tmp_path))
    assert err is not None and "spawn failed" in err


# ---------------------------------------------------------------- proxy_addr ---

def test_proxy_addr_defaults(es):
    assert es.proxy_addr({}) == ("127.0.0.1", 20131)


def test_proxy_addr_rejects_a_non_loopback_host(es):
    """CONTRACT section 2: proxy listen is 127.0.0.1, never 0.0.0.0. A
    tampered/malformed config.json must not redirect the probe elsewhere."""
    host, port = es.proxy_addr({"proxy": {"host": "0.0.0.0", "port": 20131}})
    assert host == "127.0.0.1"
    assert port == 20131


def test_proxy_addr_rejects_an_out_of_range_port(es):
    _host, port = es.proxy_addr({"proxy": {"port": 999999}})
    assert port == 20131


def test_proxy_addr_rejects_a_bool_port(es):
    """isinstance(True, int) is True in Python - without an explicit bool
    check, --port true-ish JSON would silently pick port 1."""
    _host, port = es.proxy_addr({"proxy": {"port": True}})
    assert port == 20131


def test_proxy_addr_accepts_localhost(es):
    host, _port = es.proxy_addr({"proxy": {"host": "localhost", "port": 20131}})
    assert host == "localhost"


# ------------------------------------------------------------------ never raises ---

def test_main_never_raises_even_if_run_explodes(es, monkeypatch, capsys):
    def boom():
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(es, "run", boom)
    rc = es.main()
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_drains_stdin_before_running(es, monkeypatch):
    """The hook payload on stdin is read and ignored (CONTRACT section 12) -
    ensure_spillover must not leave it unread or choke on it."""
    monkeypatch.setattr(es, "probe_health", lambda host, port: _healthy(mode="direct"))

    fake_buffer = io.BytesIO(b'{"hook_event_name": "SessionStart"}')

    class FakeStdin:
        buffer = fake_buffer

        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", FakeStdin())
    rc = es.main()
    assert rc == 0
    assert fake_buffer.read() == b""  # fully drained


# ------------------------------------------------------------ real subprocess ---

def test_end_to_end_subprocess_never_hangs_and_exits_0(tmp_path):
    """One real subprocess run, pointed at a HOME_DIR that has never been
    deployed (no app/supervisor.js), so spawn_supervisor's own file-exists
    check refuses before anything could be spawned - the whole script must
    still exit 0 fast. This does open one real loopback socket probe against
    127.0.0.1:20131 (nothing here can mock across a process boundary), so it
    only asserts shape/timing, never a specific message, to stay correct
    regardless of whatever else may be listening on that port."""
    env = dict(os.environ)
    env["BRAVO_SPILLOVER_HOME"] = str(tmp_path / "never-deployed")
    start = time.perf_counter()
    r = real_subprocess.run([PYTHON, "-S", str(ENSURE)], input=b"{}", env=env,
                            capture_output=True, timeout=10)
    elapsed = time.perf_counter() - start
    assert r.returncode == 0
    assert elapsed < 5.0, f"ensure_spillover.py took {elapsed:.2f}s"
    out = r.stdout.decode("utf-8", "replace").strip()
    if out:
        doc = json.loads(out)
        assert doc["hookSpecificOutput"]["hookEventName"] == "SessionStart"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
