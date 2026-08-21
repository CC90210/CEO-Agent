"""ig_dm_state.py — the Instagram DM closer's memory. The ONLY module here that writes SQL.

One row of `instagram_dm_conversations` per Instagram thread: what stage the
relationship is at, what the prospect actually told us, how many replies we have
spent today, whether a human has taken over, and whether a meeting exists.

    poller ──▶ brain (pure)        poller ──▶ ig_dm_state ◀── ig_closer

This module imports the stage machine FROM ig_conversation_brain so there is
exactly one copy of it. It imports nothing from ig_closer or the poller.

──────────────────────────────────────────────────────────────────────────────
THREE DEFECTS IN THE SUBSTRATE THIS MODULE IS BUILT AROUND. Each was proved on
this machine, not inherited from a doc:

1. `TursoDB.execute()` DOES NOT COMMIT — and neither does `TursoDB.insert()`.
   Proved 2026-08-20 against a local libSQL file: after db.insert() and
   db.execute(), the writing process saw both rows and a SEPARATE process saw
   ZERO. No error, no warning. Only `TursoDB.claim()` commits (db_turso.py:608).
   A daemon that writes state and reports success would be lying, and the state
   would evaporate on process exit.
   => EVERY write in this module goes through _write(), which commits. There is
      no other write path, deliberately: a rule you have to remember is a rule
      that gets forgotten at 2am.

2. `TursoDB.execute()` returns a cursor that is TRUTHY even when it matched
   nothing, so `if db.execute(...)` reports success for a no-op UPDATE. Every
   existence test and every compare-and-swap here reads the row back with
   `.query()` and compares the value. rowcount is never trusted.

3. Any table with a `tenant_id` column is auto-registered tenant-scoped
   (db_turso.py:379-391) and every statement needs a `tenant_id = ?` predicate.
   There is no `allow_unscoped=True` in this file. All four statement shapes
   used here were checked against `unscoped_tables()` and pass unaided.

──────────────────────────────────────────────────────────────────────────────
WHAT THIS REPLACED. state/instagram_dm_state.json was a re-send bomb:
_load_state() reset to an empty dict on JSONDecodeError and write_text() is not
atomic, so ONE torn write cleared every cooldown and the next --live run would
re-DM the entire inbox. seen_messages was truncated to the last 2000 ids, so ids
aged out and became re-processable. migrate_legacy_json_state() imports what it
can and renames the file so it can never be read again.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

# ONE copy of the stage machine, imported rather than restated. A second copy
# drifts, and the two halves of the system then disagree about what a legal
# move is — with the DB half winning silently.
from ig_conversation_brain import (  # noqa: E402
    STAGES,
    is_legal_transition,
)

CAPABILITY_META = {
    "category": "growth.inbound",
    "lifecycle": "active",
    "risk": "state_write",
    "triggers": ["instagram dm state", "dm conversation state", "ig handoffs"],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": False},
}

TABLE = "instagram_dm_conversations"
PROVIDER = "instagram"
OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

TERMINAL_STAGES = frozenset({"booked", "handed_off", "disqualified"})
BOOKING_STATUSES = ("none", "claimed", "booked", "failed")

DAILY_REPLY_CAP_PER_CONVERSATION = 3
DAILY_REPLY_CAP_GLOBAL = 40
MIN_REPLY_GAP_SECONDS = 120
MAX_CONSECUTIVE_MODEL_FAILURES = 3
MAX_CONSECUTIVE_GUARDRAIL_REJECTS = 2

LEGACY_STATE_PATH = PROJECT_ROOT / "state" / "instagram_dm_state.json"

_MAX_ERROR_CHARS = 300
_MAX_BOOKING_ERROR_CHARS = 500


class IgStateError(RuntimeError):
    """The conversation row cannot be used as asked."""


class IllegalTransition(IgStateError):
    """A stage move the machine forbids."""


class BookingClaimLost(IgStateError):
    """The booking claim is no longer ours; another process owns this meeting."""


# ── time ─────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _today(now: Optional[datetime] = None) -> str:
    return (now or _now()).strftime("%Y-%m-%d")


def _parse_iso(value: Any) -> Optional[datetime]:
    """None when unparseable. Every caller treats None as "cannot prove it" and
    picks the SAFE branch — the old _in_cooldown returned False on ValueError,
    which permitted an immediate re-send to someone we had just messaged."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── the single write path ────────────────────────────────────────────────────

