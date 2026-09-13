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


# --- what opens it (2026-09-12) -----------------------------------------------
# The trigger was a substring test ("weekly limit" / "usage limit" / "quota")
# over both streams. It opened on "Approaching Opus usage limit", a warning, and
# missed "You've hit your session limit · resets 8pm", the 2026-09-03 incident
# string. It is now lib.claude_auth.is_subscription_limit (verb-anchored,
# config/claude_auth_signals.json), read from stderr first and from stdout only
# when stderr is empty.

SIGNALS = json.loads((Path(__file__).resolve().parents[2] / "config" /
                      "claude_auth_signals.json").read_text(encoding="utf-8"))
INCIDENT = "You've hit your session limit · resets 8pm"


@pytest.fixture
def fake_cli(monkeypatch):
    """Stand in for the claude binary: record every spawn, return what the test
    scripts. Nothing real is launched and no quota is spent."""
    calls: list[dict] = []

    def install(returncode=0, stdout="", stderr=""):
        monkeypatch.setattr(cc, "resolve_claude_bin", lambda: "claude")

        def _run(args, **kw):
            calls.append({"args": list(args), **kw})
            return cc.subprocess.CompletedProcess(args, returncode, stdout, stderr)

        monkeypatch.setattr(cc.subprocess, "run", _run)
        return calls

    return install


@pytest.mark.parametrize("message", SIGNALS["subscription_limit_must_match"])
def test_a_real_subscription_limit_opens_the_breaker(fake_cli, message):
    fake_cli(returncode=1, stderr=message)
    assert cc.run_claude_cli("hi") is None
    assert cc._quota_cooldown_remaining() > 0, f"{message!r} should have opened the breaker"


@pytest.mark.parametrize("message", SIGNALS["subscription_limit_must_not_match"])
def test_a_warning_or_transient_limit_leaves_the_breaker_shut(fake_cli, message):
    fake_cli(returncode=1, stderr=message)
    assert cc.run_claude_cli("hi") is None
    assert cc._quota_cooldown_remaining() == 0, (
        f"{message!r} opened the breaker: every automation would sit on fallback "
        "models for the whole cooldown")


def test_the_incident_string_records_its_reset_hint(fake_cli, isolated_marker):
    fake_cli(returncode=1, stderr=INCIDENT)
    cc.run_claude_cli("hi")
    assert json.loads(isolated_marker.read_text(encoding="utf-8"))["reset_hint"] == "8pm"


def test_stdout_is_read_when_stderr_is_empty(fake_cli):
    """2026-08-13: the CLI can explain itself on stdout alone."""
    fake_cli(returncode=1, stdout=INCIDENT)
    cc.run_claude_cli("hi")
    assert cc._quota_cooldown_remaining() > 0


def test_stderr_is_read_first(fake_cli):
    """stdout counts only when stderr is empty: a real error on stderr is not
    overridden by a limit phrase that merely appears in stdout."""
    fake_cli(returncode=1, stderr="TypeError: foo is undefined", stdout=INCIDENT)
    cc.run_claude_cli("hi")
    assert cc._quota_cooldown_remaining() == 0


def test_a_success_never_opens_the_breaker(fake_cli):
    fake_cli(returncode=0, stdout=INCIDENT)  # a reply that merely quotes the phrase
    assert cc.run_claude_cli("hi") == INCIDENT
    assert cc._quota_cooldown_remaining() == 0


# --- the automation pin (Claude Spillover guard) ------------------------------
# Once ~/.claude/settings.json points ANTHROPIC_BASE_URL at the spillover proxy,
# an automation would follow it there. --settings <pin> outranks user settings;
# the X-Bravo-Lane header is the second, independent guard.

def test_run_claude_cli_passes_the_automation_pin(fake_cli, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:20131")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    calls = fake_cli(returncode=0, stdout="ok")
    assert cc.run_claude_cli("hi") == "ok"
    args, env = calls[0]["args"], calls[0]["env"]
    pin = Path(args[args.index("--settings") + 1])
    assert pin.is_absolute() and pin == cc.AUTOMATION_PIN_PATH
    assert json.loads(pin.read_text(encoding="utf-8")) == {
        "env": {"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}}
    assert env["ANTHROPIC_CUSTOM_HEADERS"] == "X-Bravo-Lane: automation"
    assert "ANTHROPIC_BASE_URL" not in env and "CLAUDE_CODE_ENTRYPOINT" not in env, (
        "an inherited lane var reached the automation's claude")


def test_the_document_path_passes_the_automation_pin(fake_cli, tmp_path):
    doc = tmp_path / "invoice.pdf"
    doc.write_bytes(b"%PDF-1.4 test")
    calls = fake_cli(returncode=0, stdout="ok")
    assert cc.run_claude_cli_on_document(doc, "What is the total?") == "ok"
    args = calls[0]["args"]
    assert args[args.index("--settings") + 1] == str(cc.AUTOMATION_PIN_PATH)
    assert calls[0]["env"]["ANTHROPIC_CUSTOM_HEADERS"] == "X-Bravo-Lane: automation"


@pytest.mark.parametrize("pin_content", [
    None,                                                          # missing
    "{ not json",                                                  # corrupt
    '{"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:20131"}}',   # wrong target
])
def test_a_bad_pin_is_loud_but_never_blocks_the_call(fake_cli, monkeypatch, tmp_path,
                                                     capsys, pin_content):
    pin = tmp_path / "automation_pin.json"
    if pin_content is not None:
        pin.write_text(pin_content, encoding="utf-8")
    monkeypatch.setattr(cc, "AUTOMATION_PIN_PATH", pin)
    calls = fake_cli(returncode=0, stdout="ok")
    assert cc.run_claude_cli("hi") == "ok", "a bad pin must never block an automation"
    assert "--settings" not in calls[0]["args"]
    assert "AUTOMATION PIN" in capsys.readouterr().err
