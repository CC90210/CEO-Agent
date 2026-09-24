"""Dashboard scripts must use the verified Windows system CA store."""
from __future__ import annotations

import subprocess
import sys

import run_dashboard_script as runner


def test_node_child_uses_system_ca(monkeypatch, tmp_path):
    script = tmp_path / "scripts" / "probe.ts"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(runner, "DASHBOARD_DIR", tmp_path)
    monkeypatch.setattr(runner, "dashboard_env", lambda: {"PATH": "safe"})
    monkeypatch.setattr(sys, "argv", ["run_dashboard_script.py", "scripts/probe.ts"])
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(runner, "safe_run", fake_run)
    assert runner.main() == 0
    assert seen["cmd"][:2] == ["node", "--use-system-ca"]
