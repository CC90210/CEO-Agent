"""Quota should defer the noncritical sleep pass, not create a broken-cron alert."""
from __future__ import annotations

import argparse

import bravo_sleep as sleep


def test_quota_deferred_sleep_requests_retry_without_claiming_a_run(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sleep, "LAST_RUN_PATH", tmp_path / "last_run.txt")
    monkeypatch.setattr(sleep, "_recent_session_log", lambda _hours: "activity")
    monkeypatch.setattr(sleep, "_recent_git_log", lambda _hours: "commits")
    monkeypatch.setattr(
        sleep,
        "_call_model",
        lambda _prompt: (_ for _ in ()).throw(sleep.ModelQuotaDeferred(900)),
    )
    args = argparse.Namespace(window_hours=24, dry_run=False)

    assert sleep.cmd_run(args) == sleep.DEFERRED_EXIT_CODE
    assert not sleep.LAST_RUN_PATH.exists()
    output = capsys.readouterr().out
    assert "deferred" in output.lower()
    assert "retry_after=900" in output


def test_nonquota_auth_or_runtime_failure_still_fails_loud(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sleep, "LAST_RUN_PATH", tmp_path / "last_run.txt")
    monkeypatch.setattr(sleep, "_recent_session_log", lambda _hours: "activity")
    monkeypatch.setattr(sleep, "_recent_git_log", lambda _hours: "commits")
    monkeypatch.setattr(
        sleep,
        "_call_model",
        lambda _prompt: (_ for _ in ()).throw(RuntimeError("authentication failed")),
    )
    args = argparse.Namespace(window_hours=24, dry_run=False)

    assert sleep.cmd_run(args) == 3
    assert "model call failed" in capsys.readouterr().err.lower()


def test_quota_during_duplicate_judgment_defers_before_any_write(
    monkeypatch, tmp_path, capsys
):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    target = memory_dir / "MISTAKES.md"
    target.write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(sleep, "MEMORY_DIR", memory_dir)
    monkeypatch.setattr(sleep, "LAST_RUN_PATH", tmp_path / "last_run.txt")
    monkeypatch.setattr(sleep, "COOLDOWN_PATH", tmp_path / "cooldowns.json")
    monkeypatch.setattr(sleep, "MEMORY_DIFF_DIR", tmp_path / "memory_diff")
    monkeypatch.setattr(sleep, "_recent_session_log", lambda _hours: "activity")
    monkeypatch.setattr(sleep, "_recent_git_log", lambda _hours: "commits")
    monkeypatch.setattr(
        sleep,
        "_near_duplicates",
        lambda _title, _body: [{"ref": "MISTAKES.md#old", "snippet": "similar"}],
    )

    calls = 0

    def model_call(_prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            return '[{"file":"MISTAKES","title":"new lesson","body":"details"}]'
        raise sleep.ModelQuotaDeferred(600)

    monkeypatch.setattr(sleep, "_call_model", model_call)
    args = argparse.Namespace(window_hours=24, dry_run=False)

    assert sleep.cmd_run(args) == sleep.DEFERRED_EXIT_CODE
    assert calls == 2
    assert target.read_text(encoding="utf-8") == "original\n"
    assert not sleep.LAST_RUN_PATH.exists()
    assert not sleep.COOLDOWN_PATH.exists()
    assert not sleep.MEMORY_DIFF_DIR.exists()
    output = capsys.readouterr().out
    assert "retry_after=600" in output
    assert "no memory files changed" in output
