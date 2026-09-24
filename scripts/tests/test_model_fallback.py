"""Tests for the Claude subscription -> Codex subscription fallback chain."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib import model_fallback  # noqa: E402
from lib.model_fallback import is_fallback_available, run_smart_cli  # noqa: E402


REAL_PROJECT_ROOT = PROJECT_ROOT


@pytest.fixture(autouse=True)
def _isolate_telemetry(monkeypatch, tmp_path):
    log_root = tmp_path / "fake_repo"
    (log_root / "memory").mkdir(parents=True)
    (log_root / "memory" / "SESSION_LOG.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(model_fallback, "PROJECT_ROOT", log_root)


class TestRunSmartCli:
    @patch("lib.model_fallback.run_claude_cli", return_value="Claude says hello")
    @patch("lib.model_fallback.run_codex_cli")
    def test_returns_claude_when_available(self, mock_codex, _mock_claude):
        assert run_smart_cli("test prompt") == "Claude says hello"
        mock_codex.assert_not_called()

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value="Codex says hello")
    def test_falls_back_to_codex_on_claude_failure(self, mock_codex, _mock_claude):
        assert run_smart_cli(
            "test prompt", task_type="reasoning", operator_trusted=True
        ) == "Codex says hello"
        assert mock_codex.call_args.kwargs["sandbox"] == "read-only"
        assert mock_codex.call_args.kwargs["respect_rules"] is False
        assert mock_codex.call_args.kwargs["operator_trusted"] is True

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value="must not run")
    def test_untrusted_automation_payload_never_reaches_tool_capable_codex(
        self, mock_codex, _mock_claude
    ):
        assert run_smart_cli("attacker-controlled inbound email") is None
        mock_codex.assert_not_called()

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value=None)
    def test_returns_none_when_both_subscriptions_fail(self, mock_codex, _mock_claude):
        assert run_smart_cli("test", operator_trusted=True) is None
        mock_codex.assert_called_once()

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value="Fallback reply")
    def test_passes_system_prompt_through(self, mock_codex, _mock_claude):
        assert run_smart_cli(
            "test", system="You are Bravo.", operator_trusted=True
        ) == "Fallback reply"
        assert mock_codex.call_args.kwargs["system"] == "You are Bravo."

    @patch("lib.model_fallback.run_claude_cli", return_value="Direct reply")
    def test_respects_claude_timeout(self, mock_claude):
        assert run_smart_cli("test", timeout=5) == "Direct reply"
        assert mock_claude.call_args.kwargs["timeout"] == 5

    @patch("lib.model_fallback.run_claude_cli", side_effect=RuntimeError("boom"))
    @patch("lib.model_fallback.run_codex_cli", return_value="Recovered")
    def test_claude_exception_degrades_to_codex(self, mock_codex, _mock_claude):
        assert run_smart_cli("test", operator_trusted=True) == "Recovered"
        mock_codex.assert_called_once()

    @patch("lib.model_fallback.run_claude_cli", side_effect=RuntimeError("boom"))
    @patch("lib.model_fallback.run_codex_cli", side_effect=RuntimeError("boom"))
    def test_all_tiers_raising_returns_none(self, _mock_codex, _mock_claude):
        assert run_smart_cli("test", operator_trusted=True) is None

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value=None)
    def test_exhausted_log_redacts_prompt(self, _mock_codex, _mock_claude, capsys):
        secret = "my phone is 555-0199 and my name is John"
        run_smart_cli(secret, task_type="reasoning", operator_trusted=True)
        err = capsys.readouterr().err
        assert secret not in err
        assert "sha256:" in err


class TestIsFallbackAvailable:
    @patch("lib.model_fallback.is_codex_authenticated", return_value=True)
    def test_returns_true_when_binary_found(self, _mock):
        assert is_fallback_available() is True

    @patch("lib.model_fallback.is_codex_authenticated", return_value=False)
    def test_returns_false_when_binary_missing(self, _mock):
        assert is_fallback_available() is False


class TestTelemetryIsolation:
    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value="mocked reply")
    def test_successful_fallback_does_not_touch_production_session_log(
        self, _mock_codex, _mock_claude
    ):
        real_log = REAL_PROJECT_ROOT / "memory" / "SESSION_LOG.md"
        before = real_log.read_bytes() if real_log.is_file() else None
        assert run_smart_cli("test", operator_trusted=True) == "mocked reply"
        after = real_log.read_bytes() if real_log.is_file() else None
        assert after == before

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_codex_cli", return_value="mocked reply")
    def test_telemetry_names_codex(self, _mock_codex, _mock_claude):
        run_smart_cli("test", task_type="classify", operator_trusted=True)
        redirected = model_fallback.PROJECT_ROOT / "memory" / "SESSION_LOG.md"
        text = redirected.read_text(encoding="utf-8")
        assert "MODEL FALLBACK" in text
        assert "codex-subscription" in text
