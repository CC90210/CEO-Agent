"""An escalation may not double as a non-answer.

WHY THIS EXISTS
---------------
2026-09-03, 14:38Z. The operator DM'd the business account from a test profile
and asked "Could I get some help on ai". The model chose action=handoff. Its own
stated reason ended: "Last msg 'Could I get some help on ai' may be genuine,
needs human call on disqualify vs engage."

The poller's handoff branch sent nothing. So the operator got a Telegram alert
saying a human was needed, and no reply on Instagram. His words:

    "Why am I getting Telegram messages, but the agents are not responding to
     the DM?"

That pairing — interrupt a human AND leave the prospect on read — is worse than
either failure alone. It is also the model resolving its OWN uncertainty by
escalating, on a thread where a single question would have settled it.

The rule, in two halves:

  1. BRAIN (Gate D): a handoff must carry a parting reply. Rejected on the first
     attempt with a message that names the fix. Honoured on the second with the
     violation recorded, because "a human alerted and nothing sent" is exactly
     what already shipped — this gate can only improve on it, never stall a
     conversation that used to move. Silence stays available: that is `hold`.
  2. POLLER: when the parting line exists it goes out through the ONE send path,
     and the human is raised only AFTER the DM lands. A send that fails leaves
     the row live and retryable rather than paused with nobody answered.

The source assertions at the bottom pin the wiring, because a rule that is not
reachable from the running code is a decoration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integrations"))

import integrations.ig_conversation_brain as brain  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


# ── helpers ─────────────────────────────────────────────────────────────────

def _turns(text: str = "Could I get some help on ai"):
    turns, _ = brain.transcript_window(
        [{"id": "m1", "direction": "incoming", "message": text,
          "createdTime": "2026-09-03T14:37:00.000Z"}],
        participant_id="p1",
    )
    return turns


def _payload(*, action: str, stage: str, reply, handoff_reason=None) -> str:
    return json.dumps({
        "stage": stage,
        "action": action,
        "reply": reply,
        "extracted": {k: None for k in
                      ("name", "email", "phone", "business", "need", "timeline")},
        "memory": {k: None for k in
                   ("budget", "objections", "pitched", "summary")},
        "handoff_reason": handoff_reason,
        "confidence": 0.7,
    })


def _runner_returning(*payloads):
    """A fake model that returns each payload in turn, recording its prompts."""
    seen: list[str] = []
    remaining = list(payloads)

    def runner(prompt, **_kw):
        seen.append(prompt)
        return remaining.pop(0) if remaining else remaining_last[0]

    remaining_last = [payloads[-1]]
    runner.prompts = seen  # type: ignore[attr-defined]
    return runner


SILENT_HANDOFF = _payload(
    action="handoff", stage="handed_off", reply=None,
    handoff_reason="may be genuine, needs human call on disqualify vs engage")
ANSWERED_HANDOFF = _payload(
    action="handoff", stage="handed_off",
    reply="Happy to help with the AI side. Conaugh handles that himself and I am "
          "flagging him now, so he can pick this up with you directly.",
    handoff_reason="asked for AI help, wants a person")


# ── 1. Gate D: a silent handoff is rejected, once ───────────────────────────

def test_a_silent_handoff_is_rejected_on_the_first_attempt():
    """The incident. The model must be asked to answer before it escalates."""
    runner = _runner_returning(SILENT_HANDOFF, ANSWERED_HANDOFF)
    d = brain.decide(_turns(), current_stage="engaged",
                     participant_display_name="Test", runner=runner)
    assert d.ok
    assert d.action == "handoff"
    assert d.reply and "flagging him" in d.reply, "the retry's answer must survive"
    assert d.attempts == 2, "the silent handoff must have cost exactly one retry"


def test_the_retry_prompt_names_the_fix():
    """A rejection the model cannot act on just burns a turn."""
    runner = _runner_returning(SILENT_HANDOFF, ANSWERED_HANDOFF)
    brain.decide(_turns(), current_stage="engaged",
                 participant_display_name="Test", runner=runner)
    second = runner.prompts[1]  # type: ignore[attr-defined]
    assert "YOUR PREVIOUS OUTPUT WAS REJECTED" in second
    assert "no reply" in second, "must say what was wrong"
    assert '"handoff"' in second, "must say to KEEP the handoff, not abandon it"
    assert '"hold"' in second, "must name the action that legitimately sends nothing"


# ── 2. it fails SAFE: a stubborn model still gets its human ─────────────────

def test_a_stubborn_silent_handoff_is_honoured_with_the_violation_recorded():
    """Gate D must never be able to stall a conversation.

    "A human alerted and nothing sent" is the behaviour that already shipped. If
    the model insists twice, we keep it — and count it — rather than returning a
    failure that sends nothing AND raises nobody.
    """
    runner = _runner_returning(SILENT_HANDOFF, SILENT_HANDOFF)
    d = brain.decide(_turns(), current_stage="engaged",
                     participant_display_name="Test", runner=runner)
    assert d.ok, "a twice-insisted handoff must still be a usable decision"
    assert d.action == "handoff"
    assert d.reply is None
    assert "handoff_without_reply" in d.violations
    assert d.attempts == 2


# ── 3. an answered handoff passes straight through ─────────────────────────

def test_an_answered_handoff_needs_no_retry():
    runner = _runner_returning(ANSWERED_HANDOFF)
    d = brain.decide(_turns(), current_stage="engaged",
                     participant_display_name="Test", runner=runner)
    assert d.ok and d.action == "handoff" and d.attempts == 1
    assert d.reply, "the parting line must NOT be nulled the way hold's is"
    assert "handoff_without_reply" not in d.violations


def test_a_hold_may_still_say_nothing():
    """Silence did not become illegal — it moved to the action that means it."""
    runner = _runner_returning(_payload(
        action="hold", stage="engaged", reply=None,
        handoff_reason="they asked us to stop"))
    d = brain.decide(_turns("stop messaging me"), current_stage="engaged",
                     participant_display_name="Test", runner=runner)
    assert d.ok and d.action == "hold" and d.reply is None and d.attempts == 1
    assert "handoff_without_reply" not in d.violations


# ── 4. the parting line is held to the same copy rules as any other ────────

def test_a_handoff_reply_goes_through_the_copy_guardrails():
    """It is sent to a real person, so it is not exempt.

    Proven by making the parting line break a guardrail and watching the SAME
    rejection machinery fire: over-length copy is a guardrail_reject.
    """
    over_long = "x " * 400
    runner = _runner_returning(
        _payload(action="handoff", stage="handed_off", reply=over_long,
                 handoff_reason="needs a person"),
        ANSWERED_HANDOFF,
    )
    d = brain.decide(_turns(), current_stage="engaged",
                     participant_display_name="Test", runner=runner)
    assert d.attempts == 2, "the bad copy must have been rejected and retried"
    assert d.ok and d.reply and "flagging him" in d.reply


# ── 5. the rules are WIRED ──────────────────────────────────────────────────

def test_the_poller_sends_the_parting_line_before_raising_the_human():
    src = (REPO / "scripts" / "integrations" / "instagram_dm_poller.py").read_text(
        encoding="utf-8")
    branch = src[src.index('if decision.action == "handoff":'):]
    branch = branch[: branch.index("return delta") + len("return delta")]
    assert 'if not str(decision.reply or "").strip():' in branch, (
        "the early return must be conditional on there being nothing to send")
    assert "handoff_after_send = reason" in src, (
        "an answered handoff must fall through to the send path")

    # ...and exactly one of the two notifiers runs after the send.
    tail = src[src.index("if handoff_after_send:"):]
    tail = tail[: tail.index("# ── 19.")]
    assert "handoff(row_id, reason=handoff_after_send" in tail
    assert "_flag_terminal_ending(" in tail and "else:" in tail, (
        "the answered-handoff notify and _flag_terminal_ending must be exclusive; "
        "running both pages twice for one conversation")


def test_the_brain_gate_is_reachable_and_first_attempt_only():
    src = (REPO / "scripts" / "integrations" / "ig_conversation_brain.py").read_text(
        encoding="utf-8")
    assert 'if action == "handoff" and not parting and attempt == 1:' in src, (
        "Gate D must be scoped to the first attempt so it cannot stall a thread")
    assert 'sends_copy = action in {"reply", "book"} or (' in src, (
        "a handoff's reply must reach validate_reply")


def test_the_prompt_teaches_the_split():
    src = (REPO / "scripts" / "integrations" / "ig_conversation_brain.py").read_text(
        encoding="utf-8")
    playbook = src[src.index("  handoff  "):]
    playbook = playbook[: playbook.index("  book     ")]
    assert "The reply is NOT optional here" in playbook
    assert "use hold, not handoff" in playbook, (
        "the prompt must name the action that legitimately sends nothing")
    assert "ENGAGE" in playbook, (
        "the model must be told which way to err when it is torn")
    assert "null ONLY when action is hold" in src, (
        "the reply FIELD spec still said null for handoff; the model reads that "
        "line, not the action menu, when it fills the field")
