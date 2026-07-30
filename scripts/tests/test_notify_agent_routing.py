"""Multi-agent bridge routing — Bravo / Maven / Atlas.

Each C-suite agent runs its own PM2 Telegram bridge with its own bot token in
its own repo. notify() used to send everything through Bravo's bridge regardless
of subject, so CC's executive channel carried Maven's post failures and Atlas's
Stripe syncs next to real OS health. A channel that carries everything gets read
as nothing.

The risky part is the FALLBACK: Maven's and Atlas's tokens normally are NOT in
Bravo's env (separate credentials by design). Getting that wrong either drops
the alert entirely or delivers it unlabelled. Both are tested here.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notify as nf  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    importlib.reload(nf)
    yield


# ── category → owner ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("category,owner", [
    ("content", "maven"),
    ("instagram", "maven"),
    ("outreach", "maven"),
    ("lead", "maven"),
    ("revenue", "atlas"),
    ("invoice", "atlas"),
    ("stripe", "atlas"),
    ("system", "bravo"),
    ("email", "bravo"),
    ("booking", "bravo"),
])
def test_category_routes_to_the_owning_agent(category, owner):
    assert nf.resolve_agent(category) == owner


def test_unknown_category_defaults_to_bravo():
    """Bravo is the operator's channel and the safe default — an unrouted alert
    must reach someone, not vanish."""
    assert nf.resolve_agent("some_new_category") == "bravo"
    assert nf.resolve_agent("") == "bravo"


def test_explicit_agent_overrides_the_category():
    """A cron failure is category='system' but may belong to Maven."""
    assert nf.resolve_agent("system", agent="maven") == "maven"
    assert nf.resolve_agent("revenue", agent="bravo") == "bravo"
    assert nf.resolve_agent("content", agent="ATLAS") == "atlas"


def test_every_owner_has_a_token_mapping():
    """A category routed to an agent with no AGENT_TOKEN_KEYS entry would fall
    through to the wrong bridge silently."""
    for owner in set(nf.CATEGORY_OWNER.values()) | {nf.DEFAULT_AGENT}:
        assert owner in nf.AGENT_TOKEN_KEYS, f"{owner} has no token mapping"


def test_bravo_uses_the_historical_env_keys():
    """Bravo's bridge must keep working on the keys it has always used —
    renaming them would take the whole fleet's alerting down."""
    assert nf.AGENT_TOKEN_KEYS["bravo"] == ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS")


def test_sibling_key_names_match_the_siblings_own_source():
    """These names are a CONTRACT with another repo, not a local choice.

    Maven's notify.py resolves MAVEN_TELEGRAM_BOT_TOKEN +
    MAVEN_TELEGRAM_ALLOWED_USERS; Atlas uses ATLAS_TELEGRAM_TOKEN +
    ATLAS_TELEGRAM_CHAT_ID. A first draft here guessed
    MAVEN_TELEGRAM_CHAT_ID — CC would have set the key Maven expects and Bravo
    would have looked for a different one, falling back silently forever.
    """
    assert nf.AGENT_TOKEN_KEYS["maven"] == (
        "MAVEN_TELEGRAM_BOT_TOKEN", "MAVEN_TELEGRAM_ALLOWED_USERS")
    assert nf.AGENT_TOKEN_KEYS["atlas"] == (
        "ATLAS_TELEGRAM_TOKEN", "ATLAS_TELEGRAM_CHAT_ID")


# ── delivery + fallback ──────────────────────────────────────────────────────

def _capture(monkeypatch, env: dict):
    """Run notify() against a fake env and a fake requests, return the payload."""
    sent: dict = {}

    monkeypatch.setattr(nf, "_load_env", lambda: env)
    monkeypatch.setattr(nf, "_notify_disabled", lambda: False)
    monkeypatch.setattr(nf, "_dedup_should_send", lambda *a, **k: True)
    monkeypatch.setattr(nf, "_get_blocked_categories", lambda: set())

    class _Resp:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"ok": True}

    # The stub must carry `.exceptions` — notify()'s retry path references
    # requests.exceptions.ConnectionError, so a bare stub raises AttributeError
    # and the test fails for a reason that has nothing to do with routing.
    import requests as _real_requests

    class _Req:
        exceptions = _real_requests.exceptions

        @staticmethod
        def post(url, **kw):
            sent["url"] = url
            sent["json"] = kw.get("json") or kw.get("data")
            return _Resp()

    monkeypatch.setitem(sys.modules, "requests", _Req)
    return sent


