"""Fallback health messages must describe the live trust-scoped ladder."""
from __future__ import annotations

import pytest

import harness_eval
import model_router
from lib import claude_cli, model_fallback


def test_harness_names_codex_and_does_not_promise_untrusted_automation_fallback(monkeypatch):
    monkeypatch.setattr(claude_cli, "run_claude_cli", lambda *_a, **_kw: None)
    monkeypatch.setattr(model_fallback, "is_fallback_available", lambda: True)

    ok, message = harness_eval.check_model_call_path()

    assert ok is False
    assert "Codex" in message
    assert "authenticated operator" in message
    assert "opencode" not in message.lower()
    assert "automations degrade" not in message.lower()


def test_model_router_failure_explains_why_codex_was_not_attempted(monkeypatch):
    monkeypatch.setattr(model_router, "load_env", lambda: {})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(model_fallback, "run_smart_cli", lambda *_a, **_kw: None)

    with pytest.raises(RuntimeError) as exc:
        model_router.call(
            [{"role": "user", "content": "classify this inbound payload"}],
            model="claude-sonnet-4-6",
        )

    message = str(exc.value)
    assert "Codex was not attempted" in message
    assert "operator-authenticated" in message
    assert "opencode" not in message.lower()
