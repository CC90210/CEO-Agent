from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

CORE = Path(__file__).resolve().parents[1] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import cron_dispatcher as dispatcher  # noqa: E402


def test_dispatcher_uses_canonical_timeout_key(monkeypatch, tmp_path):
    seen = {}
    job = {
        "id": "job-1",
        "name": "Atlas pulse",
        "action_type": "atlas_pulse_publish",
        "action_config": {"timeout": 777, "timeout_seconds": 111},
        "run_count": 0,
        "schedule": "0 0 * * *",
    }
    monkeypatch.setattr(dispatcher, "_job_command", lambda _job: (["python", "x.py"], tmp_path))
    monkeypatch.setattr(dispatcher, "load_env", lambda: {})
    monkeypatch.setattr(dispatcher, "_update_run_state", lambda *_args: None)

    def fake_run(*_args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(dispatcher.subprocess, "run", fake_run)

    result = dispatcher.execute_job(object(), job)

    assert result["ok"] is True
    assert seen["timeout"] == 777
