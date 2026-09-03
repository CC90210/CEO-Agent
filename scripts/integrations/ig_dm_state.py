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

1. `TursoDB.execute()` DOES NOT COMMIT. Proved 2026-08-20 against a local libSQL
   file: after db.execute(), the writing process saw the row and a SEPARATE
   process saw ZERO. No error, no warning, and the returned cursor is truthy
   either way.
   `TursoDB.insert()` had the same hole and was FIXED on 2026-08-21 (db_turso.py
   :563 now commits, matching claim() at :608, pinned by
   test_insert_is_durable_from_a_second_connection). An earlier version of this
   docstring still said insert() does not commit — corrected here rather than
   left to mislead. _write() below is unaffected either way: it commits
   explicitly, which is the property this module depends on.
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
    MAX_MEMORY_FIELD_CHARS,
    MAX_MEMORY_SUMMARY_CHARS,
    STAGES,
    is_legal_transition,
    sanitize_untrusted,
)

CAPABILITY_META = {
    "category": "growth.inbound",
    "lifecycle": "active",
    "risk": "local_write",
    "triggers": ["instagram dm state", "dm conversation state", "ig handoffs"],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": False},
}

TABLE = "instagram_dm_conversations"
PROVIDER = "instagram"
OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

# The legacy CRM table book_discovery_call.load_lead() reads. This module writes
# exactly one shape of row into it (see ensure_booking_lead) and never touches a
# row it did not create — BOOKING_LEAD_SOURCE is the predicate that guarantees it.
LEADS_TABLE = "leads"
BOOKING_LEAD_SOURCE = "instagram_dm"

TERMINAL_STAGES = frozenset({"booked", "handed_off", "disqualified"})
BOOKING_STATUSES = ("none", "claimed", "booked", "failed")

# Budgets for a SETTER, not an autoresponder (raised 2026-08-21).
#
# These were 3 / 40 / 120s, sized for "answer a DM once and stop". That is the
# wrong shape for the job: this agent opens, qualifies, nurtures and books, which
# is a 10-20 turn conversation. Two live prospects sat at 2 of 3 replies within
# hours of going live — the next message each of them sent would have been met
# with silence, mid-negotiation, with no handoff and no alert, because a budget
# refusal is a skip and not a failure.
#
# 30 per conversation per day still bounds a runaway loop (a self-talk bug caps
# out at 30 messages, not infinity) while being far above any real sales
# conversation. The global cap bounds fleet-wide model spend on the shared
# subscription; at ~27s per call, 200 replies is ~90 minutes of CLI time spread
# across a day.
#
# The gap is what stops a burst reading as a bot. 45s is long enough that two
# messages never land on top of each other and short enough that a person typing
# a follow-up thought is not left waiting minutes for an answer.
DAILY_REPLY_CAP_PER_CONVERSATION = 30
DAILY_REPLY_CAP_GLOBAL = 200
MIN_REPLY_GAP_SECONDS = 45
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

    assignments["last_decision_json"] = _decision_json(decision)

    del message_sent  # the DM text lives in the thread; storing it twice ages badly
    return _touch(db, row_id, tenant_id, assignments)


def _decision_json(decision: Any) -> str:
    """One serialisation for every write of last_decision_json."""
    try:
        return json.dumps(decision.as_dict())
    except (AttributeError, TypeError, ValueError) as exc:
        return json.dumps({"unserializable_decision": str(exc)[:200]})


