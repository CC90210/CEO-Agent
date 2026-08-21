"""ig_closer.py — the Instagram DM close loop: slot -> Google Meet -> email -> Telegram.

Builder B of the IG DM Closer contract (docs/IG_DM_CLOSER_CONTRACT.md §6).

The brain decides *that* a prospect is ready. This module is the only thing that
turns that decision into a meeting on CC's calendar, an invite in a stranger's
inbox, and a ping on CC's phone. Every one of those is irreversible, so the whole
module is dry by default and a real booking needs an explicit `apply=True`.

WHAT IT DOES NOT DO
    It does not talk to the model, it does not read the transcript, it does not
    write SQL, and it does not reimplement calendar or email logic. Slots and the
    calendar event come from book_discovery_call; the email leaves through
    send_gateway (the single sanctioned outbound chokepoint); state is written
    only through ig_dm_state. This module is the orchestration between them and
    the safety gates around them.

THE IDEMPOTENCY GUARANTEE (read this before changing anything below)
    A conversation books at most once, ever, even with two poller processes racing.
    The guarantee is NOT "we checked booking_status first" — a check-then-act pair
    has a window between the two halves wide enough for a second cron run to slip
    through, which is exactly the double-reply race that paused the live automation.
    The guarantee is a compare-and-swap with read-back, the DB-side equivalent of
    the poller's O_EXCL lock file:

        UPDATE ... SET booking_status='claimed', booking_claim_token=?
         WHERE tenant_id=? AND id=? AND booking_status='none'
        SELECT booking_claim_token ...            -- read back, never rowcount
        -> we own the booking iff the token we read is the token we wrote

    Only the winner of that swap reaches the calendar. Every later write
    (finalize_booking / fail_booking) carries the same token, so a process that
    lost the race cannot overwrite the winner's result — it raises
    BookingClaimLost instead. And `failed` never decays back to `none` on its own:
    a half-completed booking stays parked until an operator runs
    `ig_dm_state.py reset-booking`, because "retry the thing that already put an
    event on the calendar" is how you double-book a prospect.

    Dry mode never takes the claim. A dry run leaves the database byte-identical.

PARTIAL FAILURE IS REPORTED, NEVER HIDDEN
    The calendar event and the confirmation email are two separate outward acts and
    the first one can succeed while the second fails. When that happens the booking
    is still finalized as `booked` (the Google invite already went out; pretending
    otherwise would be a lie to the operator) and the Telegram notification names
    the email status explicitly so a human can repair it. Anything unexpected after
    the claim is caught, the traceback goes to stderr, fail_booking parks the row,
    and the operator is notified. Nothing is ever swallowed.

Usage:
    python scripts/integrations/ig_closer.py close --conversation-id <id> --dry-run
    python scripts/integrations/ig_closer.py close --conversation-id <id> --json
    python scripts/integrations/ig_closer.py close --conversation-id <id> --apply
    python scripts/integrations/ig_closer.py close --conversation-id <id> \
        --start "2026-08-21T14:00" --apply
"""

from __future__ import annotations

CAPABILITY_META = {
    "category": "sales.booking",
    "lifecycle": "active",
    # A module is classified by its most dangerous path. `close(apply=True)`
    # creates a calendar event, mails a Google invite to a stranger, and sends a
    # confirmation email. Dry mode is read-only, but that is not the ceiling.
    "risk": "external_write",
    "triggers": [
        "close an instagram dm lead", "book the instagram prospect",
        "ig dm close loop", "instagram dm booking",
    ],
    "owner": "bravo",
    "project": "oasis",
    # Deliberately invisible to the chat bridge: booking a stranger onto CC's
    # calendar must come from operator intent (a CLI run with --apply, or the
    # poller running with --book), never from a conversational turn.
    "bridge": {"visible": False},
}

import argparse
import json
import re
import secrets
import sys
import traceback
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

import book_discovery_call  # noqa: E402  — slots, calendar event, pre-call brief
import email_playbook  # noqa: E402      — the copy linter the whole fleet shares
import notify as notify_module  # noqa: E402
import send_gateway  # noqa: E402        — the ONLY sanctioned outbound email path
from notify import notify_result  # noqa: E402