def get_db_handle():
    """The raw TursoDB. One place to patch in tests."""
    from lib.db_turso import get_db  # type: ignore

    return get_db()


def _write(db, sql: str, params: Any) -> None:
    """Execute and COMMIT. The only write path in this module.

    db.execute() does not commit (proved cross-process, see the module
    docstring), so a write that skipped this helper would be visible to the
    writing process, invisible to everyone else, and gone on exit.
    """
    db.execute(sql, tuple(params))
    db.commit()


def _extracted_field(extracted: Any, name: str) -> Optional[str]:
    """One field off a brain Extracted, or off a plain mapping with the same keys.

    Empty and whitespace-only collapse to None so that "the prospect did not
    mention it again" can never be written over a fact they already gave us.
    """
    value = getattr(extracted, name, None)
    if value is None and isinstance(extracted, Mapping):
        value = extracted.get(name)
    text = str(value).strip() if value is not None else ""
    return text or None


def _row(db, row_id: str, tenant_id: str) -> Optional[dict]:
    rows = db.query(
        f"select * from {TABLE} where tenant_id = ? and id = ?",
        (tenant_id, str(row_id)),
    )
    return dict(rows[0]) if rows else None


def _require_row(db, row_id: str, tenant_id: str) -> dict:
    row = _row(db, row_id, tenant_id)
    if row is None:
        raise IgStateError(f"conversation row {row_id!r} not found for tenant {tenant_id!r}")
    return row


def _touch(db, row_id: str, tenant_id: str, assignments: dict[str, Any]) -> dict:
    """UPDATE ... SET <assignments>, updated_at = now. Returns the refreshed row.

    Read back rather than assumed: execute()'s cursor is truthy even when the
    UPDATE matched nothing, so the returned row IS the verification.
    """
    payload = dict(assignments)
    payload["updated_at"] = _iso()
    sets = ", ".join(f"{col} = ?" for col in payload)
    _write(
        db,
        f"update {TABLE} set {sets} where tenant_id = ? and id = ?",
        list(payload.values()) + [tenant_id, str(row_id)],
    )
    return _require_row(db, row_id, tenant_id)


# ── read ─────────────────────────────────────────────────────────────────────

def get_or_create(db, *, conv: Mapping[str, Any],
                  tenant_id: str = OASIS_TENANT_ID) -> dict:
    """The row for this Zernio conversation, creating it on first sight.

    INSERT OR IGNORE against idx_ig_dm_conv_unique, then SELECT. When two polls
    race, the loser's insert is ignored and it reads back the WINNER's row —
    which is why the id is generated locally but never trusted as the identity.
    """
    conversation_id = str(conv.get("id") or "").strip()
    participant_id = str(conv.get("participantId") or "").strip()
    account_id = str(conv.get("accountId") or "").strip()
    missing = [n for n, v in (("id", conversation_id),
                              ("participantId", participant_id),
                              ("accountId", account_id)) if not v]
    if missing:
        raise IgStateError(
            f"conversation is missing {', '.join(missing)} — without them the row "
            f"has no stable identity and would duplicate on every poll"
        )

    now = _iso()
    _write(
        db,
        f"insert or ignore into {TABLE} "
        "(id, tenant_id, provider, provider_conversation_id, participant_id, "
        " participant_handle, participant_name, account_id, stage, "
        " stage_entered_at, created_at, updated_at) "
        "values (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)",
        (
            str(uuid.uuid4()), tenant_id, PROVIDER, conversation_id, participant_id,
            (conv.get("participantUsername") or None),
            (conv.get("participantName") or None),
            account_id, now, now, now,
        ),
    )
    rows = db.query(
        f"select * from {TABLE} "
        "where tenant_id = ? and provider = ? and provider_conversation_id = ?",
        (tenant_id, PROVIDER, conversation_id),
    )
    if not rows:
        raise IgStateError(
            f"insert of conversation {conversation_id!r} left no row — the write "
            f"did not commit or the unique index is missing"
        )
    return dict(rows[0])


