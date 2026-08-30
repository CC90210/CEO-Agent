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


# ---------------------------------------------- what the job actually said ---
# Added 2026-08-29 during a self-review. This path stored a bare "ok" and threw
# stdout away, so triggering a job BY HAND — the debugging path, where you most
# need to know what happened — overwrote cron_jobs.last_result with strictly
# less information than the scheduler's previous scheduled run had written.

def _run_dispatch(monkeypatch, stdout, returncode=0, stderr=""):
    from core import cron_dispatcher as cd

    class _Proc:
        pass
    p = _Proc()
    p.stdout, p.stderr, p.returncode = stdout, stderr, returncode
    monkeypatch.setattr(cd.subprocess, "run", lambda *a, **k: p)
    monkeypatch.setattr(cd, "load_env", lambda: {})
    monkeypatch.setattr(cd, "_job_command", lambda job: (["python", "x.py"], "."))
    stored = {}
    monkeypatch.setattr(cd, "_update_run_state",
                        lambda client, job, ok, result: stored.update(
                            ok=ok, result=result))
    cd.execute_job(object(), {"id": "1", "name": "J", "action_type": "script_run"})
    return stored


def test_a_manual_dispatch_records_what_the_job_reported(monkeypatch):
    stored = _run_dispatch(monkeypatch, '{"drained": 3, "remaining": 7}')
    assert stored["ok"] is True
    assert stored["result"] != "ok", "stdout is still being discarded"
    assert "drained=3" in stored["result"] and "remaining=7" in stored["result"]


def test_the_ok_verdict_is_preserved_not_replaced(monkeypatch):
    """Callers and the health check key on the ok/failed prefix. The summary is
    additive; it must not change the verdict's shape."""
    assert _run_dispatch(monkeypatch, "done, 3 scored")["result"].startswith("ok")
    failed = _run_dispatch(monkeypatch, "", returncode=2, stderr="boom")
    assert failed["result"].startswith("failed:2")
    assert "boom" in failed["result"]


def test_silent_stdout_still_stores_the_bare_verdict(monkeypatch):
    assert _run_dispatch(monkeypatch, "")["result"] == "ok"


def test_a_summary_failure_never_breaks_the_dispatch(monkeypatch):
    """The summary is telemetry. A job that ran must never be reported as failed
    because rendering its result raised."""
    from core import cron_dispatcher as cd
    import scheduler
    monkeypatch.setattr(scheduler, "summarize_stdout",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    stored = _run_dispatch(monkeypatch, "real output")
    assert stored["ok"] is True
    assert stored["result"] == "ok"
    assert cd is not None