BRAVO_ENV = {"TELEGRAM_BOT_TOKEN": "bravo-token", "TELEGRAM_ALLOWED_USERS": "111"}


def test_maven_alert_uses_mavens_bridge_when_configured(monkeypatch):
    env = {**BRAVO_ENV,
           "MAVEN_TELEGRAM_BOT_TOKEN": "maven-token",
           "MAVEN_TELEGRAM_ALLOWED_USERS": "222"}
    sent = _capture(monkeypatch, env)
    assert nf.notify("post failed", category="content") is True
    assert "maven-token" in sent["url"], "did not use Maven's bot"
    assert sent["json"]["chat_id"] == "222"
    assert "bridge not configured" not in sent["json"]["text"]


def test_atlas_alert_uses_atlas_bridge_when_configured(monkeypatch):
    env = {**BRAVO_ENV,
           "ATLAS_TELEGRAM_TOKEN": "atlas-token",
           "ATLAS_TELEGRAM_CHAT_ID": "333"}
    sent = _capture(monkeypatch, env)
    assert nf.notify("stripe sync failed", category="revenue") is True
    assert "atlas-token" in sent["url"]
    assert sent["json"]["chat_id"] == "333"


def test_missing_sibling_bridge_falls_back_to_bravo_AND_says_so(monkeypatch):
    """THE important case. Maven's token lives in Maven's repo, so it is usually
    absent here. The alert must still arrive — labelled, not silently misfiled."""
    sent = _capture(monkeypatch, dict(BRAVO_ENV))       # no MAVEN_* keys
    assert nf.notify("post failed", category="content") is True
    assert "bravo-token" in sent["url"], "alert was dropped instead of falling back"
    text = sent["json"]["text"]
    assert "[for maven" in text, f"misroute is unlabelled: {text!r}"
    assert "bridge not configured" in text


def test_bravo_alert_is_never_labelled_as_a_misroute(monkeypatch):
    sent = _capture(monkeypatch, dict(BRAVO_ENV))
    assert nf.notify("scheduler down", category="system", force=True) is True
    assert "bridge not configured" not in sent["json"]["text"]


def test_missing_bravo_token_fails_loudly_not_silently(monkeypatch):
    sent = _capture(monkeypatch, {"TELEGRAM_ALLOWED_USERS": "111"})
    assert nf.notify("anything", category="system", force=True) is False
    assert not sent, "should not have attempted a send"


# ── the scheduler's ownership map ────────────────────────────────────────────

def test_scheduler_routes_cron_failures_by_owner():
    import scheduler

    assert scheduler.agent_for_action("content_post") == "maven"
    assert scheduler.agent_for_action("ig_dm_check") == "maven"
    assert scheduler.agent_for_action("stripe_sync") == "atlas"
    assert scheduler.agent_for_action("revenue_report") == "atlas"
    assert scheduler.agent_for_action("email_inbox_check") == "bravo"
    assert scheduler.agent_for_action("funnel_sync") == "bravo"
    # An unknown action must still reach someone.
    assert scheduler.agent_for_action("brand_new_job") == "bravo"


def test_domain_sets_are_module_level_and_disjoint():
    """They were locals inside execute_job; the router needs the same map, and a
    second copy would drift. Overlap would make ownership ambiguous."""
    import scheduler

    assert isinstance(scheduler.MAVEN_DOMAIN_ACTIONS, frozenset)
    assert isinstance(scheduler.ATLAS_DOMAIN_ACTIONS, frozenset)
    assert not (scheduler.MAVEN_DOMAIN_ACTIONS & scheduler.ATLAS_DOMAIN_ACTIONS)