def get_by_conversation_id(db, provider_conversation_id: str, *,
                           tenant_id: str = OASIS_TENANT_ID) -> Optional[dict]:
    rows = db.query(
        f"select * from {TABLE} "
        "where tenant_id = ? and provider = ? and provider_conversation_id = ?",
        (tenant_id, PROVIDER, str(provider_conversation_id)),
    )
    return dict(rows[0]) if rows else None


def list_by_stage(db, stage: str, *, tenant_id: str = OASIS_TENANT_ID,
                  limit: int = 50) -> list[dict]:
    rows = db.query(
        f"select * from {TABLE} where tenant_id = ? and stage = ? "
        "order by updated_at desc limit ?",
        (tenant_id, str(stage), int(limit)),
    )
    return [dict(r) for r in rows]


def list_handoffs(db, *, tenant_id: str = OASIS_TENANT_ID, limit: int = 50) -> list[dict]:
    rows = db.query(
        f"select * from {TABLE} where tenant_id = ? and handoff_pending = 1 "
        "order by updated_at desc limit ?",
        (tenant_id, int(limit)),
    )
    return [dict(r) for r in rows]


def list_all(db, *, tenant_id: str = OASIS_TENANT_ID, limit: int = 50) -> list[dict]:
    rows = db.query(
        f"select * from {TABLE} where tenant_id = ? order by updated_at desc limit ?",
        (tenant_id, int(limit)),
    )
    return [dict(r) for r in rows]


# ── the reply budget (replaces the 24h cooldown) ─────────────────────────────

def reply_budget(db, row: Mapping[str, Any], *, now: Optional[datetime] = None,
                 tenant_id: str = OASIS_TENANT_ID) -> tuple[bool, str]:
    """(allowed, reason). The throttle that replaced COOLDOWN_HOURS.

    A 24h gag is right for a one-shot autoresponder and fatal for a closer: the
    prospect answers a question and waits a day for the follow-up. Three replies
    per conversation per UTC day, forty across the tenant, two minutes apart.

    FAILS CLOSED on an unparseable last_outbound_at. The old _in_cooldown
    returned False there, which permitted an immediate re-send.
    """
    when = now or _now()

    if int(row.get("automation_paused") or 0):
        return False, "paused"
    stage = str(row.get("stage") or "")
    if stage in TERMINAL_STAGES:
        return False, f"terminal:{stage}"

    replies_today = int(row.get("replies_today") or 0)
    if str(row.get("replies_today_date") or "") != _today(when):
        replies_today = 0
    if replies_today >= DAILY_REPLY_CAP_PER_CONVERSATION:
        return False, "conv_cap"

    last_out_raw = row.get("last_outbound_at")
    if last_out_raw:
        last_out = _parse_iso(last_out_raw)
        if last_out is None:
            # Cannot prove enough time has passed => assume it has not.
            return False, "gap"
        if (when - last_out) < timedelta(seconds=MIN_REPLY_GAP_SECONDS):
            return False, "gap"

    rows = db.query(
        f"select coalesce(sum(replies_today), 0) as n from {TABLE} "
        "where tenant_id = ? and replies_today_date = ?",
        (tenant_id, _today(when)),
    )
    if rows and int(rows[0].get("n") or 0) >= DAILY_REPLY_CAP_GLOBAL:
        return False, "global_cap"

    return True, "ok"


# ── message accounting ───────────────────────────────────────────────────────

