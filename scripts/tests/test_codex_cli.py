"""Subscription-only Codex fallback runner contracts."""
from __future__ import annotations

import subprocess

from lib import codex_cli


def test_prompt_uses_stdin_and_success_comes_from_last_message(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "C:/npm/codex.cmd")
    monkeypatch.setattr(
        codex_cli,
        "command_without_cmd_shim",
        lambda _p: ["C:/node.exe", "C:/npm/codex.js"],
    )
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        out = cmd[cmd.index("--output-last-message") + 1]
        open(out, "w", encoding="utf-8").write("Codex recovered")
        return subprocess.CompletedProcess(cmd, 0, stdout="noise", stderr="")

    monkeypatch.setattr(codex_cli, "safe_run", fake_run)
    prompt = "private lead text that must never enter argv"
    result = codex_cli.run_codex_cli(
        prompt,
        system="You are Bravo.",
        cwd=tmp_path,
        sandbox="read-only",
        respect_rules=False,
        operator_trusted=True,
    )

    assert result == "Codex recovered"
    assert prompt not in " ".join(seen["cmd"])
    assert prompt in seen["kwargs"]["input"]
    assert "--ephemeral" in seen["cmd"]
    assert "--ignore-user-config" in seen["cmd"]
    assert "--ignore-rules" in seen["cmd"]
    assert seen["cmd"][-1] == "-"


def test_fallback_child_inherits_only_runtime_allowlist_not_business_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "codex")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN", "must-not-reach-child")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "must-not-reach-child")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "must-not-reach-child")
    monkeypatch.setenv("PATH", "C:/safe/bin")
    monkeypatch.setenv("USERPROFILE", "C:/Users/Test")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs["env"])
        out = cmd[cmd.index("--output-last-message") + 1]
        open(out, "w", encoding="utf-8").write("ok")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(codex_cli, "safe_run", fake_run)
    assert codex_cli.run_codex_cli(
        "hello", cwd=tmp_path, operator_trusted=True
    ) == "ok"
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        assert key not in captured
    assert captured["USERPROFILE"] == "C:/Users/Test"
    assert captured["CI"] == "true"


def test_nonzero_output_is_failure_not_user_visible_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "codex")
    monkeypatch.setattr(
        codex_cli,
        "safe_run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="provider diagnostic"
        ),
    )
    assert codex_cli.run_codex_cli(
        "hello", cwd=tmp_path, operator_trusted=True
    ) is None


def test_workspace_write_can_respect_repo_rules(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "codex")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        out = cmd[cmd.index("--output-last-message") + 1]
        open(out, "w", encoding="utf-8").write("done")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(codex_cli, "safe_run", fake_run)
    assert codex_cli.run_codex_cli(
        "build it", cwd=tmp_path, sandbox="workspace-write", respect_rules=True,
        operator_trusted=True,
    ) == "done"
    assert "workspace-write" in seen["cmd"]
    assert "--ignore-user-config" in seen["cmd"]
    assert "--ignore-rules" not in seen["cmd"]


def test_direct_untrusted_call_is_refused_before_spawn(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "codex")
    called = False

    def fake_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("untrusted Codex call reached the process boundary")

    monkeypatch.setattr(codex_cli, "safe_run", fake_run)
    assert codex_cli.run_codex_cli("inbound email", cwd=tmp_path) is None
    assert called is False


def test_authenticated_probe_requires_successful_login_status(monkeypatch):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "codex")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="logged in")

    monkeypatch.setattr(codex_cli, "safe_run", fake_run)
    assert codex_cli.is_codex_authenticated() is True
    assert seen["cmd"][-2:] == ["login", "status"]
    assert seen["kwargs"]["stdin"] is subprocess.DEVNULL


def test_authenticated_probe_rejects_installed_but_logged_out(monkeypatch):
    monkeypatch.setattr(codex_cli, "resolve_codex_bin", lambda: "codex")
    monkeypatch.setattr(
        codex_cli,
        "safe_run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, stdout="", stderr=""),
    )
    assert codex_cli.is_codex_authenticated() is False