# ── sibling modules owned by the other two builders ──────────────────────────
# Imported softly so that `--help`, the copy template and the read-only calendar
# probes stay runnable while Builders A and C land their files. This is NOT an
# error-swallowing except: the import is attempted whenever the file exists, so a
# syntax error or a broken dependency inside them propagates loudly. Only genuine
# absence is tolerated, and every code path that needs them calls _require_*()
# first, which fails with a diagnostic naming the missing file.
_STATE_MODULE_PATH = Path(__file__).with_name("ig_dm_state.py")
_BRAIN_MODULE_PATH = Path(__file__).with_name("ig_conversation_brain.py")

if _STATE_MODULE_PATH.exists():
    import ig_dm_state  # type: ignore  # noqa: E402
else:  # pragma: no cover - transitional, until Builder C lands the DAO
    ig_dm_state = None  # type: ignore

if _BRAIN_MODULE_PATH.exists():
    import ig_conversation_brain  # type: ignore  # noqa: E402
else:  # pragma: no cover - transitional, until Builder A lands the brain
    ig_conversation_brain = None  # type: ignore


# ── constants ────────────────────────────────────────────────────────────────

CLOSER_AGENT_SOURCE: str = "ig_dm_closer"
BOOKING_DAYS_HORIZON: int = 5
# NEVER "instagram": that category is in notify.DEFAULT_BLOCKED and routes to
# Maven's bot, whose token does not live in this repo. It would look wired and be
# dead. "lead" is bravo-owned and delivers.
NOTIFY_CATEGORY: str = "lead"

# Stages from which a close is legal. Anything else means the conversation never
# agreed to a call, and booking it would be an ambush.
CLOSEABLE_STAGES: frozenset[str] = frozenset({"qualified", "booking"})

# Recipient shape gate. Single bare address, ASCII only, no display-name form, no
# separators that could smuggle a second recipient past the mail layer.
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$", re.ASCII)
_EMAIL_FORBIDDEN_CHARS = frozenset(' \t\r\n,;<>"\'()[]\\')

# A prospect-supplied first name is untrusted text on its way into an email body.
# Letters (including accented ones — Montreal), spaces, hyphens, apostrophes and
# periods survive; everything else is dropped.
_NAME_ALLOWED_EXTRA = frozenset(" -'.’")

_EM_DASHES = ("—", "–")

_MAX_SUBJECT_CHARS = 70
_MAX_NOTIFY_DETAIL_CHARS = 180


class CloserContractError(RuntimeError):
    """A dependency this module cannot function without is missing.

    Raised by _require_state()/_require_brain() only. It is a wiring error, not a
    runtime condition, so it is loud rather than folded into a CloseResult.
    """