def record_inbound(db, row_id: str, *, message_id: str, at_iso: str,
                   tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Mark this inbound message consumed. NEVER called by a dry run."""
    current = _require_row(db, row_id, tenant_id)
    return _touch(db, row_id, tenant_id, {
        "last_processed_message_id": str(message_id or "") or None,
        "last_inbound_at": str(at_iso or _iso()),
        "inbound_message_count": int(current.get("inbound_message_count") or 0) + 1,
    })


def record_outbound(db, row_id: str, *, decision: Any, message_sent: str,
                    at: Optional[datetime] = None,
                    tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Called AFTER the Zernio POST succeeds, never before.

    This write is what closes the double-send window, so it must land even when
    something else about the decision is wrong. If the stage move is illegal the
    stage STAYS PUT and the anomaly is recorded in last_error — the counters,
    last_outbound_at and replies_today are still written.

    DEVIATION, deliberate: the contract's parenthetical reads "IllegalTransition
    -> caller logs and continues". Raising here would abort the caller before it
    could record the inbound message id, so the next poll would re-decide the
    same message and could send a SECOND DM to a real person. A message that has
    already left the machine must always be recorded. The anomaly is surfaced in
    the returned row instead of thrown.
    """
    when = at or _now()
    current = _require_row(db, row_id, tenant_id)
    current_stage = str(current.get("stage") or "new")
    next_stage = str(getattr(decision, "stage", None) or current_stage)

    assignments: dict[str, Any] = {
        "last_outbound_at": _iso(when),
        "reply_count_total": int(current.get("reply_count_total") or 0) + 1,
        "consecutive_model_failures": 0,
        "consecutive_guardrail_rejects": 0,
    }

    # replies_today resets when the stored date is not today (UTC).
    if str(current.get("replies_today_date") or "") == _today(when):
        assignments["replies_today"] = int(current.get("replies_today") or 0) + 1
    else:
        assignments["replies_today"] = 1
    assignments["replies_today_date"] = _today(when)

    if next_stage != current_stage:
        if is_legal_transition(current_stage, next_stage):
            assignments["stage"] = next_stage
            assignments["stage_entered_at"] = _iso(when)
            if next_stage in TERMINAL_STAGES:
                assignments["automation_paused"] = 1
        else:
            assignments["last_error"] = (
                f"illegal_transition: {current_stage} -> {next_stage} "
                f"(the DM was sent; stage left unchanged)"
            )
            print(f"[ig_dm_state] ILLEGAL STAGE MOVE {current_stage} -> {next_stage} "
                  f"on {row_id}; reply recorded, stage unchanged", file=sys.stderr)

    try:
        assignments["last_decision_json"] = json.dumps(decision.as_dict())
    except (AttributeError, TypeError, ValueError) as exc:
        assignments["last_decision_json"] = json.dumps(
            {"unserializable_decision": str(exc)[:200]})

    del message_sent  # the DM text lives in the thread; storing it twice ages badly
    return _touch(db, row_id, tenant_id, assignments)


# ── extraction ───────────────────────────────────────────────────────────────

def apply_extraction(db, row_id: str, *, extracted: Any,
                     email_source_message_id: Optional[str] = None,
                     tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Merge what the prospect said into the row. COALESCE semantics IN SQL.

    A None or empty field NEVER overwrites a stored value — the model is asked
    for facts stated in THIS turn, so a blank means "not mentioned again", not
    "retracted".

    extracted_email is FIRST-WRITE-WINS. A second, DIFFERENT address is ignored
    and raises a handoff: an address that changes mid-thread is either a typo
    that would send the invite into the void, or someone redirecting a meeting
    to an inbox the prospect does not control.
    """
    def _f(name: str) -> Optional[str]:
        return _extracted_field(extracted, name)

    current = _require_row(db, row_id, tenant_id)
    stored_email = (str(current.get("extracted_email") or "").strip().lower() or None)
    new_email = (_f("email") or "").lower() or None

    _write(
        db,
        f"update {TABLE} set "
        "extracted_name = coalesce(?, extracted_name), "
        "extracted_phone = coalesce(?, extracted_phone), "
        "extracted_business = coalesce(?, extracted_business), "
        "extracted_need = coalesce(?, extracted_need), "
        "extracted_timeline = coalesce(?, extracted_timeline), "
        "extracted_email = coalesce(extracted_email, ?), "
        "extracted_email_source_msg_id = coalesce(extracted_email_source_msg_id, ?), "
        "updated_at = ? "
        "where tenant_id = ? and id = ?",
        (
            _f("name"), _f("phone"), _f("business"), _f("need"), _f("timeline"),
            new_email,
            (str(email_source_message_id) if (new_email and email_source_message_id)
             else None),
            _iso(), tenant_id, str(row_id),
        ),
    )

    if stored_email and new_email and new_email != stored_email:
        print(f"[ig_dm_state] EMAIL CHANGED on {row_id}: a second address arrived and "
              f"was ignored (first-write-wins); handing to a human", file=sys.stderr)
        return request_handoff(db, row_id, reason="email_changed", tenant_id=tenant_id)

    return _require_row(db, row_id, tenant_id)


def reset_email(db, row_id: str, *, tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Operator CLI only. The one way past first-write-wins."""
    return _touch(db, row_id, tenant_id, {
        "extracted_email": None, "extracted_email_source_msg_id": None,
    })


# ── failure accounting ───────────────────────────────────────────────────────

def record_failure(db, row_id: str, *, kind: str, detail: str,
                   tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Count a failed turn, and escalate to a human when they stack up.

    Two consecutive guardrail rejections is the signature of an injection
    attempt, not a bad day for the model — that is why its threshold is lower
    than the model-unavailable one. Returns the refreshed row so the caller can
    see whether the handoff fired and notify.
    """
    current = _require_row(db, row_id, tenant_id)
    is_model = str(kind) == "model_unavailable"
    field = "consecutive_model_failures" if is_model else "consecutive_guardrail_rejects"
    limit = (MAX_CONSECUTIVE_MODEL_FAILURES if is_model
             else MAX_CONSECUTIVE_GUARDRAIL_REJECTS)
    count = int(current.get(field) or 0) + 1

    assignments: dict[str, Any] = {
        field: count,
        "last_error": f"{kind}: {str(detail or '')[:_MAX_ERROR_CHARS]}",
    }
    if count >= limit:
        assignments.update({
            "handoff_pending": 1,
            "handoff_reason": f"auto: {kind} x{count}",
            "stage": "handed_off",
            "stage_entered_at": _iso(),
            "automation_paused": 1,
        })
        print(f"[ig_dm_state] ESCALATING {row_id} to a human: {kind} x{count}",
              file=sys.stderr)
    return _touch(db, row_id, tenant_id, assignments)


# ── stage ────────────────────────────────────────────────────────────────────

def set_stage(db, row_id: str, *, stage: str, reason: Optional[str] = None,
              tenant_id: str = OASIS_TENANT_ID, force: bool = False) -> dict:
    """Move the conversation. Raises IllegalTransition unless force=True.

    force is reserved for the operator CLI and for ig_closer writing 'booked' —
    which no other caller may set, because 'booked' asserts that an event exists
    in Google Calendar and only the closer can know that.
    """
    if stage not in STAGES:
        raise IllegalTransition(f"{stage!r} is not a stage; known: {list(STAGES)}")
    current = _require_row(db, row_id, tenant_id)
    current_stage = str(current.get("stage") or "new")

    if not force and not is_legal_transition(current_stage, stage):
        raise IllegalTransition(
            f"{current_stage} -> {stage} is not a legal move"
            + (f" ({reason})" if reason else "")
        )

    assignments: dict[str, Any] = {"stage": stage}
    if stage != current_stage:
        assignments["stage_entered_at"] = _iso()
    if stage in TERMINAL_STAGES:
        # Terminal means the poller must not spend another model call here.
        assignments["automation_paused"] = 1
    if reason:
        assignments["last_error"] = str(reason)[:_MAX_ERROR_CHARS]
    return _touch(db, row_id, tenant_id, assignments)


def request_handoff(db, row_id: str, *, reason: str,
                    tenant_id: str = OASIS_TENANT_ID) -> dict:
    """A human owns this conversation now. Idempotent."""
    return _touch(db, row_id, tenant_id, {
        "handoff_pending": 1,
        "handoff_reason": str(reason)[:_MAX_ERROR_CHARS],
        "stage": "handed_off",
        "stage_entered_at": _iso(),
        "automation_paused": 1,
    })


def resume(db, row_id: str, *, stage: str = "engaged",
           tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Operator only: hand a conversation back to the automation."""
    if stage not in STAGES:
        raise IllegalTransition(f"{stage!r} is not a stage")
    return _touch(db, row_id, tenant_id, {
        "stage": stage, "stage_entered_at": _iso(),
        "automation_paused": 0, "handoff_pending": 0, "handoff_reason": None,
        "consecutive_model_failures": 0, "consecutive_guardrail_rejects": 0,
    })


def pause(db, row_id: str, *, tenant_id: str = OASIS_TENANT_ID) -> dict:
    return _touch(db, row_id, tenant_id, {"automation_paused": 1})


def link_crm_lead(db, row_id: str, *, lead_id: str,
                  tenant_id: str = OASIS_TENANT_ID) -> dict:
    return _touch(db, row_id, tenant_id, {"lead_id": str(lead_id)})


# ── booking: compare-and-swap with read-back ─────────────────────────────────

def claim_booking(db, row_id: str, *, claim_token: str,
                  tenant_id: str = OASIS_TENANT_ID) -> bool:
    """THE idempotency boundary. True iff THIS caller now owns the booking.

    Conditional UPDATE, then READ THE ROW BACK and compare the token. rowcount
    is not a contract on this driver and execute()'s cursor is truthy even when
    it changed nothing, so a rowcount-based claim would report a win to every
    racer and mail two Google invites for one prospect.

    False means: someone else owns it, or it already booked, or a prior attempt
    FAILED and needs an operator reset. Never retry a False into a True.
    """
    if not claim_token:
        raise IgStateError("claim_booking requires a non-empty claim token")
    _write(
        db,
        f"update {TABLE} set booking_status = 'claimed', booking_claim_token = ?, "
        "booking_claimed_at = ?, updated_at = ? "
        "where tenant_id = ? and id = ? and booking_status = 'none'",
        (str(claim_token), _iso(), _iso(), tenant_id, str(row_id)),
    )
    rows = db.query(
        f"select booking_claim_token from {TABLE} where tenant_id = ? and id = ?",
        (tenant_id, str(row_id)),
    )
    return bool(rows) and str(rows[0].get("booking_claim_token") or "") == str(claim_token)


def finalize_booking(db, row_id: str, *, claim_token: str, start_iso: str,
                     end_iso: str, meet_link: str, email_status: str,
                     tenant_id: str = OASIS_TENANT_ID) -> dict:
    """The meeting exists. Guarded by the claim token; a zero-effect update raises."""
    _write(
        db,
        f"update {TABLE} set booking_status = 'booked', booked_start = ?, "
        "booked_end = ?, booked_meet_link = ?, booking_email_status = ?, "
        "stage = 'booked', stage_entered_at = ?, automation_paused = 1, updated_at = ? "
        "where tenant_id = ? and id = ? and booking_claim_token = ?",
        (str(start_iso), str(end_iso), str(meet_link), str(email_status),
         _iso(), _iso(), tenant_id, str(row_id), str(claim_token)),
    )
    row = _require_row(db, row_id, tenant_id)
    if (str(row.get("booking_status") or "") != "booked"
            or str(row.get("booking_claim_token") or "") != str(claim_token)):
        raise BookingClaimLost(
            f"finalize_booking on {row_id} changed nothing: the claim token no longer "
            f"matches (status={row.get('booking_status')!r}). Another process owns "
            f"this booking."
        )
    return row


def fail_booking(db, row_id: str, *, claim_token: str, error: str,
                 tenant_id: str = OASIS_TENANT_ID) -> dict:
    """A booking attempt died after the claim was taken.

    'failed' NEVER returns to 'none' automatically. That is precisely what makes
    double-booking impossible after a PARTIAL success — where the calendar event
    exists but a later step blew up, and a retry would create a second meeting.
    Only reset_booking(), run by a human who has looked at the calendar, reopens it.
    """
    _write(
        db,
        f"update {TABLE} set booking_status = 'failed', booking_error = ?, "
        "handoff_pending = 1, handoff_reason = 'booking failed', "
        "stage = 'handed_off', stage_entered_at = ?, automation_paused = 1, "
        "updated_at = ? "
        "where tenant_id = ? and id = ? and booking_claim_token = ?",
        (str(error)[:_MAX_BOOKING_ERROR_CHARS], _iso(), _iso(),
         tenant_id, str(row_id), str(claim_token)),
    )
    row = _require_row(db, row_id, tenant_id)
    if str(row.get("booking_status") or "") != "failed":
        raise BookingClaimLost(
            f"fail_booking on {row_id} changed nothing "
            f"(status={row.get('booking_status')!r}) — the claim is not ours"
        )
    return row


def reset_booking(db, row_id: str, *, tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Operator CLI only. Check the calendar BEFORE running this."""
    return _touch(db, row_id, tenant_id, {
        "booking_status": "none", "booking_claim_token": None,
        "booking_claimed_at": None, "booking_error": None,
    })


# ── the `leads` bridge ───────────────────────────────────────────────────────

def ensure_booking_lead(db, row: Mapping[str, Any], *, extracted: Any, apply: bool,
                        tenant_id: str = OASIS_TENANT_ID) -> Optional[str]:
    """The legacy `leads` row a booking needs. THE ONLY place this system writes one.

    book_discovery_call.load_lead() reads db.table("leads") (84 rows); the DM
    lead lives in tenant_records (32k rows). Bridging is unavoidable, so it is
    made VISIBLE and operator-gated instead of silent: apply=False creates
    nothing, and the notes field carries the lineage of both ids so the two
    tables can be reconciled later.
    """
    existing = str(row.get("booking_lead_id") or "").strip()
    if existing:
        return existing
    if not apply:
        return None

    def _f(name: str) -> Optional[str]:
        return _extracted_field(extracted, name)

    handle = row.get("participant_handle") or row.get("participant_id") or "unknown"
    # `name` is NOT NULL in the live DDL, so it needs three fallbacks, not one.
    name = _f("name") or row.get("participant_name") or f"@{handle}"
    lead_id = str(uuid.uuid4())
    now = _iso()

    db.insert("leads", {
        "id": lead_id,
        "name": name,
        "email": _f("email"),
        "phone": _f("phone"),
        "company": _f("business"),
        "source": "instagram_dm",
        "status": "qualified",          # `leads` has `status`, NOT `stage`
        "score": 70,
        "assigned_to": "bravo",
        "notes": ("Bridged from Instagram DM. "
                  f"conversation={row.get('provider_conversation_id')} "
                  f"tenant_records_lead={row.get('lead_id')}"),
        "created_at": now,
        "updated_at": now,
    }, tenant_id=tenant_id)
    # insert() does NOT commit — proved cross-process. Without this the booking
    # would reference a lead row that no other process can see.
    db.commit()

    _touch(db, str(row["id"]), tenant_id, {"booking_lead_id": lead_id})
    return lead_id


# ── one-shot import of the retired JSON file ─────────────────────────────────

def migrate_legacy_json_state(db, *, state_path: Path = LEGACY_STATE_PATH,
                              tenant_id: str = OASIS_TENANT_ID,
                              apply: bool = False) -> dict:
    """Import state/instagram_dm_state.json, then make it unreadable.

    replied{participantId: iso} -> last_outbound_at on the matching row.
    seen_messages[-1]           -> last_processed_message_id (best effort; the
                                   old list was truncated to 2000 ids, so it is
                                   not authoritative for anything older).
    apply=True renames the file to .migrated so no future run can read it.
    """
    result = {"scanned": 0, "matched": 0, "updated": 0, "applied": bool(apply)}
    if not state_path.exists():
        result["note"] = f"no legacy state file at {state_path}"
        return result

    try:
        legacy = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # Loud, not silent: this file being unreadable is exactly the failure
        # that used to clear every cooldown and re-DM the whole inbox.
        result["note"] = f"legacy state unreadable ({exc}); nothing imported"
        print(f"[ig_dm_state] legacy state unreadable: {exc}", file=sys.stderr)
        return result

    replied = legacy.get("replied") or {}
    seen = legacy.get("seen_messages") or []
    last_seen = str(seen[-1]) if seen else None

    for participant_id, iso in replied.items():
        result["scanned"] += 1
        rows = db.query(
            f"select id, last_outbound_at from {TABLE} "
            "where tenant_id = ? and provider = ? and participant_id = ?",
            (tenant_id, PROVIDER, str(participant_id)),
        )
        if not rows:
            continue
        result["matched"] += 1
        if not apply:
            continue
        assignments: dict[str, Any] = {"last_outbound_at": str(iso)}
        if last_seen:
            assignments["last_processed_message_id"] = last_seen
        _touch(db, str(rows[0]["id"]), tenant_id, assignments)
        result["updated"] += 1

    if apply:
        target = state_path.with_suffix(state_path.suffix + ".migrated")
        state_path.replace(target)
        result["renamed_to"] = str(target)
    return result


# ── operator CLI ─────────────────────────────────────────────────────────────

_SHOW_FIELDS = (
    "id", "provider_conversation_id", "participant_handle", "participant_name",
    "stage", "automation_paused", "handoff_pending", "handoff_reason",
    "booking_status", "booked_start", "replies_today", "replies_today_date",
    "reply_count_total", "last_inbound_at", "last_outbound_at",
    "last_processed_message_id", "extracted_name", "extracted_email",
    "extracted_business", "extracted_need", "extracted_timeline",
    "lead_id", "booking_lead_id", "last_error", "updated_at",
)


def _fmt(row: Mapping[str, Any]) -> str:
    return "\n".join(f"  {k:<28} {row.get(k)!r}" for k in _SHOW_FIELDS)


def _print_change(before: Optional[Mapping[str, Any]], after: Mapping[str, Any]) -> None:
    print("BEFORE"); print(_fmt(before or {}))
    print("AFTER"); print(_fmt(after))


def _resolve(db, conversation_id: str, tenant_id: str) -> dict:
    row = get_by_conversation_id(db, conversation_id, tenant_id=tenant_id)
    if row is None:
        raise SystemExit(f"ERROR: no conversation {conversation_id!r} for tenant {tenant_id}")
    return row


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect and steer Instagram DM conversations.")
    p.add_argument("--tenant-id", default=OASIS_TENANT_ID)
    sub = p.add_subparsers(dest="cmd", required=True)

    lst = sub.add_parser("list", help="read-only")
    lst.add_argument("--stage")
    lst.add_argument("--handoffs", action="store_true")
    lst.add_argument("--limit", type=int, default=50)
    lst.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="read-only")
    show.add_argument("--conversation-id", required=True)
    show.add_argument("--json", action="store_true")

    res = sub.add_parser("resume"); res.add_argument("--conversation-id", required=True)
    res.add_argument("--stage", default="engaged")
    pau = sub.add_parser("pause"); pau.add_argument("--conversation-id", required=True)
    hnd = sub.add_parser("handoff"); hnd.add_argument("--conversation-id", required=True)
    hnd.add_argument("--reason", required=True)
    dsq = sub.add_parser("disqualify"); dsq.add_argument("--conversation-id", required=True)
    dsq.add_argument("--reason", required=True)
    rsb = sub.add_parser("reset-booking"); rsb.add_argument("--conversation-id", required=True)
    rse = sub.add_parser("reset-email"); rse.add_argument("--conversation-id", required=True)
    mig = sub.add_parser("migrate-json"); mig.add_argument("--apply", action="store_true")

    args = p.parse_args()
    db = get_db_handle()
    tenant = args.tenant_id

    if args.cmd == "list":
        rows = (list_handoffs(db, tenant_id=tenant, limit=args.limit) if args.handoffs
                else list_by_stage(db, args.stage, tenant_id=tenant, limit=args.limit)
                if args.stage
                else list_all(db, tenant_id=tenant, limit=args.limit))
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            print(f"{len(rows)} conversation(s)")
            for r in rows:
                print(f"  {r['provider_conversation_id']:<20} @{r.get('participant_handle')!s:<20} "
                      f"{r['stage']:<13} paused={r['automation_paused']} "
                      f"handoff={r['handoff_pending']} booking={r['booking_status']}")
        return 0

    if args.cmd == "show":
        row = _resolve(db, args.conversation_id, tenant)
        print(json.dumps(row, indent=2, default=str) if args.json else _fmt(row))
        return 0

    if args.cmd == "migrate-json":
        print(json.dumps(migrate_legacy_json_state(db, tenant_id=tenant,
                                                   apply=args.apply), indent=2))
        return 0

    before = _resolve(db, args.conversation_id, tenant)
    row_id = str(before["id"])
    if args.cmd == "resume":
        after = resume(db, row_id, stage=args.stage, tenant_id=tenant)
    elif args.cmd == "pause":
        after = pause(db, row_id, tenant_id=tenant)
    elif args.cmd == "handoff":
        after = request_handoff(db, row_id, reason=args.reason, tenant_id=tenant)
    elif args.cmd == "disqualify":
        after = set_stage(db, row_id, stage="disqualified", reason=args.reason,
                          tenant_id=tenant, force=True)
    elif args.cmd == "reset-booking":
        after = reset_booking(db, row_id, tenant_id=tenant)
    elif args.cmd == "reset-email":
        after = reset_email(db, row_id, tenant_id=tenant)
    else:  # unreachable: argparse requires a known subcommand
        raise SystemExit(f"unknown command {args.cmd!r}")
    _print_change(before, after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
