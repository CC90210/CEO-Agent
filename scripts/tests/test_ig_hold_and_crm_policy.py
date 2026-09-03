"""A hold may not end a conversation, and a DM is not a lead until it has both
contact fields.

WHY THIS EXISTS
---------------
2026-09-03, 05:05Z: the operator DM'd the account from a test profile — three
casual greetings. The model chose action=hold with stage=disqualified. The
poller applied it: stage moved, set_stage paused the automation, and the
relationship ended with nothing sent and no record of the reasoning (a hold
never wrote last_decision_json; the row still carried a decision from
2026-08-21). The operator got a Telegram saying the conversation had closed,
and no reply on Instagram.

Two policy decisions came out of it, both the operator's:

  1. A hold means "send nothing this turn". It may carry the stage one step;
     it may never END the thread. A terminal proposal on a hold is a REQUEST
     for a human, with the model's reason attached.
  2. A DM thread earns a CRM lead only once the prospect has given BOTH an
     email and a phone number. Until then the agent's job is to get them.

Plus one repair: a prospect the MODEL wrote off, who then writes back, is
engaged again. An operator's disqualify is not.

These are pure rules, tested as such; the source assertions at the bottom pin
that the poller actually calls them, because a rule that exists but is not
wired is a decoration.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integrations"))

from integrations.instagram_dm_poller import (  # noqa: E402
    TERMINAL_STAGES,
    _crm_lead_ready,
    _hold_disposition,
    _reopen_reason,
)

REPO = Path(__file__).resolve().parent.parent.parent


# ── 1. a hold may step forward, never end ───────────────────────────────────

def test_a_hold_may_carry_the_stage_one_step():
    stage, review = _hold_disposition("engaged", "qualified")
    assert stage == "qualified"
    assert review is None


def test_a_hold_at_the_same_stage_is_a_plain_hold():
    stage, review = _hold_disposition("engaged", "engaged")
    assert (stage, review) == ("engaged", None)


def test_a_hold_may_not_disqualify():
    """The incident. Three greetings, a hold, and a relationship ended."""
    stage, review = _hold_disposition("engaged", "disqualified")
    assert stage == "engaged", "the stage must not move to a terminal value on a hold"
    assert review and "disqualified" in review and "confirm" in review


def test_no_terminal_stage_is_reachable_by_a_hold():
    for terminal in TERMINAL_STAGES:
        stage, review = _hold_disposition("engaged", terminal)
        assert stage == "engaged", f"{terminal} must not be applied on a hold"
        assert review, f"a terminal proposal on a hold must request review ({terminal})"


def test_a_terminal_stage_already_reached_is_left_alone():
    """Idempotent: if the row IS disqualified (by an operator), a hold that
    restates it is not a new request."""
    assert _hold_disposition("disqualified", "disqualified") == ("disqualified", None)


# ── 2. a DM is not a lead until it has both contact fields ──────────────────

def test_both_fields_present_earns_a_lead():
    assert _crm_lead_ready({"extracted_email": "a@b.co", "extracted_phone": "+15145550000"})


def test_email_alone_does_not():
    assert not _crm_lead_ready({"extracted_email": "a@b.co", "extracted_phone": None})


def test_phone_alone_does_not():
    assert not _crm_lead_ready({"extracted_email": None, "extracted_phone": "+15145550000"})


def test_blank_strings_do_not_count():
    """The extraction layer can store "" — that is not a phone number."""
    assert not _crm_lead_ready({"extracted_email": "  ", "extracted_phone": ""})


def test_a_first_reply_earns_nothing():
    """The old behaviour: a lead with both fields null on the first reply."""
    assert not _crm_lead_ready({})


# ── 3. a model write-off reopens on a new message; an operator's does not ──

def _row(stage, last_error, entered):
    return {"stage": stage, "last_error": last_error, "stage_entered_at": entered}


def test_a_model_disqualify_reopens_when_they_write_again():
    row = _row("disqualified", "model hold", "2026-09-03T05:06:46+00:00")
    conv = {"updatedTime": "2026-09-03T07:00:00.000Z"}
    assert _reopen_reason(row, conv)


def test_it_stays_closed_until_they_actually_write():
    """Same stage, same reason — but nothing new in the thread."""
    row = _row("disqualified", "model hold", "2026-09-03T05:06:46+00:00")
    conv = {"updatedTime": "2026-09-03T05:05:20.232Z"}  # before the disqualify
    assert _reopen_reason(row, conv) is None


def test_an_operator_disqualify_never_reopens():
    """The operator's 'no' outranks a new 'hey'."""
    row = _row("disqualified", "spam account, do not engage", "2026-09-01T00:00:00+00:00")
    conv = {"updatedTime": "2026-09-03T07:00:00.000Z"}
    assert _reopen_reason(row, conv) is None


def test_handed_off_and_booked_are_never_reopened_here():
    for stage in ("handed_off", "booked"):
        row = _row(stage, "model hold", "2026-09-01T00:00:00+00:00")
        assert _reopen_reason(row, {"updatedTime": "2026-09-03T07:00:00.000Z"}) is None


def test_an_unparseable_timestamp_leaves_it_paused():
    """Fail closed: a bad stamp is not evidence that they wrote back."""
    row = _row("disqualified", "model hold", "garbage")
    assert _reopen_reason(row, {"updatedTime": "2026-09-03T07:00:00.000Z"}) is None


# ── 4. the rules are WIRED, not merely defined ──────────────────────────────

def test_the_poller_actually_uses_the_rules():
    src = (REPO / "scripts" / "integrations" / "instagram_dm_poller.py").read_text(encoding="utf-8")
    hold = src[src.index('if decision.action == "hold":'):]
    hold = hold[: hold.index("return delta")]
    assert "_hold_disposition(" in hold, "the hold branch must ask _hold_disposition"
    assert "state.record_hold(" in hold, "a hold must persist the model's reasoning"
    assert "stage=decision.stage" not in hold, (
        "the hold branch must never apply the model's proposed stage unconditionally"
    )
    crm = src[src.index("# ── 19. CRM projection"):]
    crm = crm[: crm.index("# ── 20.")]
    assert "_crm_lead_ready(row)" in crm and "_upsert_lead(" in crm, (
        "the CRM write must be gated on _crm_lead_ready"
    )
    assert "_reopen_reason(row, conv)" in src and "state.reopen_from_inbound(" in src


def test_the_dao_records_holds_and_reopens_narrowly():
    src = (REPO / "scripts" / "integrations" / "ig_dm_state.py").read_text(encoding="utf-8")
    assert "def record_hold(" in src
    reopen = src[src.index("def reopen_from_inbound("):]
    reopen = reopen[: reopen.index("\ndef ", 1)] if "\ndef " in reopen[1:] else reopen
    assert '!= "disqualified"' in reopen, "reopen must refuse any stage but disqualified"
    assert 'startswith("model")' in reopen, "reopen must refuse an operator's disqualify"