# ── result type ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CloseResult:
    ok: bool
    applied: bool                      # True only when a real calendar event exists
    conversation_id: str
    row_id: str
    stage_of_failure: Optional[str]
    booking_lead_id: Optional[str]
    slot_start: Optional[str]
    slot_end: Optional[str]
    slot_label: Optional[str]
    meet_link: Optional[str]
    calendar_output: Optional[str]
    email_status: Optional[str]
    email_reason: Optional[str]
    notify_ok: bool
    notify_reason: Optional[str]
    error: Optional[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# The closed set of stage_of_failure values. Kept as a constant so a typo in a
# failure path is catchable by a test rather than by an operator reading a
# Telegram message about a step that does not exist.
STAGES_OF_FAILURE: tuple[str, ...] = (
    "precondition", "denied_domain", "calendar_unverified", "no_slots",
    "meet_link_missing", "lead_bridge", "claim_lost", "calendar_create",
    "email", "unexpected",
)


# ── dependency guards ────────────────────────────────────────────────────────

def _require_state():
    """Return the ig_dm_state module or fail with a diagnostic naming the file."""
    if ig_dm_state is None:
        raise CloserContractError(
            f"ig_closer requires the conversation-state DAO at {_STATE_MODULE_PATH}. "
            "It is not on disk (Builder C owns it). No booking, no state read and no "
            "state write is possible without it."
        )
    return ig_dm_state


def _require_brain():
    """Return the brain module (needed only for its DENIED_EMAIL_DOMAINS constant).

    The deny list is the money-boundary guard: an address on our own perimeter
    would put whoever controls it inside CC's calendar with a Meet link. It is not
    optional and it is not re-typed here — one list, one home.
    """
    if ig_conversation_brain is None:
        raise CloserContractError(
            f"ig_closer requires {_BRAIN_MODULE_PATH} for DENIED_EMAIL_DOMAINS. "
            "It is not on disk (Builder A owns it). Refusing to book without the "
            "domain deny list rather than booking with a weaker guard."
        )
    return ig_conversation_brain


def _default_tenant_id() -> str:
    return _require_state().OASIS_TENANT_ID


def _compat_db(db: Any) -> Any:
    """Adapt a raw TursoDB to the supabase-shaped client book()/send() expect.

    ig_dm_state hands out `lib.db_turso.get_db()`, a TursoDB with .query()/
    .execute() and no .table(). book_discovery_call.book() and send_gateway.send()
    both drive `db.table(...)`. Wrapping is the whole adaptation — the compat layer
    is the same one the rest of the fleet already runs on, and an object that
    already has .table() is passed through untouched rather than double-wrapped.
    """
    if db is None:
        raise CloserContractError("ig_closer.close() needs a database handle; got None")
    if hasattr(db, "table"):
        return db
    from lib.turso_supabase_compat import TursoSupabaseCompat  # noqa: E402

    return TursoSupabaseCompat(db)


# ── small helpers ────────────────────────────────────────────────────────────

def _field(obj: Any, name: str) -> Optional[str]:
    """Read a field from an Extracted dataclass or a plain mapping."""
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        value = obj.get(name)
    else:
        value = getattr(obj, name, None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _valid_recipient(email: Optional[str]) -> tuple[bool, str]:
    """Shape gate on the address we are about to mail. (ok, reason).

    Defence in depth: the brain already refused to accept an address it did not
    see the prospect type. This runs again at the money boundary, because the
    recipient of an irreversible outward act is not a field to take on trust from
    an upstream module, a CLI argument, or a database row someone edited by hand.
    """
    if not email:
        return False, "no email on the conversation"
    if any(ch in _EMAIL_FORBIDDEN_CHARS for ch in email):
        return False, "address contains a separator or display-name syntax"
    if not email.isascii():
        return False, "address contains non-ASCII characters"
    if not _EMAIL_RE.match(email):
        return False, "address does not match a single bare email address"
    if len(email) > 254:
        return False, "address is longer than 254 characters"
    return True, "ok"


def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower().removeprefix("www.")


def _clean_first_name(raw: Optional[str]) -> str:
    """Prospect-supplied name -> a safe salutation token.

    Keeps letters (accents included), spaces, hyphens, apostrophes and periods.
    Everything else is dropped, so nothing typed into a DM can restructure the
    email body. Falls back to "there", which reads fine and never lies.
    """
    if not raw:
        return "there"
    first = str(raw).strip().split()[0] if str(raw).strip() else ""
    kept = [
        ch for ch in first
        if unicodedata.category(ch).startswith("L") or ch in _NAME_ALLOWED_EXTRA
    ]
    cleaned = "".join(kept).strip(" -'.’")[:40]
    return cleaned or "there"


def _notify_safe(text: Optional[str], limit: int = _MAX_NOTIFY_DETAIL_CHARS) -> str:
    """Make a fragment safe to put in a Telegram body.

    notify() decides on MESSAGE CONTENT: a body matching _NOT_BRAVO_DOMAIN_RE is
    dropped entirely and one matching _GROUP_BLOCKED_TERMS_RE is rerouted. An error
    string carrying the word "traceback", or a stranger who typed "phone lookup",
    would otherwise silence the alert about themselves. Newlines collapse, blocked
    terms are masked, and the fragment is truncated.
    """
    if not text:
        return ""
    flat = " ".join(str(text).split())
    for attr in ("_GROUP_BLOCKED_TERMS_RE", "_NOT_BRAVO_DOMAIN_RE"):
        pattern = getattr(notify_module, attr, None)
        if pattern is not None:
            flat = pattern.sub("[term]", flat)
    if len(flat) > limit:
        flat = flat[: limit - 1].rstrip() + "…"
    return flat


def _handle_of(row: Mapping[str, Any]) -> str:
    raw = (row.get("participant_handle") or row.get("participant_name")
           or row.get("participant_id") or "unknown")
    return _notify_safe(raw, limit=64) or "unknown"


def _slot_from_start(start: str) -> dict[str, str]:
    """Build a slot dict from an operator-supplied local ISO start time."""
    start_dt = datetime.fromisoformat(start)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=book_discovery_call.TZ)
    else:
        start_dt = start_dt.astimezone(book_discovery_call.TZ)
    end_dt = start_dt + timedelta(minutes=book_discovery_call.CALL_MINUTES)
    return {
        "start": start_dt.isoformat(timespec="minutes"),
        "end": end_dt.isoformat(timespec="minutes"),
        "label": start_dt.strftime("%a %d %b, %I:%M %p").replace(" 0", " "),
    }


def _fail(
    row: Mapping[str, Any],
    stage_of_failure: str,
    error: str,
    *,
    applied: bool = False,
    booking_lead_id: Optional[str] = None,
    slot: Optional[Mapping[str, str]] = None,
    meet_link: Optional[str] = None,
    calendar_output: Optional[str] = None,
    email_status: Optional[str] = None,
    email_reason: Optional[str] = None,
    notify_ok: bool = False,
    notify_reason: Optional[str] = None,
) -> CloseResult:
    print(f"[ig_closer] FAILED step={stage_of_failure} conversation="
          f"{row.get('provider_conversation_id')} error={error}", file=sys.stderr)
    return CloseResult(
        ok=False,
        applied=applied,
        conversation_id=str(row.get("provider_conversation_id") or ""),
        row_id=str(row.get("id") or ""),
        stage_of_failure=stage_of_failure,
        booking_lead_id=booking_lead_id,
        slot_start=(slot or {}).get("start"),
        slot_end=(slot or {}).get("end"),
        slot_label=(slot or {}).get("label"),
        meet_link=meet_link,
        calendar_output=calendar_output,
        email_status=email_status,
        email_reason=email_reason,
        notify_ok=notify_ok,
        notify_reason=notify_reason,
        error=error,
    )


# ── public: environment probes ───────────────────────────────────────────────

def resolve_meet_link() -> Optional[str]:
    """The static Google Meet room google_tool pastes onto every event.

    Loaded through lib.secret_loader — never by reading a .env file, which
    secret_guard blocks by design. It is one shared room, not a per-call link.

    Why this is a hard precondition rather than a warning: when GOOGLE_MEET_LINK
    is absent, google_tool silently omits conferenceData and creates an event with
    no Meet at all. The prospect would get a calendar invite to a call with no
    room, and the confirmation email would have nothing to point at.
    """
    from lib.secret_loader import load_env  # noqa: E402

    value = (load_env().get("GOOGLE_MEET_LINK") or "").strip()
    return value or None


def verify_calendar_readable(*, days: int = BOOKING_DAYS_HORIZON) -> bool:
    """True when CC's calendar was actually read. Fails CLOSED on doubt.

    book_discovery_call.busy_windows() returns [] for two opposite reasons: the
    calendar is genuinely empty, and the calendar read FAILED (it prints to stderr
    and returns [] at book_discovery_call.py:117-118). free_slots() cannot tell
    those apart, so on a failed read it fails OPEN and confidently offers a slot on
    top of an existing meeting.

    CC's calendar is never empty across five weekdays. An empty busy list is
    therefore evidence of an unreadable calendar, not of a free week, and the
    caller must refuse to book rather than double-book him.
    """
    return bool(book_discovery_call.busy_windows(days))


def choose_slot(*, days: int = BOOKING_DAYS_HORIZON,
                limit: int = 12) -> Optional[dict[str, str]]:
    """First bookable 30-minute window, or None.

    Does NOT verify the calendar — close() calls verify_calendar_readable() first,
    so that a failed read can never be laundered into "here is a free slot".
    """
    slots = book_discovery_call.free_slots(days, limit)
    return slots[0] if slots else None


# ── public: the confirmation email ───────────────────────────────────────────

def _copy_violations(subject: str, body_text: str) -> list[str]:
    """Every copy rule this email has to satisfy, checked deterministically."""
    out: list[str] = []
    out.extend(f"lint:{hit}" for hit in email_playbook.lint_draft(body_text))
    for dash in _EM_DASHES:
        if dash in body_text or dash in subject:
            out.append("em_dash")
            break
    for ch in subject + body_text:
        code = ord(ch)
        if (0x1F000 <= code <= 0x1FAFF) or (0x2600 <= code <= 0x27BF) or code == 0xFE0F:
            out.append("emoji")
            break
    if len(subject) > _MAX_SUBJECT_CHARS:
        out.append(f"subject_too_long:{len(subject)}")
    if subject.lower().startswith("re:"):
        out.append("subject_reply_prefix")
    if "!" in subject:
        out.append("subject_exclamation")
    return out


def build_confirmation_email(
    *,
    first_name: str,
    slot_label: str,
    slot_start_iso: str,
    meet_link: str,
) -> tuple[str, str]:
    """(subject, body_text) for the booking confirmation. Plain text only.

    body_html deliberately stays None: send_gateway validates body_html and returns
    status "error" when handed a non-HTML string, so a "helpful" HTML version is a
    silent send failure waiting to happen.

    The template self-checks against the same linter that guards every other piece
    of outbound copy and raises ValueError when it trips. A template that violates
    the copy rules is a build-time bug — catching it here beats discovering it in a
    prospect's inbox.
    """
    if not meet_link:
        raise ValueError("build_confirmation_email needs a meet link")

    name = _clean_first_name(first_name)
    label = " ".join(str(slot_label or "").split()) or slot_start_iso
    minutes = book_discovery_call.CALL_MINUTES

    subject = f"OASIS call confirmed: {label}"
    if len(subject) > _MAX_SUBJECT_CHARS:
        subject = "OASIS call confirmed"

    body_text = (
        f"Hi {name},\n"
        f"\n"
        f"You are booked for {label}, Toronto time. It runs {minutes} minutes.\n"
        f"\n"
        f"Here is the room: {meet_link}\n"
        f"\n"
        f"Before we talk, pull up the page or the workflow that is costing you the "
        f"most time so we can go straight at it.\n"
        f"\n"
        f"If that time stops working, reply to this email and I will move it.\n"
        f"\n"
        f"Conaugh McKenna\n"
        f"OASIS AI Solutions\n"
    )

    if body_text.count(meet_link) != 1:
        raise ValueError("the meet link must appear exactly once in the body")

    violations = _copy_violations(subject, body_text)
    if violations:
        raise ValueError(
            "confirmation email template violates the copy rules: "
            + "; ".join(violations)
        )
    return subject, body_text


# ── public: the close loop ───────────────────────────────────────────────────

def close(
    db: Any,
    row: Mapping[str, Any],
    *,
    extracted: Any,
    apply: bool = False,
    slot: Optional[Mapping[str, str]] = None,
    tenant_id: Optional[str] = None,
    notifier: Callable[..., tuple[bool, str]] = notify_result,
) -> CloseResult:
    """Slot -> Google Meet -> confirmation email -> Telegram. DRY BY DEFAULT.

    `row` is an ig_dm_state conversation row dict; `extracted` is a brain Extracted
    (a plain mapping with the same keys also works). `notifier` is injectable for
    tests and must have notify_result's (ok, reason) signature.

    NEVER RAISES. Every failure path returns CloseResult(ok=False,
    stage_of_failure=<closed set>) with the traceback already on stderr.

    apply=False performs steps 1-6 and returns a fully populated CloseResult with
    applied=False: no claim, no calendar event, no email, no notification, and no
    database write of any kind.

    Idempotency: see the module docstring. Step 7 is the boundary — after it,
    exactly one process owns this booking, and every subsequent write is guarded by
    the same claim token.
    """
    conversation_id = str(row.get("provider_conversation_id") or "")
    row_id = str(row.get("id") or "")
    handle = _handle_of(row)

    tenant = tenant_id or ""
    claim_token: Optional[str] = None
    applied = False
    booking_lead_id: Optional[str] = None
    meet_link: Optional[str] = None
    chosen: Optional[Mapping[str, str]] = None
    calendar_output: Optional[str] = None
    email_status: Optional[str] = None
    email_reason: Optional[str] = None

    try:
        # Resolved inside the try so that a missing sibling module surfaces as
        # CloseResult(ok=False, stage_of_failure="unexpected") rather than an
        # exception — this function's contract is that it never raises.
        state = _require_state()
        tenant = tenant_id or state.OASIS_TENANT_ID

        # ── 1. preconditions ─────────────────────────────────────────────────
        if not row_id or not conversation_id:
            return _fail(row, "precondition",
                         "row is missing id or provider_conversation_id")
        if str(row.get("booking_status") or "none") != "none":
            return _fail(row, "precondition",
                         f"booking_status is {row.get('booking_status')!r}, not 'none'"
                         "; an operator reset is required before another attempt")
        if str(row.get("stage") or "") not in CLOSEABLE_STAGES:
            return _fail(row, "precondition",
                         f"stage {row.get('stage')!r} is not one of "
                         f"{sorted(CLOSEABLE_STAGES)}")
        if int(row.get("automation_paused") or 0) != 0:
            return _fail(row, "precondition", "automation_paused is set")

        email = _field(extracted, "email")
        ok_email, why = _valid_recipient(email)
        if not ok_email:
            return _fail(row, "precondition", f"recipient rejected: {why}")
        assert email is not None  # narrowed by _valid_recipient
        email = email.lower()

        # ── 2. domain deny (money-boundary defence in depth) ─────────────────
        denied = _require_brain().DENIED_EMAIL_DOMAINS
        if _email_domain(email) in denied:
            return _fail(row, "denied_domain",
                         f"domain {_email_domain(email)} is on the deny list")

        # ── 3. calendar must be provably readable ────────────────────────────
        if not verify_calendar_readable():
            return _fail(row, "calendar_unverified",
                         "busy_windows() returned nothing, which means the calendar "
                         "read failed or the week is implausibly empty — refusing to "
                         "book on an unverified calendar")

        # ── 4. slot ──────────────────────────────────────────────────────────
        chosen = slot or choose_slot()
        if not chosen or not chosen.get("start"):
            return _fail(row, "no_slots", "no bookable slot in the horizon")

        # ── 5. meet link ─────────────────────────────────────────────────────
        meet_link = resolve_meet_link()
        if not meet_link:
            return _fail(row, "meet_link_missing",
                         "GOOGLE_MEET_LINK is absent from the agents env, so the "
                         "invite would carry no meeting room", slot=chosen)

        # ── 6. leads bridge ──────────────────────────────────────────────────
        # book_discovery_call.load_lead() reads the legacy `leads` table; the DM
        # lead lives in tenant_records. The bridge row is created only in apply
        # mode, and only by the DAO.
        booking_lead_id = state.ensure_booking_lead(
            db, row, extracted=extracted, apply=apply, tenant_id=tenant
        )
        if apply and not booking_lead_id:
            return _fail(row, "lead_bridge",
                         "ensure_booking_lead returned no id in apply mode",
                         slot=chosen, meet_link=meet_link)

        # Render the email BEFORE the claim: a template failure must never leave a
        # claimed row or a booked calendar event behind it.
        try:
            subject, body_text = build_confirmation_email(
                first_name=_field(extracted, "name") or row.get("participant_name") or "",
                slot_label=str(chosen.get("label") or ""),
                slot_start_iso=str(chosen.get("start") or ""),
                meet_link=meet_link,
            )
        except ValueError as exc:
            return _fail(row, "email", f"confirmation template rejected: {exc}",
                         booking_lead_id=booking_lead_id, slot=chosen,
                         meet_link=meet_link)

        if not apply:
            return CloseResult(
                ok=True, applied=False, conversation_id=conversation_id,
                row_id=row_id, stage_of_failure=None,
                booking_lead_id=booking_lead_id,
                slot_start=str(chosen.get("start") or ""),
                slot_end=str(chosen.get("end") or ""),
                slot_label=str(chosen.get("label") or ""),
                meet_link=meet_link, calendar_output=None,
                email_status="dry_run", email_reason=f"dry_run: {subject}",
                notify_ok=False, notify_reason="dry_run: no notification sent",
                error=None,
            )

        compat = _compat_db(db)

        # ── 7. claim — THE IDEMPOTENCY BOUNDARY ──────────────────────────────
        claim_token = secrets.token_hex(8)
        if not state.claim_booking(db, row_id, claim_token=claim_token,
                                   tenant_id=tenant):
            claim_token = None
            return _fail(row, "claim_lost",
                         "another process owns this booking, or it already booked, "
                         "or a prior attempt failed and needs reset-booking",
                         booking_lead_id=booking_lead_id, slot=chosen,
                         meet_link=meet_link)

        # ── 8. calendar event — FIRST IRREVERSIBLE OUTWARD EFFECT ────────────
        # book(..., apply=True) mails the attendee a real Google invite
        # (sendUpdates:"all"). Note the opposite defaults of the two primitives
        # below: book() is dry until apply=True, send_gateway.send() is live until
        # dry_run=True. Both are normalized onto this function's single `apply`.
        booking = book_discovery_call.book(
            compat, booking_lead_id, str(chosen["start"]), apply=True
        )
        calendar_output = str(booking.get("calendar_output") or "")[:300] or None
        if not booking.get("ok") or not booking.get("applied"):
            err = str(booking.get("error") or "calendar create failed")
            state.fail_booking(db, row_id, claim_token=claim_token,
                               error=err, tenant_id=tenant)
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, "calendar_create", err, conversation_id)
            return _fail(row, "calendar_create", err,
                         booking_lead_id=booking_lead_id, slot=chosen,
                         meet_link=meet_link, calendar_output=calendar_output,
                         notify_ok=n_ok, notify_reason=n_reason)
        applied = True
        start_iso = str(booking.get("start") or chosen.get("start") or "")
        end_iso = str(booking.get("end") or chosen.get("end") or "")

        # ── 9. confirmation email — non-fatal ────────────────────────────────
        # The invite already went out. A failed confirmation email downgrades the
        # quality of the booking; it does not un-book it. The status travels to the
        # operator verbatim so a human can repair it.
        send_result = send_gateway.send(
            channel="email",
            agent_source=CLOSER_AGENT_SOURCE,
            to_email=email,
            lead_id=booking_lead_id,
            subject=subject,
            body_text=body_text,
            brand="oasis",
            # A booking confirmation is not a solicitation. The draft critic fires
            # only on intent="commercial", where an unrelated critic outage would
            # fail-closed and block a legitimate confirmation.
            intent="transactional",
            tenant_id=tenant,
            metadata={
                "source": "instagram_dm",
                "conversation_id": conversation_id,
                "slot_start": str(chosen.get("start") or ""),
            },
            dry_run=not apply,
            db=compat,
        )
        email_status = str(send_result.get("status") or "unknown")
        email_reason = str(send_result.get("reason") or "")[:300] or None
        if email_status != "sent":
            print(f"[ig_closer] BOOKED BUT EMAIL NOT SENT conversation="
                  f"{conversation_id} status={email_status} reason={email_reason}",
                  file=sys.stderr)

        # ── 10. finalize + notify ────────────────────────────────────────────
        try:
            state.finalize_booking(
                db, row_id, claim_token=claim_token, start_iso=start_iso,
                end_iso=end_iso, meet_link=meet_link, email_status=email_status,
                tenant_id=tenant,
            )
        except state.BookingClaimLost as exc:
            # The meeting EXISTS. Another process took the row out from under us.
            # This is the one partial-failure the operator absolutely must hear
            # about, so it is loud, notified, and reported with applied=True.
            traceback.print_exc()
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, "claim_lost",
                f"calendar event created but state finalize lost the claim: {exc}",
                conversation_id)
            return _fail(row, "claim_lost",
                         f"calendar event created, finalize lost the claim: {exc}",
                         applied=True, booking_lead_id=booking_lead_id, slot=chosen,
                         meet_link=meet_link, calendar_output=calendar_output,
                         email_status=email_status, email_reason=email_reason,
                         notify_ok=n_ok, notify_reason=n_reason)

        notify_ok, notify_reason = notifier(
            f"Booked: @{handle}, {_notify_safe(chosen.get('label'), limit=64)}. "
            f"Meet link emailed to {email} ({email_status}). "
            f"Conversation {conversation_id}.",
            category=NOTIFY_CATEGORY,
            dedup_key=f"igdm:{conversation_id}:booked",
        )
        if not notify_ok:
            print(f"[ig_closer] notification not delivered ({notify_reason}) for "
                  f"conversation={conversation_id}", file=sys.stderr)

        return CloseResult(
            ok=True, applied=True, conversation_id=conversation_id, row_id=row_id,
            stage_of_failure=None, booking_lead_id=booking_lead_id,
            slot_start=start_iso, slot_end=end_iso,
            slot_label=str(chosen.get("label") or ""), meet_link=meet_link,
            calendar_output=calendar_output, email_status=email_status,
            email_reason=email_reason, notify_ok=notify_ok,
            notify_reason=notify_reason, error=None,
        )

    except Exception as exc:  # noqa: BLE001 — the boundary; nothing is swallowed
        traceback.print_exc()
        detail = f"{type(exc).__name__}: {exc}"
        # An unexpected failure AFTER the claim must not leave the row claimed
        # forever, and one after the calendar write must reach a human.
        if claim_token and not applied:
            try:
                _require_state().fail_booking(db, row_id, claim_token=claim_token,
                                              error=detail, tenant_id=tenant)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        n_ok, n_reason = (False, "not attempted")
        if claim_token:
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, "unexpected", detail, conversation_id)
        return _fail(row, "unexpected", detail, applied=applied,
                     booking_lead_id=booking_lead_id, slot=chosen,
                     meet_link=meet_link, calendar_output=calendar_output,
                     email_status=email_status, email_reason=email_reason,
                     notify_ok=n_ok, notify_reason=n_reason)


