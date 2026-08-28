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


class TestTierHealthRecovery:
    """Regression tests for the fallback-tier health ordering.

    Codex's adversarial review caught that the first draft could not recover
    from a demotion. run_smart_cli returns on the first candidate that succeeds,
    so a demoted model is never called again, never records a success, and its
    consecutive_fail never resets — one transient outage would re-order that
    task type permanently until someone deleted the state file by hand.

    The first draft's test PASSED, because it called _record_tier_health(ok=True)
    directly. That proved the reset mechanism existed while proving nothing
    about whether any real code path could reach it. These tests assert on
    reachability instead.
    """

    CANDS = ["nemotron-3.5-lightning-free", "mimo-v2.5-free"]

    def _fail_n(self, task, model, n):
        for _ in range(n):
            model_fallback._record_tier_health(task, model, ok=False)

    def test_no_history_preserves_declared_order(self):
        assert model_fallback._order_by_health("classify", self.CANDS) == self.CANDS

    def test_repeated_failure_demotes(self):
        self._fail_n("classify", self.CANDS[0], model_fallback.TIER_DEMOTE_AFTER)
        assert model_fallback._order_by_health("classify", self.CANDS)[0] == self.CANDS[1]

    def test_demotion_never_drops_a_candidate(self):
        """A model that failed a thousand times is still tried if it is the only
        one left — demotion reorders, it must never remove."""
        self._fail_n("classify", self.CANDS[0], 50)
        assert set(model_fallback._order_by_health("classify", self.CANDS)) == set(self.CANDS)

    def test_demotion_expires_so_recovery_does_not_need_a_success(self):
        """THE bug Codex found. Without a TTL the demoted model is never probed
        again, so it can never record the success that would clear it."""
        import json
        from datetime import datetime, timedelta, timezone
        task, model = "classify", self.CANDS[0]
        self._fail_n(task, model, model_fallback.TIER_DEMOTE_AFTER)
        assert model_fallback._order_by_health(task, self.CANDS)[0] == self.CANDS[1]

        # Age the last failure past the TTL — no success recorded, deliberately.
        data = model_fallback._read_tier_health()
        old = datetime.now(timezone.utc) - timedelta(
            seconds=model_fallback.DEMOTE_TTL_SEC + 60)
        data[f"{task}:{model}"]["last_fail"] = old.isoformat()
        model_fallback.TIER_HEALTH_PATH.write_text(json.dumps(data), encoding="utf-8")

        assert model_fallback._order_by_health(task, self.CANDS) == self.CANDS, (
            "an expired demotion must return the model to its declared position "
            "WITHOUT requiring a success it can never get")

    def test_fresh_demotion_still_holds(self):
        """The TTL must not defeat the demotion it is escaping from."""
        self._fail_n("classify", self.CANDS[0], model_fallback.TIER_DEMOTE_AFTER)
        assert model_fallback._order_by_health("classify", self.CANDS)[0] == self.CANDS[1]

    def test_corrupt_store_falls_back_to_declared_order(self):
        model_fallback.TIER_HEALTH_PATH.write_text("{not json", encoding="utf-8")
        assert model_fallback._order_by_health("classify", self.CANDS) == self.CANDS

    def test_unparseable_timestamp_does_not_hold_a_demotion(self):
        import json
        task, model = "classify", self.CANDS[0]
        self._fail_n(task, model, model_fallback.TIER_DEMOTE_AFTER)
        data = model_fallback._read_tier_health()
        data[f"{task}:{model}"]["last_fail"] = "not-a-timestamp"
        model_fallback.TIER_HEALTH_PATH.write_text(json.dumps(data), encoding="utf-8")
        assert model_fallback._order_by_health(task, self.CANDS) == self.CANDS

    def test_task_types_are_isolated(self):
        self._fail_n("classify", self.CANDS[0], model_fallback.TIER_DEMOTE_AFTER)
        assert model_fallback._order_by_health("reasoning", self.CANDS) == self.CANDS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
