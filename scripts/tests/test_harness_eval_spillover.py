"""Tests for harness_eval.check_claude_spillover() (scripts/spillover/CONTRACT.md).

Isolated from the real, actively-developed scripts/integrations/omniroute_tool.py
(owned by another agent in this session) by monkeypatching PROJECT_ROOT to a
scratch directory - this file never depends on that tool existing, being
correct, or being stable while someone else is still writing it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_EVAL = REPO_ROOT / "scripts" / "harness_eval.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("harness_eval_spillover_probe", HARNESS_EVAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hev():
    return _load_module()


@pytest.fixture
def fake_root(tmp_path):
    """A scratch stand-in for PROJECT_ROOT with scripts/integrations/ present
    but empty by default. Tests add omniroute_tool.py only when they need it
    to exist, so the real in-progress file is never touched or relied on."""
    (tmp_path / "scripts" / "integrations").mkdir(parents=True)
    return tmp_path


# ------------------------------------------------------------- not installed ---

def test_not_installed_when_config_json_is_absent(hev, fake_root, monkeypatch, tmp_path):
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    home = tmp_path / "bravo-spillover-not-installed"
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    ok, detail = hev.check_claude_spillover()
    assert ok is True
    assert detail == "not installed"


def test_not_installed_ignores_a_stray_secrets_dir(hev, fake_root, monkeypatch, tmp_path):
    """Presence of anything ELSE under HOME_DIR must not fake 'installed' -
    only config.json's own presence is the gate."""
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    home = tmp_path / "bravo-spillover"
    (home / "secrets").mkdir(parents=True)
    (home / "secrets" / "omniroute_lane.key").write_bytes(b"not-really-a-blob")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    ok, detail = hev.check_claude_spillover()
    assert ok is True
    assert detail == "not installed"


# ------------------------------------------------------------------ tool missing ---

def test_tool_missing_is_a_failure_when_config_json_exists(hev, fake_root, monkeypatch, tmp_path):
    """The exact override this task calls out: if omniroute_tool.py does not
    exist yet, the check must report 'tool missing' as FAILED, never silently
    ok - a deployed-but-undoctorable spillover install is a real gap."""
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    home = tmp_path / "bravo-spillover"
    home.mkdir()
    (home / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    # fake_root/scripts/integrations/omniroute_tool.py is deliberately absent.
    ok, detail = hev.check_claude_spillover()
    assert ok is False
    assert detail == "tool missing"


# --------------------------------------------------------------- doctor result ---

def test_doctor_success_is_ok(hev, fake_root, monkeypatch, tmp_path):
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    tool_path = fake_root / "scripts" / "integrations" / "omniroute_tool.py"
    tool_path.write_text("# stub", encoding="utf-8")
    home = tmp_path / "bravo-spillover"
    home.mkdir()
    (home / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))

    calls = {}

    def fake_run(cmd, timeout=60, env_extra=None):
        calls["cmd"] = cmd
        calls["timeout"] = timeout
        return 0, '{"ok": true}', ""
    monkeypatch.setattr(hev, "_run", fake_run)

    ok, detail = hev.check_claude_spillover()
    assert ok is True
    assert "exit 0" in detail
    assert calls["timeout"] == 45, "spec: doctor gets a 45s budget"
    assert calls["cmd"][0] == sys.executable
    assert calls["cmd"][-2:] == ["doctor", "--json"]
    assert str(tool_path) in calls["cmd"]


def test_doctor_failure_is_reported_not_swallowed(hev, fake_root, monkeypatch, tmp_path):
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    (fake_root / "scripts" / "integrations" / "omniroute_tool.py").write_text("# stub", encoding="utf-8")
    home = tmp_path / "bravo-spillover"
    home.mkdir()
    (home / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))

    monkeypatch.setattr(hev, "_run", lambda *a, **k: (1, "", "OmniRoute unreachable: ECONNREFUSED"))
    ok, detail = hev.check_claude_spillover()
    assert ok is False
    assert "exit 1" in detail
    assert "ECONNREFUSED" in detail


def test_doctor_crash_no_output_is_reported_gracefully(hev, fake_root, monkeypatch, tmp_path):
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    (fake_root / "scripts" / "integrations" / "omniroute_tool.py").write_text("# stub", encoding="utf-8")
    home = tmp_path / "bravo-spillover"
    home.mkdir()
    (home / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))

    monkeypatch.setattr(hev, "_run", lambda *a, **k: (-1, "", ""))
    ok, detail = hev.check_claude_spillover()
    assert ok is False
    assert "no output" in detail


def test_malformed_config_json_still_installed_gate_runs_doctor(hev, fake_root, monkeypatch, tmp_path):
    """config.json existing-but-unparseable is still 'installed' as far as
    this gate cares - it only checks file PRESENCE, never parses it (that is
    machine_parity's job); the doctor call is what actually proves health."""
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    (fake_root / "scripts" / "integrations" / "omniroute_tool.py").write_text("# stub", encoding="utf-8")
    home = tmp_path / "bravo-spillover"
    home.mkdir()
    (home / "config.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(home))
    monkeypatch.setattr(hev, "_run", lambda *a, **k: (0, "{}", ""))
    ok, _detail = hev.check_claude_spillover()
    assert ok is True


# ------------------------------------------------------------------- CHECKS row ---

def test_registered_in_checks_as_documented(hev):
    row = next((c for c in hev.CHECKS if c[0] == "claude spillover sane"), None)
    assert row is not None, "CHECKS is missing the 'claude spillover sane' row"
    _name, fn, model_only, slice_name = row
    assert fn is hev.check_claude_spillover
    assert model_only is False, "this check must run without --with-model"
    assert slice_name == "model-call"


def test_check_runs_cleanly_through_main_with_config_absent(hev, fake_root, monkeypatch, tmp_path, capsys):
    """End-to-end through main()'s own dispatch loop (not just a direct call)
    to prove the row is actually wired in and doesn't crash the run. CHECKS
    and HISTORY_PATH are both scoped to this test so it neither runs the rest
    of the (slow, network-dependent) suite nor writes into the real repo's
    state/harness_eval_history.jsonl."""
    monkeypatch.setattr(hev, "PROJECT_ROOT", fake_root)
    monkeypatch.setattr(hev, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(hev, "CHECKS", [
        ("claude spillover sane", hev.check_claude_spillover, False, "model-call"),
    ])
    monkeypatch.setenv("BRAVO_SPILLOVER_HOME", str(tmp_path / "bravo-spillover-not-installed"))

    rc = hev.main(["--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["pass"] is True
    row = payload["results"][0]
    assert row["check"] == "claude spillover sane"
    assert row["ok"] is True
    assert row["detail"] == "not installed"
    assert rc == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
