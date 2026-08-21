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
    otherwise would be a lie to the operator) and it gets its OWN alert — "BOOKED
    BUT NOT CONFIRMED", on its own dedup key — because a meeting whose room link
    never reached the prospect is a distinct state that a human has to finish by
    hand, not a footnote on a success.

    Every failure after the claim is caught, traced to stderr, PARKED with
    fail_booking and notified with the name of the step that broke. Two invariants
    make that recoverable rather than decorative:

      * the park is keyed on `finalized`, not on `applied`. A row whose meeting
        exists but whose state write never landed MUST be parked — 'claimed' sets
        no handoff, no pause and no stage, so the automation would keep talking to
        someone who already has a meeting. A row that DID finalize must never be
        parked: finalize_booking leaves the claim token in place, so fail_booking
        would cheerfully rewrite a real booking into 'failed' + handed_off.
      * when the calendar event already exists, the persisted booking_error is
        prefixed CALENDAR EVENT EXISTS. reset_booking() is the only way back to
        'none' and its contract is "check the calendar BEFORE running this";
        booking_error is the only channel that warning has.

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
# Cap for a whole assembled alert body (see _notify_call). Generous enough that
# the longest agent-authored alert — "BOOKED BUT NOT CONFIRMED" — survives intact,
# tight enough that nothing pasted into it can grow into a wall of text.
_MAX_NOTIFY_BODY_CHARS = 600


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
    "email", "finalize", "notify", "unexpected",
)

# Prefixed onto the error a failed booking is PARKED with, whenever the calendar
# event already exists. reset_booking() is documented "check the calendar BEFORE
# running this" (ig_dm_state.py) and booking_error is the only field that can
# carry that warning to the human who reads it. "unexpected" told them nothing.
CALENDAR_EXISTS_PREFIX = "CALENDAR EVENT EXISTS, do not retry blind — "

# The ambiguous half of the same problem. book_discovery_call shells out to
# google_tool with timeout=180 and does not catch subprocess.TimeoutExpired, so a
# raise from the calendar step means the event MIGHT exist: Google may have
# inserted it (and mailed the attendee, sendUpdates:"all") before the call died.
# `applied` records what WE know, not what the world did, so the warning has to
# fire on the step rather than on the flag.
CALENDAR_UNKNOWN_PREFIX = ("CALENDAR STATE UNKNOWN, the create call never "
                           "returned — check the calendar before retrying — ")

# Placeholder used ONLY to prove the confirmation template renders, before the
# claim and before any event exists. The real room is minted by Google during
# the calendar create and the body is rendered again with it. This string is
# never sent to anyone; if it ever appears in an outbound email, the re-render
# below was skipped.
TEMPLATE_PROBE_LINK = "https://meet.google.com/pending-per-event-room"


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
    """The LEGACY static Google Meet room. NOT the room a booking uses any more.

    close() no longer reads this. It is one shared URL for every event this repo
    has ever created, so prospect A's invite and prospect B's invite pointed at
    the same room and either could walk into the other's call — or a paying
    client's — from an email they never deleted. Bookings now ask Google to mint
    a room per event (book_discovery_call.book(meet_scope="per_event")) and the
    confirmation email carries the room that was actually created.

    Kept for the `meet_scope="static"` escape hatch and for operator diagnostics.
    Loaded through lib.secret_loader — never by reading a .env file, which
    secret_guard blocks by design.
    """
    from lib.secret_loader import load_env  # noqa: E402

    value = (load_env().get("GOOGLE_MEET_LINK") or "").strip()
    return value or None


