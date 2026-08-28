"""test_model_fallback.py — unit tests for scripts/lib/model_fallback.py.

Tests the smart fallback logic: Claude CLI → OpenCode primary → OpenCode
secondary. All subprocess calls are mocked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib import model_fallback  # noqa: E402
from lib.model_fallback import is_fallback_available, run_smart_cli  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_tier_health(monkeypatch, tmp_path):
    """Point the fallback-tier health store at a temp file for every test.

    run_smart_cli records per-(task_type, model) success/failure so a tier that
    keeps timing out gets tried last. Without this fixture those records land in
    the REAL state/model_tier_health.json, which makes these tests
    order-dependent — the tests that deliberately fail the primary tier record
    consecutive failures, and after three of them the ordering flips and the
    "primary is tried first" assertions below fail. It also means a test run
    would demote a production model tier, which is worse than the flakiness.
    """
    monkeypatch.setattr(model_fallback, "TIER_HEALTH_PATH",
                        tmp_path / "model_tier_health.json")


class TestRunSmartCli:
    """Test the fallback chain: Claude → OpenCode primary → OpenCode secondary."""

    @patch("lib.model_fallback.run_claude_cli", return_value="Claude says hello")
    @patch("lib.model_fallback.run_opencode_cli")
    def test_returns_claude_when_available(self, mock_oc, mock_claude):
        result = run_smart_cli("test prompt")
        assert result == "Claude says hello"
        mock_oc.assert_not_called()

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_opencode_cli", return_value="OpenCode says hello")
    def test_falls_back_to_opencode_on_claude_failure(self, mock_oc, mock_claude):
        result = run_smart_cli("test prompt", task_type="reasoning")
        assert result == "OpenCode says hello"
        # Should have been called with big-pickle for "reasoning" task type
        call_kwargs = mock_oc.call_args
        assert "big-pickle" in str(call_kwargs)

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_opencode_cli", return_value="Fast model reply")
    def test_uses_fast_model_for_classify_task(self, mock_oc, mock_claude):
        result = run_smart_cli("classify this", task_type="classify")
        assert result == "Fast model reply"
        call_kwargs = mock_oc.call_args
        assert "nemotron" in str(call_kwargs)

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_opencode_cli")
    def test_tries_secondary_on_primary_failure(self, mock_oc, mock_claude):
        # First call (primary) fails, second call (secondary) succeeds
        mock_oc.side_effect = [None, "Secondary model reply"]
        result = run_smart_cli("test", task_type="reasoning")
        assert result == "Secondary model reply"
        assert mock_oc.call_count == 2

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_opencode_cli", return_value=None)
    def test_returns_none_when_all_tiers_exhausted(self, mock_oc, mock_claude):
        result = run_smart_cli("test", task_type="reasoning")
        assert result is None
        # Should have tried primary and secondary
        assert mock_oc.call_count == 2

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_opencode_cli", return_value="Fallback reply")
    def test_passes_system_prompt_through(self, mock_oc, mock_claude):
        result = run_smart_cli("test", system="You are Bravo.")
        assert result == "Fallback reply"
        call_kwargs = mock_oc.call_args
        assert "Bravo" in str(call_kwargs)

    @patch("lib.model_fallback.run_claude_cli", return_value="Direct reply")
    def test_respects_timeout(self, mock_claude):
        result = run_smart_cli("test", timeout=5)
        assert result == "Direct reply"
        mock_claude.assert_called_once()
        call_kwargs = mock_claude.call_args
        assert call_kwargs.kwargs.get("timeout") == 5

    @patch("lib.model_fallback.run_claude_cli", side_effect=RuntimeError("boom"))
    @patch("lib.model_fallback.run_opencode_cli", return_value="Recovered")
    def test_claude_exception_degrades_to_fallback(self, mock_oc, _mock_claude):
        """CONTRACT: run_smart_cli never raises — a tier exception is treated
        as that tier returning None."""
        assert run_smart_cli("test") == "Recovered"
        mock_oc.assert_called_once()

    @patch("lib.model_fallback.run_claude_cli", side_effect=RuntimeError("boom"))
    @patch("lib.model_fallback.run_opencode_cli", side_effect=RuntimeError("boom"))
    def test_all_tiers_raising_returns_none(self, _mock_oc, _mock_claude):
        assert run_smart_cli("test") is None

    @patch("lib.model_fallback.run_claude_cli", return_value=None)
    @patch("lib.model_fallback.run_opencode_cli", return_value=None)
    def test_exhausted_log_redacts_prompt(self, _mock_oc, _mock_claude, capsys):
        """PRIVACY: the exhausted-tiers log must not leak prompt content
        (lead DMs / inbound email are PII) — fingerprint only."""
        secret = "my phone is 555-0199 and my name is John"
        run_smart_cli(secret, task_type="reasoning")
        err = capsys.readouterr().err
        assert secret not in err
        assert "sha256:" in err


class TestIsFallbackAvailable:
    @patch("lib.opencode_cli.resolve_opencode_bin", return_value="/usr/bin/opencode")
    def test_returns_true_when_binary_found(self, _mock):
        assert is_fallback_available() is True

    @patch("lib.opencode_cli.resolve_opencode_bin", return_value=None)
    def test_returns_false_when_binary_missing(self, _mock):
        assert is_fallback_available() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