def _notify_booking_failed(
    notifier: Callable[..., tuple[bool, str]],
    handle: str,
    stage_of_failure: str,
    error: str,
    conversation_id: str,
) -> tuple[bool, str]:
    """Operator ping for a failed or partially completed booking.

    Agent-authored text only — no DM content, no raw traceback. Both are content
    that notify() itself filters on, so quoting them is how an alert about a
    prospect gets silenced by that same prospect.
    """
    try:
        ok, reason = notifier(
            f"Booking failed: @{handle} at step {stage_of_failure}. "
            f"{_notify_safe(error)}. Conversation {conversation_id}.",
            category=NOTIFY_CATEGORY,
            dedup_key=f"igdm:{conversation_id}:booking_failed",
        )
    except Exception:  # noqa: BLE001 — a dead notifier must not mask the booking result
        traceback.print_exc()
        return False, "notifier raised"
    if not ok:
        print(f"[ig_closer] booking-failed alert not delivered ({reason}) for "
              f"conversation={conversation_id}", file=sys.stderr)
    return ok, reason


# ── CLI ──────────────────────────────────────────────────────────────────────

def _extracted_from_row(row: Mapping[str, Any]) -> Any:
    """Rebuild a brain Extracted from the conversation row's extracted_* columns."""
    brain = _require_brain()
    return brain.Extracted(
        name=row.get("extracted_name"),
        email=row.get("extracted_email"),
        phone=row.get("extracted_phone"),
        business=row.get("extracted_business"),
        need=row.get("extracted_need"),
        timeline=row.get("extracted_timeline"),
    )


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ig_closer.py",
        description="Instagram DM close loop: slot -> Google Meet -> email -> Telegram. "
                    "Dry by default; --apply is the only thing that books.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("close", help="close one conversation (dry unless --apply)")
    c.add_argument("--conversation-id", required=True,
                   help="Zernio provider_conversation_id")
    gate = c.add_mutually_exclusive_group()
    gate.add_argument("--apply", action="store_true",
                      help="ACTUALLY book: creates a calendar event, mails the "
                           "prospect a Google invite and a confirmation, pings CC")
    gate.add_argument("--dry-run", action="store_true",
                      help="explicit no-op form of the default (nothing is sent)")
    c.add_argument("--start", help='local ISO override, e.g. "2026-08-21T14:00"')
    c.add_argument("--json", action="store_true")

    s = sub.add_parser("slots", help="read-only: the slots close() would choose from")
    s.add_argument("--days", type=int, default=BOOKING_DAYS_HORIZON)
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--json", action="store_true")
    return ap