def record_hold(db, row_id: str, *, decision: Any,
                tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Keep the model's reasoning when it decided to send NOTHING.

    WHY (2026-09-03): last_decision_json was written only by record_outbound,
    i.e. only when a DM actually went out. A hold wrote nothing, so when the
    model held on the operator's own test thread and proposed `disqualified`,
    the row kept `last_error = "model hold"` and a decision JSON from
    2026-08-21 — the last reply it had sent. Two weeks stale, and it read as
    if the model had drafted a reply and something downstream had eaten it.
    The one decision that ends a relationship was the one decision with no
    record of why.
    """
    return _touch(db, row_id, tenant_id, {"last_decision_json": _decision_json(decision)})


def reopen_from_inbound(db, row_id: str, *, reason: str,
                        tenant_id: str = OASIS_TENANT_ID) -> Optional[dict]:
    """A prospect the MODEL wrote off, who then wrote back, is engaged again.

    Narrow on purpose. It reopens only a row that is (a) at stage disqualified
    AND (b) paused by a model verdict — last_error begins "model", which is what
    the poller's hold branch records. A disqualification the operator set by
    hand (`ig_dm_state.py disqualify --reason ...`) carries the operator's own
    reason there and is left alone: the operator's "no" outranks a new "hey".
    Returns None when the row does not qualify, so the caller can tell "left
    paused" from "reopened" without a second read.

    Mirrors resume() in what it clears, and like request_handoff() it writes
    the stage directly rather than through set_stage(): the transition matrix
    says disqualified is final, and it is — for the automation's own verdicts.
    A human writing back is the one event that outranks the matrix.
    """
    current = _require_row(db, row_id, tenant_id)
    if str(current.get("stage") or "") != "disqualified":
        return None
    if not str(current.get("last_error") or "").lower().startswith("model"):
        return None
    return _touch(db, row_id, tenant_id, {
        "stage": "engaged", "stage_entered_at": _iso(),
        "automation_paused": 0, "handoff_pending": 0, "handoff_reason": None,
        "consecutive_model_failures": 0, "consecutive_guardrail_rejects": 0,
        "last_error": str(reason)[:_MAX_ERROR_CHARS],
    })


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


# The four lead-memory columns (migration bravo__012) and the cap each one is
# written under. The caps are enforced HERE as well as at the prompt boundary:
# these fields are rewritten on every successful turn, so a model that appends
# instead of rewriting would otherwise grow a row without limit and quietly
# inflate every future prompt for that conversation.
_MEMORY_LIMITS: dict[str, int] = {
    "budget": MAX_MEMORY_FIELD_CHARS,
    "objections": MAX_MEMORY_FIELD_CHARS,
    "pitched": MAX_MEMORY_FIELD_CHARS,
    "summary": MAX_MEMORY_SUMMARY_CHARS,
}


def _memory_field(memory: Any, name: str) -> Optional[str]:
    """One lead-memory field, sanitised and capped, or None.

    SANITISED ON THE WAY IN, not only on the way out. The render path already
    neutralises the <<< >>> fence shape and collapses newlines, and that is what
    stops a stored note forging a prompt line. Doing it here too means the
    hostile shape never reaches the database at all, so an operator reading
    `show`, a future exporter, or any second consumer of this column inherits the
    guarantee instead of having to remember it.
    """
    value = getattr(memory, name, None)
    if value is None and isinstance(memory, Mapping):
        value = memory.get(name)
    if value is None:
        return None
    flat = " ".join(sanitize_untrusted(str(value),
                                       max_chars=_MEMORY_LIMITS[name]).split())
    return flat or None


def apply_memory(db, row_id: str, *, memory: Any,
                 tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Merge the rolling lead memory into the row. COALESCE semantics IN SQL.

    LAST-non-empty-wins (`coalesce(?, col)`), the mirror image of the email's
    first-write-wins (`coalesce(col, ?)`), and the asymmetry is deliberate. An
    email is a fact that must never change under us; these four are a running
    account of a live negotiation and are MEANT to be rewritten as it moves.

    A blank still never erases. The model is asked about the current turn, so a
    null means "nothing changed", and treating that as a retraction would delete
    the recap of the opening messages — which, once the transcript window has
    scrolled past them, is the only record of how the deal started.
    """
    def _f(name: str) -> Optional[str]:
        return _memory_field(memory, name)

    _write(
        db,
        f"update {TABLE} set "
        "memory_budget = coalesce(?, memory_budget), "
        "memory_objections = coalesce(?, memory_objections), "
        "memory_pitched = coalesce(?, memory_pitched), "
        "memory_summary = coalesce(?, memory_summary), "
        "updated_at = ? "
        "where tenant_id = ? and id = ?",
        (_f("budget"), _f("objections"), _f("pitched"), _f("summary"),
         _iso(), tenant_id, str(row_id)),
    )
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


def flag_for_review(db, row_id: str, *, reason: str,
                    tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Put the row in the human queue WITHOUT rewriting the stage. Idempotent.

    request_handoff() forces stage='handed_off', which is the right answer when
    a human must take the conversation over and the wrong one when the
    conversation is already finished: a model that returns action='reply' with
    stage='disqualified' has ENDED it, and overwriting that with 'handed_off'
    would destroy the only record of why.

    But an ending nobody is told about is the same as no ending at all.
    `list --handoffs` filters on handoff_pending = 1 and nothing outside these
    four modules reads that column, so a terminal stage reached by any path
    other than action='handoff' was invisible: automation_paused=1,
    handoff_pending=0, and CC's only way to find it was to run
    `list --stage disqualified` by hand. This is the narrow write that makes the
    ending visible while leaving the ending itself intact.
    """
    return _touch(db, row_id, tenant_id, {
        "handoff_pending": 1,
        "handoff_reason": str(reason)[:_MAX_ERROR_CHARS],
    })


def note(db, row_id: str, *, note: str, tenant_id: str = OASIS_TENANT_ID) -> dict:
    """Record why the automation declined to act this turn. Touches nothing else.

    A refusal that only ever reached stdout is a refusal nobody can audit: the
    poller runs headless under the scheduler and its stdout is truncated to the
    last 200 characters of one line. last_error is the field an operator reading
    `ig_dm_state.py show` actually sees.
    """
    return _touch(db, row_id, tenant_id, {
        "last_error": str(note)[:_MAX_ERROR_CHARS],
    })


def list_stale_claims(db, *, older_than_minutes: int = 30,
                      tenant_id: str = OASIS_TENANT_ID, limit: int = 50) -> list[dict]:
    """Rows stranded at booking_status='claimed'. The queue nobody could read.

    claim_booking() sets booking_status='claimed' but leaves automation_paused=0,
    handoff_pending=0 and the stage untouched, so a process that dies between the
    claim and finalize (Ctrl-C, a PM2 restart, a cron timeout kill — none of
    which run an `except Exception` handler) leaves a row that is invisible to
    `list --handoffs` AND permanently un-bookable: every later close() dies at the
    precondition check. booking_claimed_at was written and read by nothing. This
    is what reads it.
    """
    cutoff = _iso(_now() - timedelta(minutes=int(older_than_minutes)))
    rows = db.query(
        f"select * from {TABLE} where tenant_id = ? and booking_status = 'claimed' "
        "and coalesce(booking_claimed_at, '') < ? order by booking_claimed_at asc "
        "limit ?",
        (tenant_id, cutoff, int(limit)),
    )
    return [dict(r) for r in rows]


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


def mark_examined(db, row_id: str, *, provider_updated_time: Optional[str],
                  tenant_id: str = OASIS_TENANT_ID) -> Optional[dict]:
    """Remember the thread's `updatedTime` as of a COMPLETED examination.

    This is the watermark the poller's cheap pre-filter reads (see migration
    bravo__011). The old pre-filter compared `updatedTime` against
    `last_outbound_at`, which only exists once we have replied — so every thread
    we had never answered was re-fetched on every tick forever. Measured live on
    2026-08-21: 47 of 50 threads, ~1.2s each, exhausting the run deadline at
    conversation 25 and leaving the rest of the inbox unread.

    CALL THIS ONLY ON A CONCLUSION, never on a deferral. "Answered", "not our
    turn", "unreadable", "already seen" and "handed off" are conclusions: nothing
    more can be learned about that thread until it moves again. "Out of model
    budget" and "deadline reached" are deferrals — stamping there would mark a
    waiting prospect as examined and silently abandon them until their NEXT
    message, which is precisely the mid-conversation death this system is
    supposed to have stopped having.

    A missing/blank stamp is a no-op rather than a NULL write: clearing a good
    watermark would quietly restore the every-tick refetch this exists to end.
    """
    stamp = (provider_updated_time or "").strip()
    if not stamp:
        return None
    return _touch(db, row_id, tenant_id, {"provider_updated_time": stamp})


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
                     event_id: Optional[str] = None,
                     tenant_id: str = OASIS_TENANT_ID) -> dict:
    """The meeting exists. Guarded by the claim token; a zero-effect update raises.

    `event_id` is the Google event id, and it is the meeting's ONLY inverse:
    `google_tool.py calendar delete <event_id>` cancels it and mails the
    cancellation. Creating the event already mailed the invite (sendUpdates:"all"),
    so without this stored a real meeting sits on CC's calendar that no code can
    find. Optional because the legacy static-room path never printed one — a NULL
    is an honest "no id", never an invented one.
    """
    _write(
        db,
        f"update {TABLE} set booking_status = 'booked', booked_start = ?, "
        "booked_end = ?, booked_meet_link = ?, booked_event_id = ?, "
        "booking_email_status = ?, "
        "stage = 'booked', stage_entered_at = ?, automation_paused = 1, updated_at = ? "
        "where tenant_id = ? and id = ? and booking_claim_token = ?",
        (str(start_iso), str(end_iso), str(meet_link),
         str(event_id) if event_id else None, str(email_status),
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

def booking_lead_id_for(row: Mapping[str, Any], *,
                        tenant_id: str = OASIS_TENANT_ID) -> str:
    """The `leads.id` this conversation's bridge row will always have.

    uuid5, not uuid4, and that is the whole point. The bridge is a two-step
    write — INSERT the lead, then stamp booking_lead_id back onto the
    conversation — and the steps are not atomic. With a random id, a crash
    between them leaves a committed `leads` row nothing points at and the next
    attempt creates a SECOND one; against a table CC reads by hand that is
    quiet, permanent duplication. Derived from (tenant, conversation) the id is
    the same on every attempt forever, so a retry finds its own orphan and
    adopts it instead of adding to the pile.
    """
    conversation_id = str(row.get("provider_conversation_id") or "").strip()
    if not conversation_id:
        raise IgStateError(
            "booking_lead_id_for needs provider_conversation_id — without it the "
            "bridge id is not stable and a retry would create a second lead row"
        )
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"igdm-booking-lead/{tenant_id}/{conversation_id}"))


def _find_booking_lead(db, lead_id: str, tenant_id: str) -> Optional[dict]:
    """The bridge lead by primary key, or None. ONE row, matched in SQL.

    `leads` is small today and `tenant_records` was small once too. The lookup
    is a keyed SELECT with LIMIT 1 rather than a page read plus a Python
    comparison, because the page read is the bug that shipped a duplicate lead
    on every poll against 31k rows (2026-08-20).
    """
    rows = db.query(
        f"select id, email from {LEADS_TABLE} "
        "where tenant_id = ? and id = ? limit 1",
        (tenant_id, str(lead_id)),
    )
    return dict(rows[0]) if rows else None


def _sync_booking_lead_email(db, lead_id: str, *, email: Optional[str],
                             tenant_id: str) -> None:
    """Keep the bridge lead's address equal to the one the closer just verified.

    Two different addresses reach the prospect: book_discovery_call.book() puts
    `leads.email` on the Google invite, while ig_closer mails the confirmation
    to the freshly extracted address. On a reset-and-retry after a prospect
    corrected their email those two diverge, and the invite — the irreversible
    half — goes to the dead inbox.

    Narrow on purpose: it can only ever touch a row this bridge created
    (source = 'instagram_dm'), only when we hold a non-empty address, and only
    when that address actually differs.
    """
    if not email:
        return
    rows = db.query(
        f"select email from {LEADS_TABLE} "
        "where tenant_id = ? and id = ? and source = ? limit 1",
        (tenant_id, str(lead_id), BOOKING_LEAD_SOURCE),
    )
    if not rows:
        return
    if str(rows[0].get("email") or "").strip().lower() == email:
        return
    _write(
        db,
        f"update {LEADS_TABLE} set email = ?, updated_at = ? "
        "where tenant_id = ? and id = ? and source = ?",
        (email, _iso(), tenant_id, str(lead_id), BOOKING_LEAD_SOURCE),
    )
    print(f"[ig_dm_state] bridge lead {lead_id} email re-pointed to the address the "
          f"closer verified", file=sys.stderr)


def ensure_booking_lead(db, row: Mapping[str, Any], *, extracted: Any, apply: bool,
                        tenant_id: str = OASIS_TENANT_ID) -> Optional[str]:
    """The legacy `leads` row a booking needs. THE ONLY place this system writes one.

    book_discovery_call.load_lead() reads db.table("leads") (84 rows) and there
    is no instagram_dm row in it; the DM lead lives in tenant_records (32k
    rows). load_lead is shared substrate — ig_closer drives it and so does the
    ai-audit funnel, and lead_interactions.lead_id holds a `leads` id in every
    existing row — so the bridge lives HERE rather than in that primitive.

    Made visible and operator-gated instead of silent: apply=False creates
    nothing, the id is deterministic so a retry can never duplicate, and `notes`
    carries the lineage of every id involved so a human reading the CRM can see
    exactly which Instagram thread produced this row.
    """
    def _f(name: str) -> Optional[str]:
        return _extracted_field(extracted, name)

    email = (_f("email") or "").strip().lower() or None

    existing = str(row.get("booking_lead_id") or "").strip()
    if existing:
        if apply:
            _sync_booking_lead_email(db, existing, email=email, tenant_id=tenant_id)
        return existing
    if not apply:
        return None

    lead_id = booking_lead_id_for(row, tenant_id=tenant_id)
    found = _find_booking_lead(db, lead_id, tenant_id)

    if found is None:
        handle = row.get("participant_handle") or row.get("participant_id") or "unknown"
        # `name` is NOT NULL in the live DDL, so it needs three fallbacks, not one.
        name = _f("name") or row.get("participant_name") or f"@{handle}"
        now = _iso()
        values = {
            "id": lead_id,
            "name": name,
            "email": email,
            "phone": _f("phone"),
            "company": _f("business"),
            "source": BOOKING_LEAD_SOURCE,
            "status": "qualified",      # `leads` has `status`, NOT `stage`
            "score": 70,
            "assigned_to": "bravo",
            "notes": ("Bridged from Instagram DM by ig_dm_state.ensure_booking_lead. "
                      f"handle=@{handle} "
                      f"conversation={row.get('provider_conversation_id')} "
                      f"ig_dm_conversation_row={row.get('id')} "
                      f"tenant_records_lead={row.get('lead_id')}"),
            "created_at": now,
            "updated_at": now,
        }
        try:
            db.insert(LEADS_TABLE, values, tenant_id=tenant_id)
            # insert() does NOT commit on this driver — proved cross-process.
            # Without this the booking would reference a lead row that no other
            # process can see.
            db.commit()
        except Exception as exc:  # noqa: BLE001 — re-raised unless the row is THERE
            # Two processes can reach this line with the same deterministic id.
            # The loser's INSERT trips the primary key. That is a won race, not a
            # failure, but only if the row genuinely exists now: anything else
            # propagates untouched.
            if _find_booking_lead(db, lead_id, tenant_id) is None:
                raise
            print(f"[ig_dm_state] bridge lead insert for {lead_id} lost a race "
                  f"({type(exc).__name__}: {exc}); adopting the row that won",
                  file=sys.stderr)
    else:
        # An orphan from an attempt that died between the INSERT and the stamp
        # below, or a concurrent winner. Adopt it; do not add a second row.
        print(f"[ig_dm_state] adopting existing bridge lead {lead_id} for "
              f"conversation {row.get('provider_conversation_id')}", file=sys.stderr)
        _sync_booking_lead_email(db, lead_id, email=email, tenant_id=tenant_id)

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
    "memory_budget", "memory_objections", "memory_pitched", "memory_summary",
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
    lst.add_argument("--stale-claims", action="store_true",
                     help="rows stranded at booking_status='claimed' by a process "
                          "that died before finalize — un-bookable until "
                          "reset-booking, and invisible to --handoffs")
    lst.add_argument("--claim-age-minutes", type=int, default=30)
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
        rows = (list_stale_claims(db, older_than_minutes=args.claim_age_minutes,
                                  tenant_id=tenant, limit=args.limit)
                if args.stale_claims
                else list_handoffs(db, tenant_id=tenant, limit=args.limit)
                if args.handoffs
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