def verify_calendar_readable(*, days: int = BOOKING_DAYS_HORIZON) -> bool:
    """True when CC's calendar was actually read. Fails CLOSED on doubt.

    This used to infer the read from `bool(busy_windows(days))`, and that
    inference was unsound in BOTH directions:

      * busy_windows returned [] whenever the horizon held no ALL-DAY events —
        which was the normal state of a working calendar, because the old
        text parser could not see timed events at all
        (book_discovery_call._event_window now handles both). A fully booked
        week therefore read as "unreadable" and booking never worked: the
        prospect had already been told by DM that an invite was coming.
      * one all-day entry read as proof the TIMED calendar had been read, which
        it was not.

    read_calendar() returns the read STATUS, so nothing has to be inferred from
    a row count. A failed read still fails closed — free_slots() would otherwise
    fail OPEN and confidently offer a slot on top of an existing meeting.
    """
    ok, _busy = book_discovery_call.read_calendar(days)
    return bool(ok)


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
    # `applied` says a meeting EXISTS. `finalized` says the row has been written
    # to match it. They are not the same fact and the gap between them is where a
    # row used to get stranded: the old handler skipped fail_booking whenever
    # `applied` was set, so any raise from the email, the finalize or the notify
    # left booking_status='claimed' — a state claim_booking() reaches without
    # setting automation_paused, handoff_pending or stage, so nobody was told and
    # the automation kept talking to a prospect who already had a meeting.
    # Keying the park on `not finalized` is what makes it recoverable; keying it
    # on `claim_token` alone would be WORSE, because finalize_booking leaves the
    # token in place and fail_booking would then flip a genuinely booked row to
    # 'failed' + handed_off.
    finalized = False
    # The last step entered, so the alert can name the step that actually failed
    # instead of shrugging "unexpected" at the operator.
    step = "precondition"
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
        step = "denied_domain"
        denied = _require_brain().DENIED_EMAIL_DOMAINS
        if _email_domain(email) in denied:
            return _fail(row, "denied_domain",
                         f"domain {_email_domain(email)} is on the deny list")

        # ── 3. calendar must be provably readable ────────────────────────────
        step = "calendar_unverified"
        if not verify_calendar_readable():
            return _fail(row, "calendar_unverified",
                         "busy_windows() returned nothing, which means the calendar "
                         "read failed or the week is implausibly empty — refusing to "
                         "book on an unverified calendar")

        # ── 4. slot ──────────────────────────────────────────────────────────
        step = "no_slots"
        chosen = slot or choose_slot()
        if not chosen or not chosen.get("start"):
            return _fail(row, "no_slots", "no bookable slot in the horizon")

        # ── 5. leads bridge ──────────────────────────────────────────────────
        # book_discovery_call.load_lead() reads the legacy `leads` table; the DM
        # lead lives in tenant_records. The bridge row is created only in apply
        # mode, and only by the DAO. Its id is derived from the conversation, so
        # a retry after a half-finished attempt adopts the same row rather than
        # leaving a second one behind.
        step = "lead_bridge"
        booking_lead_id = state.ensure_booking_lead(
            db, row, extracted=extracted, apply=apply, tenant_id=tenant
        )
        if apply and not booking_lead_id:
            return _fail(row, "lead_bridge",
                         "ensure_booking_lead returned no id in apply mode",
                         slot=chosen, meet_link=meet_link)

        # Render the email BEFORE the claim: a template failure must never leave a
        # claimed row or a booked calendar event behind it. The real room does
        # not exist yet — Google mints it during the calendar create — so the
        # probe renders against a placeholder purely to prove the TEMPLATE is
        # sound, and the body that actually gets sent is rendered again below
        # with the room that was really created.
        step = "email"
        try:
            subject, body_text = build_confirmation_email(
                first_name=_field(extracted, "name") or row.get("participant_name") or "",
                slot_label=str(chosen.get("label") or ""),
                slot_start_iso=str(chosen.get("start") or ""),
                meet_link=TEMPLATE_PROBE_LINK,
            )
        except ValueError as exc:
            return _fail(row, "email", f"confirmation template rejected: {exc}",
                         booking_lead_id=booking_lead_id, slot=chosen)

        if not apply:
            return CloseResult(
                ok=True, applied=False, conversation_id=conversation_id,
                row_id=row_id, stage_of_failure=None,
                booking_lead_id=booking_lead_id,
                slot_start=str(chosen.get("start") or ""),
                slot_end=str(chosen.get("end") or ""),
                slot_label=str(chosen.get("label") or ""),
                # No room is reported, because none exists yet and none is
                # reserved: it is minted by the calendar create that a dry run
                # does not perform. Reporting the old static room here said
                # "this is the room" about a URL the booking would not use.
                meet_link=None, calendar_output=None,
                email_status="dry_run",
                email_reason=f"dry_run: {subject} (the Meet room is minted when "
                             f"the event is created)",
                notify_ok=False, notify_reason="dry_run: no notification sent",
                error=None,
            )

        compat = _compat_db(db)

        # ── 7. claim — THE IDEMPOTENCY BOUNDARY ──────────────────────────────
        step = "claim_lost"
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
        step = "calendar_create"
        booking = book_discovery_call.book(
            compat, booking_lead_id, str(chosen["start"]), apply=True
        )
        calendar_output = str(booking.get("calendar_output") or "")[:300] or None
        if not booking.get("ok") or not booking.get("applied"):
            err = str(booking.get("error") or "calendar create failed")
            # Parked through the helper, not bare: fail_booking raises
            # BookingClaimLost when the claim moved, and letting that escape here
            # would degrade an accurate "calendar_create" report into "unexpected"
            # AND re-enter the same failing call from the outer handler.
            err = _park(state, db, row_id, claim_token=claim_token, error=err,
                        tenant_id=tenant)
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, "calendar_create", err, conversation_id)
            return _fail(row, "calendar_create", err,
                         booking_lead_id=booking_lead_id, slot=chosen,
                         meet_link=meet_link, calendar_output=calendar_output,
                         notify_ok=n_ok, notify_reason=n_reason)
        applied = True
        start_iso = str(booking.get("start") or chosen.get("start") or "")
        end_iso = str(booking.get("end") or chosen.get("end") or "")

        # ── 8b. the room, read back off what was actually created ────────────
        # There is NO fallback to the static GOOGLE_MEET_LINK. A silent fallback
        # is exactly how two prospects end up in one room, and google_tool
        # refuses the same substitution one layer down. If the event exists
        # without a room, that is a real meeting a human has to cancel or repair,
        # so it is parked with the CALENDAR EXISTS warning and reported.
        step = "meet_link_missing"
        meet_link = str(booking.get("meet_link") or "").strip() or None
        if not meet_link:
            err = (f"{CALENDAR_EXISTS_PREFIX}the calendar event was created but "
                   f"no Meet room came back with it, so there is no room to send. "
                   f"Cancel or repair the event before retrying.")
            err = _park(state, db, row_id, claim_token=claim_token, error=err,
                        tenant_id=tenant)
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, "meet_link_missing", err, conversation_id)
            return _fail(row, "meet_link_missing", err, applied=True,
                         booking_lead_id=booking_lead_id, slot=chosen,
                         calendar_output=calendar_output,
                         notify_ok=n_ok, notify_reason=n_reason)

        # Re-render with the real room. The probe above proved the template is
        # sound, so this can only fail on the link itself.
        try:
            subject, body_text = build_confirmation_email(
                first_name=_field(extracted, "name") or row.get("participant_name") or "",
                slot_label=str(chosen.get("label") or ""),
                slot_start_iso=str(chosen.get("start") or ""),
                meet_link=meet_link,
            )
        except ValueError as exc:
            step = "email"
            err = (f"{CALENDAR_EXISTS_PREFIX}confirmation template rejected the "
                   f"minted room: {exc}")
            err = _park(state, db, row_id, claim_token=claim_token, error=err,
                        tenant_id=tenant)
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, "email", err, conversation_id)
            return _fail(row, "email", err, applied=True,
                         booking_lead_id=booking_lead_id, slot=chosen,
                         meet_link=meet_link, calendar_output=calendar_output,
                         notify_ok=n_ok, notify_reason=n_reason)

        # ── 9. confirmation email — non-fatal ────────────────────────────────
        # The invite already went out. A failed confirmation email downgrades the
        # quality of the booking; it does not un-book it. The status travels to the
        # operator verbatim so a human can repair it.
        step = "email"
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
        step = "finalize"
        try:
            state.finalize_booking(
                db, row_id, claim_token=claim_token, start_iso=start_iso,
                end_iso=end_iso, meet_link=meet_link, email_status=email_status,
                # The meeting's inverse. book() parses it off google_tool's
                # "Event-Id:" line; persisting it is what makes
                # `google_tool.py calendar delete <id>` reachable later. The
                # invite is already in the prospect's inbox by now.
                event_id=(booking or {}).get("event_id"),
                tenant_id=tenant,
            )
            finalized = True
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

        # The notification is the LAST thing, and it can no longer decide the
        # outcome: the meeting exists and the row says so, both irreversibly. A
        # notifier that raises here used to make close() report ok=False /
        # stage_of_failure="unexpected", so the poller alerted "booking failed"
        # about a meeting that was on the calendar and in a stranger's inbox.
        step = "notify"
        label = _notify_safe(chosen.get("label"), limit=64)
        if email_status == "sent":
            notify_ok, notify_reason = _notify_call(
                notifier,
                f"Booked: @{handle}, {label}. Meet link emailed to {email}. "
                f"Conversation {conversation_id}.",
                dedup_key=f"igdm:{conversation_id}:booked",
            )
        else:
            # A meeting that exists with no confirmation email is its own state,
            # not a footnote on a success. The prospect has a Google invite whose
            # only room link is the one this email was carrying, so a human has to
            # finish the job by hand — and gets told exactly that, on its own
            # dedup key so it cannot be collapsed into the plain "Booked" alert.
            notify_ok, notify_reason = _notify_call(
                notifier,
                f"BOOKED BUT NOT CONFIRMED: @{handle}, {label}. The meeting exists "
                f"on the calendar and the Google invite went out, but the "
                f"confirmation email to {email} did NOT send "
                f"(status {_notify_safe(email_status, limit=40)}: "
                f"{_notify_safe(email_reason, limit=100) or 'no reason given'}). "
                f"Send the room link by hand. Conversation {conversation_id}.",
                dedup_key=f"igdm:{conversation_id}:booked_email_failed",
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

    except BaseException as exc:  # noqa: BLE001 — the boundary; nothing is swallowed
        # BaseException, not Exception. KeyboardInterrupt and SystemExit are not
        # Exceptions, so the old handler let them fly straight past the claim:
        # Ctrl-C during the first supervised `--apply` (the documented arming
        # plan, blocked for up to 180s inside the google_tool subprocess) left the
        # row at booking_status='claimed' with automation_paused=0,
        # handoff_pending=0 and stage untouched. Google may already have inserted
        # the event and mailed the invite. That row is invisible to
        # `list --handoffs`, permanently un-bookable (every later close() dies at
        # the precondition), and the every-minute cron keeps replying to a
        # prospect who may already hold an invite.
        #
        # The row is parked and the operator is told, and THEN the interrupt is
        # re-raised: an operator who pressed Ctrl-C means it, and swallowing a
        # SystemExit would break every caller's shutdown path. The "NEVER RAISES"
        # contract covers Exception, which is what a caller can meaningfully
        # handle. A kill -9, a PM2 restart or a cron timeout still bypasses this
        # entirely — `ig_dm_state.py list --stale-claims` is what finds those.
        traceback.print_exc()
        detail = f"{type(exc).__name__}: {exc}"
        # Name the step that actually failed. "unexpected" is reserved for a raise
        # from somewhere the step marker never reached, and it is the one word an
        # operator can do nothing with.
        failed_at = step if step in STAGES_OF_FAILURE else "unexpected"
        if applied:
            # The calendar event is out there. Whoever reads booking_error next is
            # deciding whether to reset and retry; retrying blind double-books.
            detail = f"{CALENDAR_EXISTS_PREFIX}{detail}"
        elif failed_at == "calendar_create":
            # A raise from inside book() — a subprocess timeout is the realistic
            # one — leaves the event's existence genuinely unknown. Saying nothing
            # here reads as "no event", which is the assumption that double-books.
            detail = f"{CALENDAR_UNKNOWN_PREFIX}{detail}"

        # Park the row unless it was already finalized. `finalized`, never
        # `applied`: a booking that reached finalize_booking is 'booked' and its
        # claim token still matches, so fail_booking would happily rewrite a real
        # meeting into 'failed' + handed_off.
        if claim_token and not finalized:
            detail = _park(_require_state(), db, row_id, claim_token=claim_token,
                           error=detail, tenant_id=tenant)

        n_ok, n_reason = (False, "not attempted")
        if claim_token:
            n_ok, n_reason = _notify_booking_failed(
                notifier, handle, failed_at, detail, conversation_id)
        if not isinstance(exc, Exception):
            # Parked and reported; now let the interrupt do its job.
            raise
        return _fail(row, failed_at, detail, applied=applied,
                     booking_lead_id=booking_lead_id, slot=chosen,
                     meet_link=meet_link, calendar_output=calendar_output,
                     email_status=email_status, email_reason=email_reason,
                     notify_ok=n_ok, notify_reason=n_reason)


def _park(state: Any, db: Any, row_id: str, *, claim_token: str, error: str,
          tenant_id: str) -> str:
    """fail_booking() the row and return the error string to REPORT.

    Parking is what makes a dead booking recoverable: fail_booking sets
    handoff_pending, automation_paused and stage='handed_off', none of which
    claim_booking touches. A row left at 'claimed' is therefore invisible to
    `ig_dm_state.py list --handoffs` while the automation keeps replying.

    When the park itself fails — the claim moved, the database is unreachable —
    that fact is APPENDED to the error rather than swallowed, so the operator
    alert says the row is still claimed instead of implying it was parked.
    """
    try:
        state.fail_booking(db, row_id, claim_token=claim_token, error=error,
                           tenant_id=tenant_id)
        return error
    except Exception as exc:  # noqa: BLE001 — reported, never hidden
        traceback.print_exc()
        note = (f" [ROW NOT PARKED: booking_status is still 'claimed' and the "
                f"automation is NOT paused — {type(exc).__name__}: {exc}]")
        print(f"[ig_closer] fail_booking could not park {row_id}: {exc}",
              file=sys.stderr)
        return f"{error}{note}"


def _notify_call(notifier: Callable[..., tuple[bool, str]], message: str, *,
                 dedup_key: str) -> tuple[bool, str]:
    """Send an operator notification. A dead notifier is never a booking failure.

    The whole assembled body is passed through _notify_safe here — the single
    chokepoint — rather than each interpolated fragment being sanitised at its
    own call site. notify() routes on MESSAGE CONTENT: a body matching
    _NOT_BRAVO_DOMAIN_RE is DROPPED outright, so a prospect whose email address
    is phone_lookup@gmail.com silences the alert about their own booking. Every
    site that sanitised its own fragments still left the recipient address raw,
    which is what guarding the fragment instead of the class always costs. A
    later edit that interpolates one more stranger-shaped field is covered by
    construction.
    """
    try:
        return notifier(_notify_safe(message, limit=_MAX_NOTIFY_BODY_CHARS),
                        category=NOTIFY_CATEGORY, dedup_key=dedup_key)
    except Exception as exc:  # noqa: BLE001 — traced; the booking result stands
        traceback.print_exc()
        return False, f"notifier raised: {type(exc).__name__}: {exc}"


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

    The dedup key carries the STEP. Two different failures on one conversation
    inside NOTIFY_DEDUP_WINDOW_SEC (an hour by default) used to collapse into one
    alert, so the second condition — the one that changed — was never surfaced.
    """
    ok, reason = _notify_call(
        notifier,
        f"Booking failed: @{handle} at step {stage_of_failure}. "
        f"{_notify_safe(error)}. Conversation {conversation_id}.",
        dedup_key=f"igdm:{conversation_id}:booking_failed:{stage_of_failure}",
    )
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
        print(f"  meet room   : {result.meet_link or 'minted when the event is created'}")
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