def main() -> int:
    argv = sys.argv[1:]
    # Allow the flat form `ig_closer.py --conversation-id X --dry-run` as well as
    # the subcommand form. Nothing else changes.
    if argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv = ["close", *argv]

    args = _build_parser().parse_args(argv)

    if args.cmd == "slots":
        verified = verify_calendar_readable(days=args.days)
        slots = book_discovery_call.free_slots(args.days, args.limit)
        if args.json:
            print(json.dumps({"calendar_verified": verified, "slots": slots}, indent=2))
        else:
            print(f"calendar readable: {verified}")
            if not verified:
                print("  refusing to treat these slots as bookable — the calendar "
                      "read failed or returned nothing")
            for x in slots:
                print(f"  {x['label']:<28} {x['start']}")
        return 0 if verified else 1

    try:
        state = _require_state()
    except CloserContractError as exc:
        # A wiring gap, not a runtime condition: name the missing file and stop.
        # Exit 2 so a cron distinguishes "not installed" from "did not book".
        print(f"[ig_closer] {exc}", file=sys.stderr)
        return 2

    db = state.get_db_handle()
    row = state.get_by_conversation_id(db, args.conversation_id)
    if not row:
        print(f"conversation {args.conversation_id} not found in "
              f"{state.TABLE}", file=sys.stderr)
        return 1

    result = close(db, row, extracted=_extracted_from_row(row), apply=bool(args.apply),
                   slot=_slot_from_start(args.start) if args.start else None)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        head = ("BOOKED" if result.applied else "DRY RUN" if result.ok else "FAILED")
        print(f"{head}: @{_handle_of(row)} conversation={result.conversation_id}")
        print(f"  slot        : {result.slot_label or '-'} ({result.slot_start or '-'})")
        print(f"  meet link   : {'present' if result.meet_link else 'MISSING'}")
        print(f"  lead bridge : {result.booking_lead_id or '- (dry mode creates none)'}")
        print(f"  email       : {result.email_status or '-'}"
              f"{' / ' + result.email_reason if result.email_reason else ''}")
        print(f"  telegram    : {result.notify_reason or '-'}")
        if not result.ok:
            print(f"  failed at   : {result.stage_of_failure}")
            print(f"  error       : {result.error}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
