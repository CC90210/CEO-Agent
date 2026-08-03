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
import re
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
    ("revenue", "atlas"),
    ("invoice", "atlas"),
    ("stripe", "atlas"),
    ("system", "bravo"),
    ("email", "bravo"),
    ("booking", "bravo"),
    ("lead", "bravo"),
])
def test_category_routes_to_the_owning_agent(category, owner):
    assert nf.resolve_agent(category) == owner


def test_lead_stays_on_the_operators_channel():
    """Regression on a mapping written from taxonomy instead of call sites.

    'Leads are marketing, so route lead -> maven' is wrong here. Both live
    emitters need CC, not Maven: funnel_sync.py:302 is the "NEW FUNNEL LEAD"
    push with name/email/notes (the operator has to phone them) and
    autonomous_agent.py:762 is inside `_notify_cc_escalation`. A lead and the
    booking that follows are one operator motion — routing them to different
    bots halves the funnel.
    """
    assert nf.resolve_agent("lead") == nf.resolve_agent("booking") == "bravo"


# Categories that ARE emitted but deliberately have no CATEGORY_OWNER row, so
# they take DEFAULT_AGENT. Reviewed 2026-07-30: both are Bravo's own work and
# Bravo is the default, so a row would be noise. Adding to this set is a
# decision — that is the point of making it explicit.
REVIEWED_DEFAULTS = {"low_priority", "ops"}

_CATEGORY_LITERAL = re.compile(r"""category\s*=\s*["']([a-z_\-]+)["']""")


def _emitted_categories() -> set[str]:
    scripts_dir = Path(__file__).resolve().parent.parent
    found: set[str] = set()
    for py in scripts_dir.rglob("*.py"):
        parts = set(py.parts)
        if "tests" in parts or "_archive" in parts or "__pycache__" in parts:
            continue
        if py.name == "notify.py":          # its own docstring examples
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found.update(_CATEGORY_LITERAL.findall(src))
    return found


def test_every_emitted_category_is_routed_or_consciously_defaulted():
    """The mapping must be derived from real call sites, not invented.

    Without this, someone adds notify(..., category="ad_spend") in a Maven-owned
    path, it silently lands on Bravo's channel, and nobody finds out because the
    alert still arrives — just on the wrong bot. Fails loudly instead: either
    map it, or add it to REVIEWED_DEFAULTS having thought about it.
    """
    emitted = _emitted_categories()
    assert emitted, "sweep found nothing — the regex or the path is wrong"
    unaccounted = emitted - set(nf.CATEGORY_OWNER) - REVIEWED_DEFAULTS
    assert not unaccounted, (
        f"emitted but unrouted: {sorted(unaccounted)} — add to CATEGORY_OWNER "
        f"or to REVIEWED_DEFAULTS")


def test_the_sweep_would_actually_catch_a_new_category():
    """Guard the guard — a regex that matches nothing passes vacuously."""
    assert _CATEGORY_LITERAL.findall('notify("x", category="ad_spend")') == ["ad_spend"]
    assert {"lead", "booking", "system"} <= _emitted_categories()


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


# ── OASIS partner-group channel isolation (2026-08-03) ───────────────────────
#
# The group is CC + Adon + Bravo + APEX/Knut. Adon is a 50/50 partner on
# PropFlow ONLY, so internal operational traffic — a blocked sending number, a
# scraper traceback, a cron failure — has no business in his chat.
#
# The pre-existing guard proves a caller ASKED for the group (group=True). It
# cannot tell whether the CONTENT belongs there. These tests pin the content
# half: operational vocabulary is rerouted to CC's private DM, never dropped,
# and legitimate partner traffic is left alone.

# Bravo-OWNED operational messages. The number-rotation and TPS examples that
# used to live here moved to NOT_BRAVOS_DOMAIN below: CC's 2026-08-03 direction
# is that those are APEX's to raise, so Bravo drops them outright rather than
# rerouting them into his DM.
OPERATIONAL_MESSAGES = [
    "Campaign pool exhausted, rotate it out",
    "Seeing failure across the outreach lane",
    "Domain ping failed for oasisai.work",
    "Cron failure on the nightly sweep",
    "Stack trace attached below",
    "Traceback (most recent call last)",
    "Scraper log shows 40 timeouts",
    "Daemon crash on bravo-scheduler",
    "Dead-letter queue is backing up",
]

