"""test_client_facing_hold.py — client-facing automations HOLD when Claude does not answer.

CC's decision, 2026-09-12 (Claude Spillover, decision #3): when anything other
than Claude would answer, email auto-replies, the draft critic and the Instagram
DM closer hold for his review instead of sending, and client content never goes
to the OpenCode free models (they log prompts). These tests pin that at the real
call sites, through the real model_fallback chain:

  * Claude is stubbed to return None — every way run_claude_cli can fail looks
    like that to its callers. The OpenCode tier is stubbed to return copy that
    WOULD clear every gate, so if any client-facing caller still reached it an
    email would auto-send and the DM turn would come back ok. That is what makes
    "OpenCode never invoked" and "nothing sent" falsifiable rather than vacuous.
  * Zero emails sent, zero DMs, the existing hold path taken, OpenCode never
    invoked, and exactly ONE Telegram note — counted through notify.py's real
    category gate and dedup, with only the HTTP POST stubbed.
  * With Claude answering, behaviour is unchanged: the same email auto-sends,
    the same DM turn succeeds, the critic still ships, and no note is sent.

The DM assertions stop at the brain's decision on purpose. The poller sends
only when decision.ok is True (instagram_dm_poller.py, step 11: "a failure is
counted and logged ... Nothing is sent"), and the brain guarantees
ok=False => action "hold" and reply None.

No live model, no network, no real email, DM or Telegram. Run:
    python -m pytest scripts/tests/test_client_facing_hold.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import draft_critic  # noqa: E402
import email_brain  # noqa: E402
import notify as notify_mod  # noqa: E402
from integrations import ig_conversation_brain as brain  # noqa: E402
from lib import model_fallback  # noqa: E402


# ── Model answers ────────────────────────────────────────────────────────────

CLASSIFY_TECH = json.dumps({"category": "Client Technical Support", "confidence": 0.95})
DRAFT_OK = json.dumps({"subject": "Re: Question about the scheduling form",
                       "body": "Saw the HVAC scheduling issue - fixable."})
CRITIC_SHIP = json.dumps({"verdict": "ship", "score": 8.5, "issues": [],
                          "suggested_revisions": {}, "notes": "clean"})
REVISED = json.dumps({"subject": "Re: hi", "body": "Rewritten by a free model."})
DM_REPLY = "Yeah, that is the bulk of what we do. What is the site doing badly right now?"
DM_OK = json.dumps({
    "stage": "engaged", "action": "reply", "reply": DM_REPLY,
    "extracted": {"name": None, "email": None, "phone": None,
                  "business": None, "need": None, "timeline": None},
    "memory": {"budget": None, "objections": None, "pitched": None, "summary": None},
    "handoff_reason": None, "confidence": 0.7,
})

# Answers that would clear every gate downstream. OpenCode always gives these,
# so a client-facing caller that reached it would visibly send.
GATE_CLEARING = {"classify": CLASSIFY_TECH, "draft": DRAFT_OK,
                 "critic": CRITIC_SHIP, "revise": REVISED, "dm": DM_OK}


def _kind(system: str) -> str:
    """Which caller is asking, read from its (stable) system prompt."""
    if "Low Priority & Archive" in system:
        return "classify"
    if "brutal-honest editor" in system:
        return "critic"
    if "rewriting a draft" in system:
        return "revise"
    if "drafting an email reply" in system:
        return "draft"
    return "dm"


class FakeTier:
    """Stands in for run_claude_cli or run_opencode_cli. Records every call.
    `answers=None` models a tier that never answers."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[dict] = []

    def __call__(self, prompt, *, system=None, model=None, timeout=None,
                 cwd=None, **_kw):
        kind = _kind(system or "")
        self.calls.append({"kind": kind, "model": model})
        if self.answers is None:
            return None
        return self.answers.get(kind)


HOLD_HEADLINE = model_fallback.CLIENT_HOLD_MESSAGE.splitlines()[0]


