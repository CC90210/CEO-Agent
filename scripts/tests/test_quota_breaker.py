"""The claude_cli quota circuit breaker.

When the 5-hour subscription quota is spent, every call still pays ~32s to spawn
the CLI and be told so, and model_fallback then pays another 120s on the dead
middle tier. Measured 2026-08-26: 172.5s for ONE classification against the
inbound sweep's 300s wall — the sweep died mid-mailbox. The breaker skips the
attempt we already know will fail.

EVERY TEST HERE IS ABOUT FAILING OPEN. A latency optimisation that can wedge the
model shut is strictly worse than the latency it saves: the fleet would silently
run on fallback models with no error anywhere. So an unreadable, corrupt,
garbage or expired marker must all mean "just make the call".
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import claude_cli as cc  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_marker(monkeypatch):
    """Never touch the real state/claude_quota_state.json."""
    path = Path(tempfile.mkdtemp()) / "quota.json"
    monkeypatch.setattr(cc, "QUOTA_STATE_PATH", path)
    return path


# --- closed (the optimisation) ------------------------------------------------

def test_no_marker_means_make_the_call():
    assert cc._quota_cooldown_remaining() == 0


def test_quota_hit_opens_the_breaker():
    cc._open_quota_breaker("Your usage limit has been reached.")
    remaining = cc._quota_cooldown_remaining()
    assert 0 < remaining <= cc.QUOTA_COOLDOWN_DEFAULT_SEC


def test_a_reset_hint_is_captured_when_the_message_carries_one(isolated_marker):
    """Recorded for diagnosis. The cooldown deliberately does NOT trust it — an
    unparsed or wrong reset time must not extend the outage."""
    cc._open_quota_breaker("Limit resets at 3pm.")
    assert json.loads(isolated_marker.read_text(encoding="utf-8"))["reset_hint"] == "3pm"


def test_a_message_without_a_hint_still_opens_the_breaker(isolated_marker):
    cc._open_quota_breaker("quota exceeded")
    assert cc._quota_cooldown_remaining() > 0
    assert json.loads(isolated_marker.read_text(encoding="utf-8"))["reset_hint"] is None


def test_breaker_never_persists_raw_provider_text_or_credentials(isolated_marker):
    secret = "sk-live-sensitive-provider-token"
    cc._open_quota_breaker(f"usage limit; diagnostic token={secret}")
    payload = json.loads(isolated_marker.read_text(encoding="utf-8"))
    rendered = json.dumps(payload)
    assert secret not in rendered
    assert "raw" not in payload
    assert payload["signal_sha256"].startswith("sha256:")


def test_quota_and_auth_are_distinct_for_defer_policy():
    assert cc._classify_provider_stop("You've hit your session limit - resets 8pm", 1) == "quota"
    assert cc._classify_provider_stop("Invalid bearer token; please run /login", 1) == "auth"
    assert cc._classify_provider_stop("TypeError: boom", 1) is None


@pytest.mark.parametrize(
    "message",
    [
        "Your limit resets at 8pm",
        "Please try again in 12 minutes",
        "Insufficient credit remaining",
        "rate_limit_error",
        "quota_exceeded",
        "429 Too Many Requests",
        "529 Overloaded",
        "Upgrade to a paid plan",
    ],
)
def test_shared_limit_signals_remain_quota_deferrals(message):
    assert cc._classify_provider_stop(message, 1) == "quota"


@pytest.mark.parametrize(
    "message",
    [
        "Please obtain a new token",
        "run `claude login`",
        "invalid_api_key",
        "401 Unauthorized",
        "403 Forbidden",
    ],
)
def test_shared_auth_signals_never_open_the_quota_breaker(message):
    assert cc._classify_provider_stop(message, 1) == "auth"


def test_quota_on_stdout_is_not_masked_by_a_stderr_warning(monkeypatch):
    class Result:
        returncode = 1
        stderr = "warning: optional launcher update available"
        stdout = "You've hit your session limit - resets 8pm"

    monkeypatch.setattr(cc, "resolve_claude_bin", lambda: "claude")
    monkeypatch.setattr(cc.subprocess, "run", lambda *args, **kwargs: Result())

    assert cc.run_claude_cli("hello") is None
    assert cc._quota_cooldown_remaining() > 0


# --- open (the safety property) -----------------------------------------------

def test_success_closes_the_breaker():
    """Self-healing: the first call that gets through reopens the primary path,
    even if the cooldown was guessed far too long."""
    cc._open_quota_breaker("usage limit")
    assert cc._quota_cooldown_remaining() > 0
    cc._close_quota_breaker()
    assert cc._quota_cooldown_remaining() == 0


def test_corrupt_marker_fails_open(isolated_marker):
    isolated_marker.write_text("{ this is not json", encoding="utf-8")
    assert cc._quota_cooldown_remaining() == 0


def test_non_numeric_until_fails_open(isolated_marker):
    isolated_marker.write_text(json.dumps({"until_epoch": "not-a-number"}),
                               encoding="utf-8")
    assert cc._quota_cooldown_remaining() == 0


def test_marker_without_the_field_fails_open(isolated_marker):
    isolated_marker.write_text(json.dumps({"detected_at": "whenever"}),
                               encoding="utf-8")
    assert cc._quota_cooldown_remaining() == 0


def test_non_dict_marker_fails_open(isolated_marker):
    isolated_marker.write_text(json.dumps(["a", "list"]), encoding="utf-8")
    assert cc._quota_cooldown_remaining() == 0


def test_expired_marker_fails_open(isolated_marker):
    isolated_marker.write_text(json.dumps({"until_epoch": time.time() - 99}),
                               encoding="utf-8")
    assert cc._quota_cooldown_remaining() == 0


def test_closing_an_absent_marker_is_not_an_error():
    cc._close_quota_breaker()
    cc._close_quota_breaker()


def test_an_unwritable_marker_does_not_raise(monkeypatch, tmp_path):
    """Recording the breaker is best-effort — a read-only state dir must not
    take down every model call in the fleet."""
    blocked = tmp_path / "not_a_file"
    blocked.mkdir()
    monkeypatch.setattr(cc, "QUOTA_STATE_PATH", blocked)
    cc._open_quota_breaker("usage limit")
    assert cc._quota_cooldown_remaining() == 0


def test_it_uses_the_shared_json_ledger_rather_than_a_private_copy():
    """lib/json_ledger.py is the repo's one implementation of this on-disk idiom
    — its docstring calls itself 'the shared implementation for everything
    written since'. The first draft of the breaker hand-rolled load/save, which
    is exactly the duplication that module exists to prevent."""
    src = (Path(cc.__file__)).read_text(encoding="utf-8")
    assert "json_ledger" in src
    assert "os.replace(tmp" not in src, "private atomic-write copy reintroduced"


def test_pure_text_cli_loads_no_settings_and_never_loads_project_hooks(monkeypatch):
    seen: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):
        seen["args"] = list(args)
        return Result()

    monkeypatch.setattr(cc, "resolve_claude_bin", lambda: "claude")
    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    assert cc.run_claude_cli("hello") == "ok"
    args = seen["args"]
    assert "--bare" not in args
    index = args.index("--setting-sources")
    assert args[index + 1] == ""