PARTNER_MESSAGES = [
    "PropFlow milestone: pilot tenant onboarded",
    "Deliverable handed over - the dashboard is live for review",
    "Sprint released: lead routing is now tenant-scoped",
    "New client onboarded on the PropFlow side",
    # The near-miss that proves the terms are phrase-scoped, not word-scoped:
    # a bare "blocked" is ordinary partner vocabulary.
    "The PropFlow deal is blocked on Adon's signature",
]


@pytest.mark.parametrize("message", OPERATIONAL_MESSAGES)
def test_operational_noise_is_rerouted_off_the_group_lane(monkeypatch, message):
    """Operational content must not reach the partner group even when the
    caller explicitly passed group=True."""
    env = {
        "TELEGRAM_BOT_TOKEN": "bravo-token",
        "TELEGRAM_ALLOWED_USERS": "5099208958",
        "GROUP_TELEGRAM_CHAT_ID": "-5165125484",
    }
    sent = _capture(monkeypatch, env)
    nf.notify(message, category="outreach", force=True, group=True)
    assert sent, "alert was dropped entirely — it must reroute, not vanish"
    chat = str(sent["json"]["chat_id"])
    assert chat == "5099208958", (
        f"operational message reached chat {chat}; expected CC's private DM")
    assert not chat.startswith("-"), "operational message reached a GROUP chat"


@pytest.mark.parametrize("message", PARTNER_MESSAGES)
def test_partner_traffic_still_reaches_the_group(monkeypatch, message):
    """The other failure direction. A guard that eats legitimate partner
    updates gets switched off, and then nothing is isolated."""
    env = {
        "TELEGRAM_BOT_TOKEN": "bravo-token",
        "TELEGRAM_ALLOWED_USERS": "5099208958",
        "GROUP_TELEGRAM_CHAT_ID": "-5165125484",
    }
    sent = _capture(monkeypatch, env)
    nf.notify(message, category="system", force=True, group=True)
    assert sent, "partner broadcast was dropped"
    assert str(sent["json"]["chat_id"]) == "-5165125484", (
        f"partner message did not reach the group: {sent['json']['chat_id']}")


def test_operational_noise_on_the_private_lane_is_untouched(monkeypatch):
    """The filter is scoped to group=True. CC's own DM is exactly where a
    blocked-number alert belongs, so it must pass through unchanged."""
    env = {"TELEGRAM_BOT_TOKEN": "bravo-token", "TELEGRAM_ALLOWED_USERS": "5099208958"}
    sent = _capture(monkeypatch, env)
    nf.notify("Cron failure on the nightly sweep",
              category="system", force=True, group=False)
    assert sent, "private-lane operational alert was suppressed — it must not be"
    assert str(sent["json"]["chat_id"]) == "5099208958"


def test_agent_activity_imports_the_denylists_rather_than_copying_them():
    """One definition, not two kept in step by hand.

    The first version of this guard duplicated the pattern into
    agent_activity.py with a "kept in sync" comment. It drifted within the
    hour: notify.py gained _NOT_BRAVO_DOMAIN_RE (TextTorrent / TPS /
    phone_lookup) and the copy did not, so "TextTorrent sender pool exhausted"
    was still mirrorable straight into the partner group. Importing removes the
    failure mode; this test stops anyone re-introducing a local copy.
    """
    import ast

    src = (Path(__file__).resolve().parent.parent
           / "integrations" / "agent_activity.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    local_defs = [
        t.id
        for node in ast.walk(tree) if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
        and t.id in ("_GROUP_BLOCKED_TERMS_RE", "_NOT_BRAVO_DOMAIN_RE")
    ]
    assert not local_defs, (
        f"agent_activity.py re-defines {local_defs} instead of importing them "
        f"from notify.py — that is exactly how the TextTorrent gap appeared.")

    imported = {
        alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        and node.module == "notify"
        for alias in node.names
    }
    assert {"_GROUP_BLOCKED_TERMS_RE", "_NOT_BRAVO_DOMAIN_RE"} <= imported, (
        f"agent_activity.py must import both denylists from notify.py; got {imported}")