def _hold_notes(sent: list[dict]) -> list[dict]:
    return [p for p in sent if HOLD_HEADLINE in (p.get("text") or "")]


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """No test here may write production state or read the secrets file.

    model_fallback records tier health and appends SESSION_LOG telemetry on an
    OpenCode success; test_model_fallback.py documents what that did to the
    production log. draft_critic.critique() loads .env.agents into os.environ
    whenever no env is passed."""
    monkeypatch.setattr(model_fallback, "TIER_HEALTH_PATH",
                        tmp_path / "model_tier_health.json")
    fake_root = tmp_path / "fake_repo"
    (fake_root / "memory").mkdir(parents=True)
    (fake_root / "memory" / "SESSION_LOG.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(model_fallback, "PROJECT_ROOT", fake_root)
    monkeypatch.setattr(draft_critic, "load_env", lambda: {})


@pytest.fixture
def models(monkeypatch):
    """install(claude_answers) -> (claude, opencode). OpenCode always answers."""
    def install(claude_answers):
        claude, opencode = FakeTier(claude_answers), FakeTier(GATE_CLEARING)
        monkeypatch.setattr(model_fallback, "run_claude_cli", claude)
        monkeypatch.setattr(model_fallback, "run_opencode_cli", opencode)
        return claude, opencode
    return install


@pytest.fixture
def telegram(monkeypatch, tmp_path):
    """notify.py for real — category gate, dedup, routing — with only the HTTP
    POST replaced. Returns the list of Telegram payloads that went out.

    Routing reads a fake env, never .env.agents; the dedup ledger is a temp
    file, never the production tmp/notify_dedup.json."""
    import requests

    sent: list[dict] = []
    urls: list[str] = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def _post(url, json=None, timeout=None, **_kw):
        urls.append(url)
        sent.append(json)
        return _Resp()

    monkeypatch.setattr(notify_mod, "_notify_disabled", lambda: False)
    monkeypatch.setattr(notify_mod, "_DEDUP_PATH", tmp_path / "notify_dedup.json")
    monkeypatch.setattr(notify_mod, "DEDUP_WINDOW_SEC", 3600)
    monkeypatch.setattr(notify_mod, "_load_env", lambda: {
        "TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_ALLOWED_USERS": "1001"})
    monkeypatch.setattr(requests, "post", _post)
    yield sent
    assert all("api.telegram.org" in u for u in urls), urls


# ── Inputs ───────────────────────────────────────────────────────────────────

def _email(**over) -> dict:
    """A known client with a plain support question: no outage, money,
    frustration or opt-out signal, not financial, not a platform sender. With
    Claude up and auto-send on, this is exactly the email that auto-replies."""
    base = {
        "from": "ops@client.example",
        "subject": "Question about the scheduling form",
        "body": ("Hi CC, the scheduling form on our site shows the wrong time "
                 "zone for bookings. Can you take a look when you get a chance?"),
        "rfc_message_id": "<hold-1@client.example>",
        "is_known_client": True,
        "may_reply": True,
        "attachments": [],
    }
    base.update(over)
    return base


def _deps() -> dict:
    """The production wiring (build_default_deps, so draft_reply is the live
    drafter with its live runner and live critic), with every outward effect
    replaced by a recorder."""
    deps = email_brain.build_default_deps(mark_read=MagicMock())
    for name in ("send_reply", "store_draft", "archive", "handoff_atlas",
                 "notify", "alert", "apply_label", "mark_read"):
        deps[name] = MagicMock()
    deps["send_reply"].return_value = {"status": "sent"}
    deps["store_draft"].return_value = "draft-1"
    return deps


def _process(deps: dict, **over) -> dict:
    # No classifier argument: email_engine calls process_email(email, deps=deps),
    # so the default classifier is the production path under test.
    return email_brain.process_email(_email(**over), deps=deps,
                                     config={"auto_send_enabled": True})


PARTICIPANT = "17841400000000001"


def _dm_turns():
    return brain.build_transcript(
        [{"id": "m1", "direction": "incoming", "message": "hey, do you build websites?",
          "createdAt": "2026-08-20T10:00:00Z", "senderId": PARTICIPANT}],
        participant_id=PARTICIPANT)


def _dm_decision():
    return brain.decide(_dm_turns(), current_stage="engaged",
                        participant_display_name="Some Prospect")


# ════════════════════════════════════════════════════════════════════════════
# Claude down: hold, send nothing, never touch OpenCode, tell CC once
# ════════════════════════════════════════════════════════════════════════════

class TestClaudeUnavailable:

    def test_email_is_held_for_review_and_nothing_is_sent(self, models, telegram):
        claude, opencode = models(None)
        deps = _deps()

        out = _process(deps)

        assert out["sent"] is False
        deps["send_reply"].assert_not_called()
        # The EXISTING degraded path: keyword rubric, fallback=True, review.
        assert out["degraded"] is True
        assert out["action"] == "review"
        deps["notify"].assert_called_once()
        assert deps["notify"].call_args.args[0].startswith("Needs your review")
        assert [c["kind"] for c in claude.calls] == ["classify"]
        assert opencode.calls == [], "client email content reached OpenCode"
        assert len(_hold_notes(telegram)) == 1

    def test_claude_lost_before_the_draft_holds_the_draft(self, models, telegram):
        claude, opencode = models({"classify": CLASSIFY_TECH})
        deps = _deps()

        out = _process(deps)

        assert out["action"] == "draft_hold"
        assert out["drafted"] is True and out["sent"] is False
        deps["send_reply"].assert_not_called()
        deps["store_draft"].assert_called_once()
        assert deps["notify"].call_args.args[0].startswith("Draft held")
        assert [c["kind"] for c in claude.calls] == ["classify", "draft"]
        assert opencode.calls == []
        assert len(_hold_notes(telegram)) == 1

    def test_claude_lost_before_the_critic_holds_the_draft(self, models, telegram):
        claude, opencode = models({"classify": CLASSIFY_TECH, "draft": DRAFT_OK})
        deps = _deps()

        out = _process(deps)

        assert out["action"] == "draft_hold" and out["sent"] is False
        deps["send_reply"].assert_not_called()
        held = deps["store_draft"].call_args.args[1]
        assert held["body"] == json.loads(DRAFT_OK)["body"]
        assert held["ship"] is False, "an unreviewed draft must never be marked shippable"
        assert [c["kind"] for c in claude.calls] == ["classify", "draft", "critic"]
        assert opencode.calls == []
        assert len(_hold_notes(telegram)) == 1

    def test_draft_critic_rejects_instead_of_letting_a_free_model_approve(
            self, models, telegram):
        claude, opencode = models(None)

        v = draft_critic.critique_draft("Re: hi", "Saw the HVAC scheduling issue - fixable.",
                                        brand="oasis", intent="transactional")

        assert v["verdict"] == "reject"
        assert v["raw_verdict"] == "escalate"
        assert any(i.get("type") == "critic_unavailable" for i in v["issues"])
        assert draft_critic.revise("Re: hi", "body", {"score": 5.0}) is None
        assert [c["kind"] for c in claude.calls] == ["critic", "revise"]
        assert opencode.calls == []
        assert len(_hold_notes(telegram)) == 1

    def test_instagram_turn_holds_and_sends_no_dm(self, models, telegram):
        claude, opencode = models(None)

        d = _dm_decision()

        assert d.ok is False
        assert d.action == "hold" and d.reply is None
        assert d.failure == "model_unavailable"
        assert d.stage == "engaged", "a held turn must not move the stage"
        assert len(claude.calls) == 2, "the brain's one retry is unchanged"
        assert opencode.calls == [], "a prospect's DMs reached OpenCode"
        assert len(_hold_notes(telegram)) == 1

    def test_every_hold_in_one_run_sends_exactly_one_telegram_note(
            self, models, telegram):
        """The whole sweep in one process: three emails, a critic review and two
        DM polls, all held. One condition, one note."""
        claude, opencode = models(None)
        deps = _deps()

        for i in range(3):
            out = _process(deps, rfc_message_id=f"<hold-{i}@client.example>")
            assert out["sent"] is False and out["action"] == "review"
        assert draft_critic.critique_draft("Re: hi", "body")["verdict"] == "reject"
        for _ in range(2):
            assert _dm_decision().reply is None

        deps["send_reply"].assert_not_called()
        assert opencode.calls == []
        notes = _hold_notes(telegram)
        assert len(notes) == 1, f"expected one deduped hold note, got {len(notes)}"
        assert len(telegram) == 1, "nothing but the hold note may reach Telegram here"
        assert "Claude is limited" in notes[0]["text"]

    def test_internal_callers_keep_the_opencode_fallback(self, models, telegram):
        """Decision #3 covers client-facing automations only. run_smart_cli —
        the daily brief, sleep agent, lead scoring — still falls back, and a
        fallback is not a hold, so it sends no note."""
        claude, opencode = models(None)

        text = model_fallback.run_smart_cli("summarise today's ops", task_type="reasoning")

        assert text == DM_OK
        assert len(opencode.calls) == 1
        assert _hold_notes(telegram) == []


# ════════════════════════════════════════════════════════════════════════════
# Claude up: behaviour unchanged
# ════════════════════════════════════════════════════════════════════════════

CLAUDE_OK = {"classify": CLASSIFY_TECH, "draft": DRAFT_OK,
             "critic": CRITIC_SHIP, "dm": DM_OK}


class TestClaudeAvailable:

    def test_known_client_email_still_auto_replies(self, models, telegram):
        claude, opencode = models(CLAUDE_OK)
        deps = _deps()

        out = _process(deps)

        assert out["degraded"] is False
        assert out["action"] == "auto_reply" and out["sent"] is True
        deps["send_reply"].assert_called_once()
        assert deps["send_reply"].call_args.args[1]["body"] == json.loads(DRAFT_OK)["body"]
        assert [(c["kind"], c["model"]) for c in claude.calls] == [
            ("classify", "haiku"), ("draft", "sonnet"), ("critic", "haiku")]
        assert opencode.calls == []
        assert _hold_notes(telegram) == []

    def test_critic_still_ships_a_clean_draft(self, models, telegram):
        claude, opencode = models(CLAUDE_OK)

        v = draft_critic.critique_draft("Re: hi", "Saw the HVAC scheduling issue - fixable.",
                                        brand="oasis", intent="transactional")

        assert v["verdict"] == "ship"
        assert opencode.calls == []
        assert _hold_notes(telegram) == []

    def test_instagram_turn_still_replies(self, models, telegram):
        claude, opencode = models(CLAUDE_OK)

        d = _dm_decision()

        assert d.ok is True
        assert d.action == "reply" and d.reply == DM_REPLY
        assert [(c["kind"], c["model"]) for c in claude.calls] == [("dm", "sonnet")]
        assert opencode.calls == []
        assert _hold_notes(telegram) == []


# ── Inbound classifiers: Claude only ─────────────────────────────────────────

class TestInboundClassifierClaudeOnly:
    """The two internal inbound-mail classifiers carry client email bodies, so
    decision #3 covers them too: with Claude down, OpenCode is never invoked."""

    def test_category_runner_returns_none_without_opencode(self, models, telegram):
        import inbound_classifier
        claude, opencode = models(None)

        out = inbound_classifier._default_category_runner(
            "Subject: invoice\n\nPlease see the attached invoice.",
            system="Pick one of: ... Low Priority & Archive")

        assert out is None
        assert claude.calls
        assert opencode.calls == []

    def test_classify_via_haiku_raises_without_opencode(self, models, telegram):
        import inbound_classifier
        claude, opencode = models(None)

        with pytest.raises(RuntimeError):
            inbound_classifier._classify_via_haiku(
                "Can you fix the booking form?", "email", "Question", "ops@client.example")

        assert claude.calls
        assert opencode.calls == []

    def test_classify_via_haiku_parses_claude_answer(self, models, telegram):
        import inbound_classifier
        claude, opencode = models(GATE_CLEARING)

        raw = inbound_classifier._classify_via_haiku(
            "Can you fix the booking form?", "email", "Question", "ops@client.example")

        assert isinstance(raw, dict)
        assert claude.calls
        assert opencode.calls == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