@pytest.mark.parametrize("py_name,js_name", [
    ("_GROUP_BLOCKED_TERMS_RE", "OPERATIONAL_NOISE_RE"),
    ("_NOT_BRAVO_DOMAIN_RE", "NOT_BRAVO_DOMAIN_RE"),
])
def test_js_bridge_denylists_match_python(py_name, js_name):
    """coordination_agent.js is the one copy that CANNOT import the Python.

    It is a live door into the partner group (@BravoGCAdon_bot), so a term
    present in Python and missing in JS leaves that door open. Compared by
    parsing the JS source for the literal, since node isn't guaranteed here.
    """
    js = (Path(__file__).resolve().parent.parent.parent
          / "coordination_agent.js").read_text(encoding="utf-8")
    m = re.search(rf"^const {js_name} = /(.+)/i;\s*$", js, re.MULTILINE)
    assert m, f"{js_name} not found in coordination_agent.js"
    js_body = m.group(1)

    py_body = getattr(nf, py_name).pattern
    # The Python patterns are written multi-line with (?:...) groups and \b
    # anchors; normalise whitespace introduced purely by source formatting.
    norm = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    assert norm(js_body) == norm(py_body), (
        f"{js_name} (JS) has drifted from {py_name} (Python).\n"
        f"  python: {py_body!r}\n"
        f"  js    : {js_body!r}")


# ── Domain ownership: Bravo must not page CC about APEX's work ───────────────
#
# CC, 2026-08-03: "I keep receiving personal messages from Bravo that pertain to
# TextTorrent, and it's saying that I need to rotate this number. This is
# completely garbage ... This is something that Apex does."
#
# TPS phone-lookup / TextTorrent number rotation was formally handed to
# APEX/Adon because Bravo CANNOT act on it — DataDome scores the source ASN, so
# only Adon's residential workstation can drain that queue. An alert Bravo can
# neither fix nor action is noise, and it arrives wearing Bravo's name.
#
# These DROP rather than reroute: the wrong OWNER, not merely the wrong
# audience. The alert still exists and is actionable at its source.

NOT_BRAVOS_DOMAIN = [
    "🚨 Sending number +18604527608 is getting blocked — rotate out",
    "Sending number +18604527608 is getting blocked - rotate it out",
    "TextTorrent sender pool exhausted",
    "TPS scrape returned blocked for 21 Live Subs",
    "TPS backlog is at 240h",
    "phone_lookup queue is stuck",
    "phone lookup job failed",
]


@pytest.mark.parametrize("message", NOT_BRAVOS_DOMAIN)
@pytest.mark.parametrize("group", [False, True])
def test_apex_domain_alerts_are_dropped_on_both_lanes(monkeypatch, message, group):
    env = {
        "TELEGRAM_BOT_TOKEN": "bravo-token",
        "TELEGRAM_ALLOWED_USERS": "5099208958",
        "GROUP_TELEGRAM_CHAT_ID": "-5165125484",
    }
    sent = _capture(monkeypatch, env)
    result = nf.notify(message, category="outreach", force=True, group=group)
    assert result is False, "notify() must report the alert was not delivered"
    assert not sent, (
        f"APEX-domain alert reached Telegram (group={group}): {sent.get('json')}")


def test_bravo_owned_outreach_alerts_still_send(monkeypatch):
    """The other direction. Bravo owns its own outreach — a genuine send failure
    on Bravo's own lane must still page CC."""
    env = {"TELEGRAM_BOT_TOKEN": "bravo-token", "TELEGRAM_ALLOWED_USERS": "5099208958"}
    sent = _capture(monkeypatch, env)
    assert nf.notify("Outreach daily cap reached — 40 of 40 sent",
                     category="outreach", force=True) is True
    assert sent, "a Bravo-owned outreach alert must still reach CC"


def test_ownership_drop_beats_the_group_reroute(monkeypatch):
    """Ordering matters: the ownership gate runs FIRST.

    "Sending number ... is getting blocked" matches BOTH denylists. If the group
    filter won, the message would be rerouted into CC's DM — which is exactly
    the message CC asked never to receive again.
    """
    env = {
        "TELEGRAM_BOT_TOKEN": "bravo-token",
        "TELEGRAM_ALLOWED_USERS": "5099208958",
        "GROUP_TELEGRAM_CHAT_ID": "-5165125484",
    }
    sent = _capture(monkeypatch, env)
    assert nf.notify("🚨 Sending number +18604527608 is getting blocked — rotate out",
                     category="outreach", force=True, group=True) is False
    assert not sent, "rerouted to CC's DM instead of being dropped"
