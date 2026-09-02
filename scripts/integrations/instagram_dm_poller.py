"""instagram_dm_poller.py — run OASIS Instagram DMs like a human closer.

Someone DMs @oasisaisolutions; the whole thread is read, a reply is written in
the operator's voice by the conversational brain, contact details are extracted
from what the prospect actually typed, and when they are warm the close loop
books the call. State lives in Turso, one row per conversation.

WHY POLLING AND NOT A WEBHOOK. Zernio supports both. Polling was chosen because
every endpoint it needs is verified working today, it needs no public URL or
dashboard step, and — the operator's actual requirement — a cron job SHOWS UP in
the Automations tab and can be switched off there. A passive webhook endpoint
would be invisible on that screen.

WHAT REPLACED THE KEYWORD CLASSIFIER (2026-08-20). The old build matched a word
list against the newest message and pasted one of two templates. It shipped three
defects that this rewrite removes at the root:

  * It read its OWN replies as prospect messages. `_incoming_text` compared
    `senderId` to `conversation.accountId`, but the outgoing senderId is an IGSID
    (17841478511636355) and accountId is a Zernio ObjectId — different
    namespaces, so the comparison could never be true. The template it had just
    sent contained the word "audit", which scored as buying intent, and the bot
    answered itself. Attribution is now `direction` only, and `needs_reply()`
    refuses to act unless the LAST turn is theirs.
  * It could only ever say two things, so a real conversation went nowhere.
  * Its 24h cooldown was the only send throttle, which is right for a one-shot
    autoresponder and fatal for a closer. A per-conversation and per-day reply
    budget replaces it.

The classifier, both templates, the JSON state file and the cooldown are DELETED,
not disabled. Dead fallbacks get resurrected by accident.

MODULE BOUNDARIES (one-way, acyclic — see docs/IG_DM_CLOSER_CONTRACT.md):
    poller -> ig_conversation_brain   (pure: no DB, no network beyond the model)
    poller -> ig_dm_state             (the only module that writes SQL)
    poller -> ig_closer               (booking; only when --book is passed)
Nothing imports the poller.

VERIFIED ZERNIO API (probed live 2026-08-20):
    GET  /v1/inbox/conversations
         -> {"data":[{id, accountId, accountUsername, platform, participantId,
                      participantUsername, participantName, lastMessage,
                      updatedTime, status, unreadCount, url, ...}]}
    GET  /v1/inbox/conversations/{id}/messages?accountId=..&limit=N&sortOrder=desc
         -> {"messages":[...], "pagination":{"hasMore":bool,"nextCursor":...},
             "sortOrderApplied":"asc"|"desc"}
    POST /v1/inbox/conversations/{id}/messages  {"accountId":.., "message":..}
`limit` and `sortOrder` are REAL parameters, not ignored: probed at limit=3 the
response carried 3 messages and hasMore=true, and sortOrder=desc flipped
sortOrderApplied. This matters — the default order is ASCENDING, so a server-side
page cap on a long thread would hand back the OLDEST messages and `needs_reply()`
would judge a stale tail. The thread is therefore fetched newest-first and
reversed locally.
Zernio answers 200 with its web-app HTML for ANY unknown path, so never treat a
200 as proof a route exists — compare the body against a known-fake control.

SAFETY, in the order it is enforced:
  1. Dry run unless --live. Nothing leaves the machine by default.
  2. Only @oasisaisolutions on instagram. Every other connected profile is out of
     scope.
  3. --only-handle scopes the whole run to one handle, so the first live test
     goes to CC's own account and never a real prospect.
  4. --book (default OFF) is the only thing that lets the closer create a real
     calendar event and mail a stranger a Google invite. Without it a booking
     request becomes a handoff to CC.
  5. Reply budget: 3 per conversation per UTC day, 40 across the tenant, 120s
     minimum gap. Enforced in SQL before a model call is spent.
  6. A failed model call NEVER produces a fallback message. It is counted, and
     three in a row hand the conversation to a human.

Usage:
    python scripts/integrations/instagram_dm_poller.py --limit 3         # dry run
    python scripts/integrations/instagram_dm_poller.py --live --only-handle ccmckennaa
    python scripts/integrations/instagram_dm_poller.py --live --json     # armed, no booking
    python scripts/integrations/instagram_dm_poller.py --live --book     # armed + booking
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import socket
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from lib.subprocess_helpers import pid_is_gone  # noqa: E402

CAPABILITY_META = {
    "category": "growth.inbound",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": ["instagram dm automation", "poll instagram dms", "answer instagram dms"],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": True},
}

API_BASE = "https://zernio.com/api"
TARGET_PLATFORM = "instagram"
TARGET_ACCOUNT = "oasisaisolutions"

OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
LOCK_PATH = PROJECT_ROOT / "state" / "instagram_dm_poller.lock"

AUDIT_FORM_URL = "https://oasisai.work/f/oasis-ai-cc/ai-audit"

# ── run budgets ──────────────────────────────────────────────────────────────
# MEASURED on this machine 2026-08-20, not assumed: run_claude_cli with a
# one-word prompt took 29.2s / 26.7s / 28.1s / 25.8s — median 27.4s. The cost is
# `claude -p` process startup, not generation, so a real conversation turn is no
# cheaper. An earlier draft of this file claimed ~11s and sized the run at 12
# calls; that would be ~330s, which overruns both the deadline below and the
# cron tick — and a run that outlives its tick is exactly what double-texted CC
# on 2026-08-20.
#
# decide() may spend TWO subprocesses per conversation (one retry), so the true
# worst case is 2x. Sizing: 5 turns x 2 attempts x ~30s = ~300s worst case, and
# the deadline stops the loop before starting a turn it cannot finish, bounding
# a run at RUN_DEADLINE_SECONDS + one turn (~270s) — inside the */5 tick the
# live cron row already uses.
#
# This cap rarely binds in practice: the inbox holds 50 conversations but
# typically only ~2 carry genuinely new inbound, and every cheap gate runs
# before a model call is spent.
# RETUNED 2026-08-21 for a */1 schedule. At */5 a prospect waited 9 minutes for
# an answer (inbound 07:37, reply 07:46) — the system working exactly as
# configured, and reading as broken to the human sitting there. A setter cannot
# feel like a batch job.
#
# Going to */1 aims a run at finishing inside a minute, so the per-run budget
# comes down as the cadence goes up: 2 turns x ~27s is ~55s plus HTTP.
#
# WHAT THE CADENCE ACTUALLY IS, corrected 2026-08-21. An earlier version of this
# comment claimed "a long run simply causes the next tick to skip" via the O_EXCL
# lock. That mechanism does not engage in this deployment: scheduler.py is a
# SINGLE-THREADED loop that runs every due job sequentially and only then sleeps,
# so it cannot start a second poll while this one is running — the lock never
# races the scheduler, and the real interval is (this run) + (every other due
# job) + the loop's sleep. Measured live over 12 minutes the job fired at 291s,
# 255s and 166s intervals against a schedule of '* * * * *'. The lock still earns
# its place against a MANUAL run overlapping the cron; it is not a cadence
# guarantee, and nothing here should be sized as though it were.
#
# This trades throughput per run for responsiveness, which is the right trade
# here: the inbox holds 50 conversations but typically only ~2 carry genuinely
# new inbound, so 2 turns per minute clears far more volume per hour than 5 turns
# per five minutes.
# RESIZED 2026-08-21, after the watermark (migration bravo__011) made a sweep
# cost roughly one HTTP call instead of one per thread.
#
# The old numbers were sized around a sweep that re-read every thread every tick:
# 2 turns and a 55s deadline, where ~25 wasted GETs at ~1.2s each already ate 30s
# of that 55s. A run reached conversation 25 of 50 and stopped. With skips now
# free, the deadline can be spent on CONVERSATION instead of on bookkeeping.
#
# Sizing, from the measured 27.4s median per `claude -p` turn (decide() may spend
# two subprocesses on a retry, so the worst case is 2x):
#     4 turns x 27s          = ~110s of model time
#   + a swept inbox           = ~5-15s
#   = 150s deadline, with the last turn allowed to overrun to ~204s.
# ig_dm_daemon.TICK_TIMEOUT is 300s, so even the worst case lands inside it.
#
# THROUGHPUT, stated plainly because "scalable" has to mean a number: 4 replies
# per run, a run every ~150s under load, is ~96 replies/hour. Ticks that find
# nothing still cost one HTTP call and finish in about a second, so an idle inbox
# stays responsive at the daemon's 20s interval. If real volume ever exceeds
# that, the next lever is concurrency across model calls — NOT a bigger number
# here, because these are serial `claude -p` subprocesses on one subscription.
# RETUNED 2026-08-22 from MEASURED latency with the REAL prompt (11K-char
# system + JSON contract): p50 73-88s, p95 ~106s per call — NOT the 27s a
# one-word probe suggested. The old deadline (150s) gave the model
# min(90, deadline-elapsed), often UNDER a median call, so the deadline was
# manufacturing the model_unavailable failures it exists to prevent —
# @adonyess carries one. Three of those in a row hand a live prospect to a
# human for nothing. Sizing: 3 calls x ~110s p95 = ~330s; deadline 360 with
# the ceiling at 150 keeps one slow retry inside the budget. The tick is no
# longer racing a shared scheduler — bravo-ig-dm owns the loop — so a longer
# run costs nothing but its own latency.
MAX_MODEL_CALLS_PER_RUN = 3
RUN_DEADLINE_SECONDS = 360

# How deep into the inbox one run looks. This was 25 against a 50-thread inbox,
# which meant threads 26..50 were NEVER examined — not answered late, never read
# at all. Ordering is `updatedTime` DESC so a fresh DM sorts to the top and was
# usually caught, but "usually, by luck of sort order" is not a guarantee, and it
# fails exactly when it matters: a burst of 25+ threads pushes real prospects
# below the cut and they are silently abandoned. Now that an unchanged thread
# costs no HTTP at all, there is no reason not to sweep the whole inbox.
DEFAULT_SCAN_LIMIT = 200

# ── which outcomes mean "done with this thread for now" ──────────────────────
# A CONCLUSION is a state where nothing further can be learned about the thread
# until it moves again: we answered, it was not our turn, Zernio has no message
# bodies for it, we had already answered that exact message, or a human now owns
# it. Those may stamp the examined-watermark.
#
# A DEFERRAL is "come back to this one": the run ran out of model calls or clock,
# the model failed, the guardrail rejected the draft, or the per-conversation
# reply gap has not elapsed. Stamping a watermark on any of those would mark a
# WAITING prospect as examined and skip them until their next message — the exact
# silent mid-conversation death this pipeline exists to prevent. So a deferral in
# the delta vetoes the stamp even if a conclusion is also present.
_CONCLUSIVE_KEYS = (
    "replied", "skipped_our_turn", "skipped_no_messages",
    "skipped_seen", "skipped_red_flag", "skipped_paused", "handoffs",
)
_DEFERRAL_KEYS = (
    "skipped_budget", "budget_exhausted", "starved",
    "failures_model", "failures_guardrail", "errors",
)


def _is_conclusive(delta: dict) -> bool:
    if any(delta.get(k) for k in _DEFERRAL_KEYS):
        return False
    return any(delta.get(k) for k in _CONCLUSIVE_KEYS)

# The deadline has to bound the RUN, not just the model calls inside it. It is
# checked at the TOP of every conversation — before the per-thread GET, which
# uses urllib with timeout=30 and runs up to --limit 25 times — and it is what
# sizes the model timeout below. Before 2026-08-21 it was consulted once, at
# step 9, AFTER the fetch, so a degraded Zernio cost 25 x 30s = 750s and the
# scheduler's own subprocess.run(timeout=600) killed the run mid-scan: no
# summary printed, and the lock file left behind for the stale-lock sweeper.
#
# MODEL_TIMEOUT_FLOOR_SECONDS is the point below which a call is not worth
# starting: run_claude_cli is startup-dominated at ~27s median on this machine,
# so a 10s budget buys nothing but a guaranteed timeout. decide() may spend TWO
# subprocesses, so the worst-case model time is 2x whatever is passed.
MODEL_TIMEOUT_FLOOR_SECONDS = 105   # below p50 is not worth starting
MODEL_TIMEOUT_CEILING_SECONDS = 150  # above p95 + margin is a hang, kill it

# ── fair scheduling: the run is TWO passes, not one interleaved walk ─────────
#
# THE STARVATION THIS FIXES (measured 2026-08-21). Zernio returns the inbox
# ordered by `updatedTime` DESC, and `updatedTime` tracks the newest message in
# EITHER direction — our own reply bumps a thread straight back to rank 0
# (Zernio's stamp landed 95-148ms after our locally-written last_outbound_at on
# all three live rows). So the shipped order was LIFO by last activity: a
# prospect who messaged once and is waiting has a FROZEN stamp, and every new
# event in the inbox — including our replies to someone chattier — sorts above
# them. Their rank decays monotonically. Priority was inversely proportional to
# how long someone had waited, which is the exact inverse of what a setter needs.
# Under sustained arrivals the oldest waiter's wait was unbounded, and nothing
# counted it: the model-budget gate `break`-ed the scan, so a starved prospect
# was not even a skip.
#
# Worse, that `break` also skipped the FREE work. An opt-out sitting below two
# chatty threads was never read: no red-flag handoff, no counter, no trace.
#
# So:
#   pass 1  every in-scope conversation, every zero-model gate, no exceptions
#   pass 2  the surviving candidates sorted OLDEST-UNANSWERED-INBOUND FIRST,
#           model calls spent from the front of that queue
#
# The order is computed here from the prospect's own message timestamp. It does
# not depend on the order Zernio handed the page back in, and it is stable:
# ties break on conversation id, so the same inbox always produces the same queue.
#
# SCAN_RESERVE_SECONDS is what pass 1 must leave on the clock for pass 2. Pass 1
# costs one messages GET per moved thread (measured mean 0.80s, max 1.23s over
# 25 live threads = ~20s of a 55s deadline), and a run that spends the whole
# deadline discovering who is waiting and then answers nobody is worse than the
# LIFO order it replaced. One model call is startup-dominated at ~27s, so the
# reserve is the floor timeout: pass 1 stops scanning with at least one full
# model turn still affordable.
SCAN_RESERVE_SECONDS = MODEL_TIMEOUT_FLOOR_SECONDS

# API cost of reading the FULL thread: one extra GET per conversation that has
# moved since our last reply. The list call already carries `updatedTime`, so a
# quiet inbox costs exactly one HTTP request per poll. 60 raw messages is a
# deliberate overshoot of the brain's 40-turn window — deleted, empty and
# attachment-only messages are dropped during attribution, so the window has to
# be filled from a larger pool.
THREAD_FETCH_LIMIT = 60

# `money` is deliberately NOT here. "how much?" is the most common inbound DM on
# this account; handing every one of them to a human defeats the automation. The
# brain deflects the number and moves to the call.
HANDOFF_RED_FLAGS = ("opt_out", "frustrated", "outage", "strategic")

# Stages that END the conversation: ig_dm_state sets automation_paused=1 for
# every one of them, so the poller will never speak to that person again. Kept
# here (rather than imported from the DAO) because the poller must be able to
# recognise the ending BEFORE the write that causes it, on the dry-run path where
# the DAO is never called. test_terminal_stages_match_the_dao pins the two lists.
TERMINAL_STAGES = frozenset({"booked", "handed_off", "disqualified"})

NOTIFY_CATEGORY = "lead"  # never "instagram": blocked, and routed to Maven's bot

_SIBLING_ROLES = {
    "ig_conversation_brain": "the conversational brain (Builder A)",
    "ig_dm_state": "the conversation-state DAO (Builder C)",
    "ig_closer": "the booking close loop (Builder B)",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _api_key() -> str:
    from lib.secret_loader import load_env  # type: ignore

    key = (load_env().get("LATE_API_KEY") or "").strip()
    if not key:
        raise SystemExit("ERROR: LATE_API_KEY missing from the agents env")
    return key


REQUEST_TIMEOUT_SEC = 30
# One retry, on transient TRANSPORT faults only.
#
# WHY (2026-09-02): a single socket read timeout on GET /v1/inbox/conversations
# raised straight out of _poll and killed the whole tick — twice in forty
# minutes (tmp/ig_dm_failures/tick-20260902T200052Z, -204048Z). Measured live
# the same hour, that endpoint answers in 0.3-1.0s across three calls with 50
# conversations, so 30s is not too tight; the blips are the network, and a
# prospect waiting on a reply should not lose a whole cycle to one of them.
#
# Deliberately NOT retried: HTTPError (the server answered — 4xx/5xx is a real
# verdict), and an HTML body (the route does not exist). Retrying those would
# hammer a broken endpoint and hide the fault. A POST is not retried either:
# these send DMs, and a timeout after the server already accepted one would
# double-message a real person.
_TRANSIENT_NET = (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError)


def _request(key: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    """Call Zernio. Raises on a non-JSON body, because a 200 of HTML means the
    route does not exist and must never be read as success."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    attempts = 2 if method == "GET" else 1
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
        except _TRANSIENT_NET as exc:
            # HTTPError subclasses URLError, so it must be caught above this.
            if attempt >= attempts:
                raise RuntimeError(
                    f"{method} {path} -> {type(exc).__name__} after {attempt} "
                    f"attempt(s) at {REQUEST_TIMEOUT_SEC}s each: {exc}"
                ) from exc
            sys.stderr.write(
                f"[ig_dm_poller] transient {type(exc).__name__} on {method} {path} "
                f"(attempt {attempt}/{attempts}) — retrying\n"
            )
    if raw.lstrip().startswith("<"):
        raise RuntimeError(f"{method} {path} returned HTML — that route does not exist")
    return json.loads(raw) if raw.strip() else {}


class _RunLock:
    """Refuse to start when another poll is already in flight.

    Persisting reply state per-reply narrows the double-send window but does not
    close it: two runs can still pass the same budget check microseconds apart.
    One run at a time is the actual guarantee. O_EXCL creation is atomic on
    Windows and POSIX alike, so the loser of the race gets the error rather than
    a second copy of the conversation.
    """

    def __init__(self, path: Path, stale_after_minutes: int = 15):
        self.path = path
        self.stale_after = timedelta(minutes=stale_after_minutes)
        self.acquired = False

    def __enter__(self) -> "_RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            # A killed run must not wedge the automation permanently.
            age = _now() - datetime.fromtimestamp(
                self.path.stat().st_mtime, tz=timezone.utc
            )
            # Ask whether the holder is ALIVE before waiting out the clock
            # (2026-09-02). The age fence alone meant every hard kill cost up
            # to 15 minutes of dead air: observed live with the lock at 14.8
            # minutes, holder pid 34424 long gone, and the daemon logging
            # "skipped: another poll holds the lock" every 20s the whole time —
            # a setter that reads Running and answers nobody, which is exactly
            # the complaint that started this. The lock exists to stop two LIVE
            # runs; a dead holder is not one.
            #
            # The age fence stays as the backstop, because a recycled PID can
            # belong to something else entirely and an unreadable lock must not
            # be assumed dead.
            if age > self.stale_after or self._holder_is_gone():
                print(f"  [warn] clearing stale lock ({int(age.total_seconds())}s old)",
                      file=sys.stderr)
                self.path.unlink(missing_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit("another poll is already running — exiting without sending")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        self.acquired = True
        return self

    def _holder_is_gone(self) -> bool:
        """True only when the recorded PID provably no longer exists.

        The liveness probe itself lives in lib/subprocess_helpers.pid_is_gone,
        because fleet_watchdog's supervision lock has the same shape and the
        same defect — two copies of "is this holder dead" is one copy too many
        for a predicate whose wrong answer sends a prospect two replies.

        Unreadable lock or non-numeric pid stays here and fails closed: that is
        this lock's own file format, not a property of pids.
        """
        try:
            pid = int(self.path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        return pid_is_gone(pid)

    def __exit__(self, *_exc) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)


def _lead_exists(handle: str) -> bool:
    """Is there already a lead for this Instagram handle?

    Asks SQL to do the matching. The previous version read a 500-row page of
    tenant_records and compared handles in Python — against 31k leads that page
    never contained the handle, so every run believed the sender was new and
    inserted another lead. Filtering has to happen where the rows are.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib.db_turso import get_db  # type: ignore

    # query() returns rows; execute() returns a cursor that is truthy even when
    # it selected nothing, which would report every handle as already existing.
    rows = get_db().query(
        "select 1 as hit from tenant_records "
        "where tenant_id = ? and entity_type = 'lead' "
        "and lower(json_extract(data, '$.instagram_handle')) = lower(?) limit 1",
        (OASIS_TENANT_ID, str(handle)),
    )
    return bool(rows)


def _lead_id_for_handle(handle: str) -> Optional[str]:
    """The tenant_records id of this handle's lead, or None.

    Separate from _lead_exists on purpose: that function is the pinned existence
    predicate (tests/test_ig_dm_closer.py asserts its SQL shape and that it
    issues exactly one query), and the conversation row needs the actual id so
    the DM thread and the CRM record can be reconciled later. Same scoped,
    SQL-side, LIMIT 1 shape — no page read, no Python-side comparison.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib.db_turso import get_db  # type: ignore

    rows = get_db().query(
        "select id from tenant_records "
        "where tenant_id = ? and entity_type = 'lead' "
        "and lower(json_extract(data, '$.instagram_handle')) = lower(?) limit 1",
        (OASIS_TENANT_ID, str(handle)),
    )
    return str(rows[0]["id"]) if rows else None


def _upsert_lead(conv: dict, text: str, reason: str) -> tuple[str, Optional[str]]:
    """Create the CRM lead if this handle is new.

    Returns (status, lead_id) where status is "created" or "existing". The id is
    the change from the 2026-08-20 build, which generated the uuid inline and
    threw it away — leaving no way to link the conversation row to the lead it
    had just created.

    `reason` is a short agent-authored label for the notes field (the stage the
    brain moved to). It replaces the old `matched` keyword, which no longer
    exists now that the classifier is gone.
    """
    from supabase_tool import get_client, load_env  # type: ignore

    db = get_client(load_env())
    handle = conv.get("participantUsername") or conv.get("participantId") or "unknown"
    if _lead_exists(handle):
        return "existing", _lead_id_for_handle(handle)

    lead_id = str(uuid.uuid4())
    now = _iso(_now())
    data = {
        "name": conv.get("participantName") or handle,
        "company": None,
        "email": None,
        "phone": None,
        "source": "instagram_dm",
        "stage": "researched",
        "score": 55,
        "value_estimate": None,
        "notes": f"Instagram DM (@{handle}), {reason}: {text[:180]}",
        "instagram_handle": handle,
        "instagram_profile_url": conv.get("url"),
        "first_dm_at": now,
        "first_dm_text": text[:500],
        "stage_entered_at": now,
        "created_from": "instagram_dm_poller",
    }
    db.table("tenant_records").insert(
        {
            "id": lead_id,
            "tenant_id": OASIS_TENANT_ID,
            "entity_type": "lead",
            "data": data,
            "created_at": now,
            "updated_at": now,
        }
    ).execute()
    return "created", lead_id


# ── sibling modules ──────────────────────────────────────────────────────────

def _sibling(name: str):
    """Import one of the three sibling modules, or fail with a named diagnostic.

    Deferred rather than done at module scope so that --help, the argument
    parser and the pinned _lead_exists tests keep working while a sibling is
    still in flight. A genuine error INSIDE a sibling still propagates — only
    absence is reported specially, and it is reported loudly.
    """
    path = Path(__file__).with_name(name + ".py")
    if not path.exists():
        raise SystemExit(
            f"ERROR: {name}.py is missing at {path}.\n"
            f"       It is {_SIBLING_ROLES.get(name, 'a required module')}. The poller "
            f"cannot read conversation state, decide a reply or book without it. "
            f"Nothing was sent."
        )
    return importlib.import_module(name)


def _notifier():
    from notify import notify_result  # type: ignore

    return notify_result


MAX_NOTIFY_DETAIL_CHARS = 200
_NOTIFY_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _notify_safe(text: Any, limit: int = MAX_NOTIFY_DETAIL_CHARS) -> str:
    """Make an untrusted fragment safe to interpolate into a Telegram body.

    Three of the strings this poller puts in a notification are shaped by a
    stranger: the model-authored `handoff_reason` (which crosses NONE of the 16
    reply guardrails — validate_reply only runs for action reply/book), the
    Zernio `participantUsername`, and a closer error that may echo either. notify()
    routes on MESSAGE CONTENT, so an attacker who gets any of those to carry
    "TextTorrent" or "phone lookup" trips _NOT_BRAVO_DOMAIN_RE and notify() drops
    the alert ABOUT THEMSELVES before it ever reaches dedup — while
    request_handoff has already set automation_paused, so no later poll retries
    it and CC never learns the conversation exists.

    Blocked terms are masked, URLs are stripped (a 200-char attacker-steered
    string with a clickable link lands in CC's private Telegram over Bravo's
    name), newlines collapse, and the fragment is truncated. Mirrors
    ig_closer._notify_safe; kept local because ig_closer is imported only when
    --book is set and this path must work on every run.
    """
    if not text:
        return ""
    flat = " ".join(str(text).split())
    flat = _NOTIFY_URL_RE.sub("[link]", flat)
    try:
        import notify as notify_module  # type: ignore
    except Exception:  # noqa: BLE001 — masking is best-effort; truncation is not
        notify_module = None  # type: ignore[assignment]
    if notify_module is not None:
        for attr in ("_GROUP_BLOCKED_TERMS_RE", "_NOT_BRAVO_DOMAIN_RE"):
            pattern = getattr(notify_module, attr, None)
            if pattern is not None:
                flat = pattern.sub("[term]", flat)
    if len(flat) > limit:
        flat = flat[: limit - 1].rstrip() + "…"
    return flat


# Telegram's own body cap is 4096; leave headroom for notify()'s own framing.
# This is the WHOLE-BODY limit, not the per-fragment one — a body is only
# truncated here if every call site already failed to bound its fragments.
MAX_NOTIFY_BODY_CHARS = 3500


def _notify(text: str, *, conv_id: str, event: str, live: bool) -> tuple[bool, str]:
    """Telegram the operator. Agent-authored text ONLY.

    Never quote raw DM text here: notify() DROPS a body matching its
    _NOT_BRAVO_DOMAIN_RE (texttorrent / phone lookup / tps scrape) and REROUTES
    one matching _GROUP_BLOCKED_TERMS_RE (traceback / cron failure). A stranger
    typing "can you do phone lookup?" would otherwise silence the alert about
    themselves. Reads (ok, reason) because a bare False conflates "suppressed by
    dedup" with "delivery failed".

    `live` is the dry-run gate. A preview run must not page CC: the documented
    preview command is `--limit 25` with no --live, and a Telegram ping from a run
    the operator believed was read-only is an effect leaving the machine.
    """
    if not live:
        print(f"  [dry-run] WOULD NOTIFY ({event}): {text}")
        return False, "dry_run"
    # Belt AND braces on the same helper. _notify_safe already existed for
    # fragments, but several call sites interpolated the handle and the
    # model-authored handoff_reason raw — and those are exactly the strings an
    # attacker shapes. An IG username like `phone_lookup`, or a prospect asking
    # about texttorrent, matches notify()'s _NOT_BRAVO_DOMAIN_RE and the alert is
    # DROPPED, not rerouted, while request_handoff has already paused the
    # conversation: the prospect gets silence and CC never learns they exist.
    # Running it once more over the assembled body makes the guard structural
    # instead of a rule each caller has to remember. Masking is idempotent —
    # "[term]" does not re-match — so a fragment already cleaned is unharmed.
    text = _notify_safe(text, limit=MAX_NOTIFY_BODY_CHARS)
    try:
        ok, reason = _notifier()(
            text, category=NOTIFY_CATEGORY, dedup_key=f"igdm:{conv_id}:{event}"
        )
    except Exception as exc:  # noqa: BLE001 — a broken notifier must not kill the run
        traceback.print_exc()
        print(f"  [error] notify failed for {conv_id}: {exc}", file=sys.stderr)
        return False, "failed"
    if not ok and reason != "suppressed":
        print(f"  [warn] notify {event} for {conv_id}: {reason}", file=sys.stderr)
    return ok, reason


# ── helpers ──────────────────────────────────────────────────────────────────

# ── the operator-visible health surface ──────────────────────────────────────
#
# scheduler.py stored `out[-1][:200]` as cron_jobs.last_result — the last line of
# stdout, hard-capped at 200 characters. (Replaced 2026-08-29 by
# scheduler.summarize_stdout, which renders a JSON payload as a verdict and
# marks any truncation. The design below is no longer FORCED by the cap, but it
# is still the right shape and the reasoning still explains why.)
# The full-key summary was 358 characters,
# so EVERY counter that says something went wrong was cut off: skipped_budget
# started at char 214, skipped_red_flag 233, failures_model 254,
# failures_guardrail 273, budget_exhausted 296, errors 317. A run where every
# conversation hit the tenant-wide cap rendered identically to a healthy quiet
# inbox on the Automations tab.
#
# Two changes make the field honest:
#   1. short keys, failures FIRST, and zero-valued counters dropped, so the whole
#      picture fits inside the 200 characters that are actually stored;
#   2. an ERROR: prefix when the run genuinely failed. cron_health_check
#      .find_bad_crons only flags a job whose last_result starts with ERROR or
#      FAILED, and this job always exits 0 with a result starting '{', so the
#      hourly fleet watchdog rated it healthy no matter what it reported.
MAX_LAST_RESULT_CHARS = 200

# Full name -> stored key. Ordered: the things that mean "a human should look"
# first, so that even a future truncation loses the least important half.
_SUMMARY_KEYS: tuple[tuple[str, str], ...] = (
    ("errors", "errors"),                     # kept full: scheduler._FAILURE_KEYS
    ("failures_model", "f_model"),
    ("failures_guardrail", "f_guard"),
    ("handoffs", "handoff"),
    # starved = prospects who needed a reply this tick and did not get one. It
    # sits with the failures deliberately: before 2026-08-21 nothing counted it
    # at all, so an abandoned conversation was indistinguishable from a quiet
    # inbox on the Automations tab and in the daemon log.
    ("starved", "starved"),
    ("oldest_wait_s", "oldest_s"),
    ("skipped_no_messages", "unreadable"),
    ("skipped_budget", "budget"),
    ("budget_exhausted", "exhausted"),
    ("skipped_red_flag", "red_flag"),
    ("replied", "replied"),
    # The denominator that makes `replied` mean anything: replied=2 is healthy
    # against needed=2 and an incident against needed=9.
    ("needed_reply", "needed"),
    ("model_calls", "calls"),
    ("scanned", "scanned"),
    ("in_scope", "in_scope"),
    ("leads_created", "leads"),
    ("bookings_attempted", "book_try"),
    ("bookings_applied", "booked"),
    ("skipped_paused", "paused"),
    ("skipped_our_turn", "our_turn"),
    ("skipped_seen", "seen"),
    ("skipped_unchanged", "unchanged"),
)
# Always emitted, even at zero: their absence is itself information.
_SUMMARY_ALWAYS = frozenset({"errors", "replied", "needed_reply", "model_calls",
                             "scanned", "in_scope"})
# A run is FAILING — not merely quiet — when one of these is non-zero. Each one
# means at least one real prospect got silence they should not have got.
_SUMMARY_FAILURE_KEYS = ("errors", "failures_model", "failures_guardrail")


def _summary_line(summary: dict, *, as_json: bool = False) -> str:
    """The single line the scheduler will keep. Must fit MAX_LAST_RESULT_CHARS."""
    failing = any(int(summary.get(k) or 0) > 0 for k in _SUMMARY_FAILURE_KEYS)
    pairs = [
        (short, int(summary.get(full) or 0))
        for full, short in _SUMMARY_KEYS
        if full in _SUMMARY_ALWAYS or int(summary.get(full) or 0)
    ]
    if as_json:
        body = {k: v for k, v in pairs}
        body["live"] = bool(summary.get("live"))
        if summary.get("book_armed"):
            body["book_armed"] = True
        line = json.dumps(body, separators=(",", ":"))
    else:
        line = "  " + "  ".join(f"{k}={v}" for k, v in pairs)
        line += f"  live={bool(summary.get('live'))}"
    if failing:
        line = "ERROR: " + line
    return line[:MAX_LAST_RESULT_CHARS]


def _parse_iso(value: Any) -> Optional[datetime]:
    """Zernio stamps are '...Z'; the DAO writes offset-aware ISO. Returns None
    when unparseable — every caller treats None as "cannot prove it, do the
    safe thing" rather than as a value."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fetch_thread(key: str, conv_id: str, account_id: str) -> list[dict]:
    """The newest THREAD_FETCH_LIMIT messages, oldest-first.

    Fetched with sortOrder=desc and reversed. Asking for the default ascending
    order and slicing the tail locally is wrong: if the server ever caps the
    page, ascending hands back the OLDEST messages and the last element is not
    the newest message at all — which would make needs_reply() judge a stale
    tail and re-answer a conversation that is already ours.
    """
    payload = _request(
        key,
        f"/v1/inbox/conversations/{conv_id}/messages"
        f"?accountId={account_id}&limit={THREAD_FETCH_LIMIT}&sortOrder=desc",
    )
    msgs = payload.get("messages") or []
    if str(payload.get("sortOrderApplied") or "").lower() == "desc":
        msgs = list(reversed(msgs))
    return msgs


def _display_name(conv: dict, handle: str) -> str:
    return str(conv.get("participantName") or handle or "there")


def _print_reply(reply: str) -> None:
    """Indent the generated message so it reads as a quoted block in the log."""
    for line in (reply or "").splitlines() or [""]:
        print(f"      {line}")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Answer OASIS Instagram DMs with the conversational brain.",
    )
    p.add_argument("--live", action="store_true", help="actually send replies")
    p.add_argument("--only-handle",
                   help="scope the entire run to this handle (first live test)")
    p.add_argument("--limit", type=int, default=DEFAULT_SCAN_LIMIT,
                   help=f"max conversations to examine (default {DEFAULT_SCAN_LIMIT})")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--book", "--allow-booking", dest="book", action="store_true",
        help="permit the closer to create a REAL calendar event and mail the "
             "prospect a Google invite. Default OFF: without it, a booking "
             "request is handed to CC instead.",
    )
    p.add_argument("--max-model-calls", type=int, default=MAX_MODEL_CALLS_PER_RUN,
                   help=f"model turns per run (default {MAX_MODEL_CALLS_PER_RUN})")
    args = p.parse_args()

    if args.book and not args.live:
        # An explicit error, never a silent downgrade: an operator who typed
        # --book and got a dry run would reasonably believe booking is armed.
        p.error("--book requires --live (booking creates a real calendar event "
                "and emails a real person)")
    if args.max_model_calls < 0:
        p.error("--max-model-calls cannot be negative")

    # A dry run sends nothing, so it neither takes the lock nor waits on one.
    if not args.live:
        return _poll(args)
    with _RunLock(LOCK_PATH):
        return _poll(args)


def _stamp_watermark(*, state, db, conv, delta, handle, live, summary) -> None:
    """Stamp the examined-watermark ONLY on a conclusion.

    See ig_dm_state.mark_examined: a deferral ("out of model budget", "deadline",
    "model failed", "starved by the fair queue") must leave the watermark alone
    so the next tick comes back to this person. Stamping a deferral is how a
    prospect gets abandoned mid-conversation and nobody finds out until they give
    up.

    `live` gates the stamp for the same reason it gates handoffs: a dry run that
    writes a watermark would make the LIVE daemon skip that thread, so previewing
    the inbox would silence real prospects. A preview with persistent effects is
    not a preview.
    """
    if not (live and _is_conclusive(delta) and delta.get("_row_id")):
        return
    try:
        state.mark_examined(
            db, str(delta["_row_id"]),
            provider_updated_time=str(conv.get("updatedTime") or ""),
        )
    except Exception as exc:  # noqa: BLE001 — never lose a poll to bookkeeping
        summary["errors"] += 1
        print(f"  [error] @{handle}: watermark not stamped: {exc}", file=sys.stderr)


def _merge_delta(summary: dict, delta: dict) -> None:
    """Fold a per-conversation delta into the run summary.

    Only counters the summary already declares are added, so `_row_id` (a str)
    and `stop_run` (a bool the summary has no slot for) cannot leak into the
    operator-visible line.
    """
    for k, v in delta.items():
        if isinstance(v, bool):
            continue
        if isinstance(summary.get(k), int) and isinstance(v, int):
            summary[k] += v


def _accumulate(target: dict, delta: dict) -> None:
    """Fold one delta into another: integers add, everything else is set.

    Distinct from _merge_delta because a delta starts nearly EMPTY — a key the
    target has never seen must be carried across, not dropped. Getting that
    wrong would silently lose `replied` on its way to the watermark decision.
    """
    for k, v in delta.items():
        if (isinstance(v, int) and not isinstance(v, bool)
                and isinstance(target.get(k), int)):
            target[k] += v
        else:
            target[k] = v


def _poll(args) -> int:
    brain = _sibling("ig_conversation_brain")
    state = _sibling("ig_dm_state")
    closer = _sibling("ig_closer") if args.book else None

    from email_playbook import detect_red_flags  # type: ignore

    key = _api_key()
    db = state.get_db_handle()
    deadline = time.monotonic() + RUN_DEADLINE_SECONDS
    # Pass 1 must not eat the clock pass 2 needs. See SCAN_RESERVE_SECONDS.
    scan_deadline = deadline - SCAN_RESERVE_SECONDS

    summary = {
        "scanned": 0, "in_scope": 0, "model_calls": 0, "replied": 0,
        "needed_reply": 0, "starved": 0, "oldest_wait_s": 0,
        "leads_created": 0, "bookings_attempted": 0, "bookings_applied": 0,
        "handoffs": 0, "skipped_paused": 0, "skipped_our_turn": 0,
        "skipped_no_messages": 0, "skipped_seen": 0, "skipped_unchanged": 0,
        "skipped_budget": 0, "skipped_red_flag": 0,
        "failures_model": 0, "failures_guardrail": 0, "budget_exhausted": 0,
        "errors": 0, "live": bool(args.live), "book_armed": bool(args.book),
    }

    convos = _request(key, "/v1/inbox/conversations").get("data") or []
    mode = " — LIVE" if args.live else " — DRY RUN"
    if args.book:
        mode += " + BOOKING ARMED"
    print(f"{len(convos)} conversation(s) in the Zernio inbox{mode}")

    # ══ PASS 1 ══ every in-scope conversation, every zero-model gate ═════════
    # No budget can cut this short — only the scan deadline, and that is a
    # degraded-Zernio backstop, not a normal exit. The red-flag handoff and the
    # already-seen bookkeeping cost nothing but a thread GET, so rationing them
    # behind the model budget bought nothing and lost opt-outs.
    candidates: list[_Candidate] = []
    for conv in convos[: args.limit]:
        summary["scanned"] += 1
        if conv.get("platform") != TARGET_PLATFORM:
            continue
        if (conv.get("accountUsername") or "").lower() != TARGET_ACCOUNT:
            continue

        handle = str(conv.get("participantUsername") or conv.get("participantId") or "?")
        # --only-handle scopes the SCAN, not just the send. The contract places
        # the send-gate check after the model call so a held handle still shows
        # what it would say; on a 50-conversation inbox that burns the entire
        # 12-call budget on people the run is forbidden to answer, and CC's own
        # first live test never gets reached. Skipping here is strictly safer
        # (fewer effects, fewer model calls) and the post-decision gate below
        # stays in place as defence in depth.
        if args.only_handle and handle.lower() != args.only_handle.lower():
            continue
        summary["in_scope"] += 1

        conv_id = str(conv.get("id") or "")
        account_id = str(conv.get("accountId") or "")

        try:
            delta, candidate = _screen_conversation(
                conv=conv, conv_id=conv_id, account_id=account_id, handle=handle,
                key=key, db=db, brain=brain, state=state,
                detect_red_flags=detect_red_flags, args=args,
                deadline=scan_deadline,
            )
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — one bad thread must not stop the poll
            summary["errors"] += 1
            traceback.print_exc()
            print(f"  [error] @{handle}: {exc}", file=sys.stderr)
            continue

        if candidate is not None:
            # The delta object is SHARED with the candidate so pass 2 can add its
            # outcome to the same record the watermark decision reads.
            candidates.append(candidate)
            continue

        _stamp_watermark(state=state, db=db, conv=conv, delta=delta, handle=handle,
                         live=bool(args.live), summary=summary)
        _merge_delta(summary, delta)
        if delta.get("stop_run"):
            # Only the scan deadline reaches here now. Everyone below is unread
            # this tick; the watermark was not stamped for any of them, so the
            # next tick starts from the same place rather than skipping them.
            break

    # ══ PASS 2 ══ the fair queue: oldest unanswered inbound first ════════════
    # Sorted HERE, from the prospect's own message timestamp, so the order does
    # not depend on what Zernio happened to return first. Ties break on
    # conversation id to keep the queue deterministic.
    candidates.sort(key=lambda c: (c.waiting_since, c.conv_id))
    summary["needed_reply"] = len(candidates)
    if candidates:
        print(f"  fair queue ({len(candidates)} waiting, oldest first): "
              + ", ".join(f"@{c.handle}({int(c.waited_seconds)}s)"
                          for c in candidates[:10]))

    starved: list[_Candidate] = []
    for cand in candidates:
        out_of_calls = summary["model_calls"] >= args.max_model_calls
        out_of_time = time.monotonic() > deadline
        if out_of_calls or out_of_time:
            # NOT an error and NOT a conclusion: this person is still waiting and
            # must be picked up next tick, at the FRONT of the queue, because
            # their wait only grows. `starved` is in _DEFERRAL_KEYS so the
            # watermark stays unstamped.
            cand.delta["starved"] = cand.delta.get("starved", 0) + 1
            starved.append(cand)
            _merge_delta(summary, cand.delta)
            continue

        try:
            answer = _answer_conversation(
                candidate=cand, key=key, db=db, brain=brain, state=state,
                closer=closer, args=args, deadline=deadline,
            )
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — one bad thread must not stop the poll
            summary["errors"] += 1
            traceback.print_exc()
            print(f"  [error] @{cand.handle}: {exc}", file=sys.stderr)
            continue

        _accumulate(cand.delta, answer)
        _stamp_watermark(state=state, db=db, conv=cand.conv, delta=cand.delta,
                         handle=cand.handle, live=bool(args.live), summary=summary)
        _merge_delta(summary, cand.delta)

    # The starvation surface. Before this line a prospect who needed a reply and
    # did not get one produced NO counter anywhere: the budget gate broke the
    # scan before they were reached, so they were not even a skip. `needed` is
    # the denominator that makes `replied` mean something.
    #
    # "got a model turn" is counted from model_calls, NOT from
    # len(candidates) - len(starved). A candidate can reach pass 2 and still be
    # refused at the re-checked reply budget, and reporting that as "answered"
    # would put the most misleading possible number on the one line an operator
    # reads — the same class of defect as the counters this whole surface exists
    # to expose.
    if candidates:
        oldest = max((c.waited_seconds for c in starved), default=0.0)
        summary["oldest_wait_s"] = int(oldest)
        print(f"  needed a reply: {len(candidates)}  "
              f"got a model turn: {summary['model_calls']}  "
              f"replied: {summary['replied']}  "
              f"no turn spent: {len(candidates) - summary['model_calls']}"
              + (f"  (oldest starved wait {int(oldest)}s)" if starved else ""))

    # Threads Zernio will not hand over are REAL prospects going unanswered, not
    # a quiet inbox: the conversation record still carries their inbound text and
    # the messages endpoint returns []. One alert per RUN and not one per thread —
    # 22 Telegrams is how an operator learns to mute the channel — and notify()'s
    # own dedup collapses the repeat to one an hour after that.
    if summary["skipped_no_messages"]:
        _notify(
            f"Instagram DMs unreadable: {summary['skipped_no_messages']} of "
            f"{summary['in_scope']} threads returned no messages from Zernio while "
            f"their conversation record still shows inbound text. Those people are "
            f"not being answered. Check the inbox by hand.",
            conv_id="run", event="no_messages", live=bool(args.live),
        )

    print()
    # ONE LINE, deliberately — do not "improve" this with indent=2.
    # (2026-08-29: scheduler.summarize_stdout replaced the 200-char slice this
    # was shaped around. The abbreviation below is no longer forced, but it is
    # still the most readable thing to put in a log line, so it stays.)
    # scheduler.py records `out[-1][:200]` as cron_jobs.last_result, i.e. the LAST
    # LINE of stdout. See _summary_line: the line is abbreviated and
    # failure-ordered so the counters that matter survive that 200-char cap, and
    # prefixed ERROR: when the run genuinely failed so the fleet watchdog can see
    # it. The full picture stays in the human-readable lines above.
    print(_summary_line(summary, as_json=bool(args.json)))
    return 0


def _flag_terminal_ending(*, state, db, row_id, handle, conv_id, new_stage,
                          previous_stage, live, action, bump) -> None:
    """A conversation that just ENDED without asking for a human still needs one.

    Nothing pairs a terminal stage with the handoff action. parse_decision only
    coerces action=handoff -> stage=handed_off, never the reverse, and
    validate_reply has no stage/action consistency check — so the model can
    legally return action='reply' with stage='disqualified', send a polite
    sign-off, and end the relationship. record_outbound (and set_stage on the
    hold branch) then writes automation_paused=1 for any terminal stage, but the
    poller only notified when action == 'handoff': handoff_pending stayed 0, the
    row never appeared in `ig_dm_state.py list --handoffs`, and nothing outside
    these four modules reads that column. A real prospect was written off in
    silence, discoverable only by running `list --stage disqualified` by hand.

    The stage is NOT rewritten. 'disqualified' is the model's finding and the
    only record of why; request_handoff would overwrite it with 'handed_off'.
    flag_for_review raises the queue flag and leaves the finding alone.
    """
    if new_stage not in TERMINAL_STAGES or previous_stage == new_stage:
        return
    reason = f"conversation ended at stage {new_stage} by a model {action}"
    if live:
        state.flag_for_review(db, row_id, reason=reason)
    else:
        print(f"  [dry-run] WOULD FLAG FOR REVIEW: {reason}")
    bump("handoffs")
    _notify(
        f"Instagram conversation closed: @{_notify_safe(handle, 64)} moved "
        f"{_notify_safe(previous_stage, 32)} -> {_notify_safe(new_stage, 32)} on a "
        f"model {action}, so the automation is now paused on it. Nobody asked for "
        f"a handoff; if that call was wrong it needs you. Conversation {conv_id}.",
        conv_id=conv_id, event=f"closed:{new_stage}", live=live,
    )


@dataclass
class _Candidate:
    """A conversation that has passed every zero-cost gate and wants a model call.

    Carries the work pass 1 already paid for — the state row, the attributed
    transcript, the newest inbound turn — so pass 2 spends nothing but the model
    call itself. `delta` is the SAME dict object pass 1 built, so whatever pass 2
    records lands on the record the watermark decision reads.
    """

    conv: dict
    conv_id: str
    account_id: str
    handle: str
    row: dict
    row_id: str
    stage: str
    turns: Any
    # How many turns fell off the front of the window. Computed in pass 1 with
    # the transcript and carried here rather than recomputed, because it is what
    # tells the model that LEAD MEMORY is its only view of the opening.
    dropped_turns: int
    newest_inbound: Any
    # When the prospect's unanswered message landed. THE sort key.
    waiting_since: datetime
    waited_seconds: float
    delta: dict = field(default_factory=dict)


def _waiting_since(*, newest_inbound, conv, now: datetime) -> datetime:
    """When did THIS prospect's still-unanswered message arrive?

    Their own message stamp, NOT the conversation's `updatedTime`. updatedTime
    tracks the newest message in either direction, so our reply to someone else's
    thread moves that thread and ordering by it is LIFO. The inbound turn's
    createdAt is frozen at the moment they typed, which is exactly the clock a
    fair queue has to run on.

    Unknown or unparseable falls back to the conversation stamp and then to
    `now`, which sorts LAST: a wait we cannot prove must never jump ahead of one
    we can. A stamp in the FUTURE (clock skew on either side) also sorts late for
    the same reason — it is not clamped forward, because clamping it to `now`
    would hand a skewed thread the front of the queue.
    """
    stamp = _parse_iso(getattr(newest_inbound, "created_at", None))
    if stamp is None:
        stamp = _parse_iso(conv.get("updatedTime"))
    return stamp if stamp is not None else now


def _handoff(*, state, db, row_id, handle, conv_id, reason, notify_reason,
             stage_, live, bump, event: str = "handoff") -> None:
    """Flag a human. In a dry run this is a print and nothing else.

    request_handoff sets stage=handed_off + handoff_pending + automation_paused,
    which is TERMINAL and only reversible with `ig_dm_state.py resume`. A
    preview run that permanently disables the automation on a real prospect —
    and pages CC while doing it — is not a preview. Every fragment that
    reaches the Telegram body goes through _notify_safe first.

    Module-level rather than a closure because BOTH halves of the split run it:
    the red-flag gate in pass 1 and the model's own handoff request in pass 2.
    Two spellings of the same act is how one of them ended up mutating a real
    conversation from a preview run.
    """
    if live:
        state.request_handoff(db, row_id, reason=reason)
    else:
        print(f"  [dry-run] WOULD HAND OFF (stage -> handed_off, automation "
              f"paused): {reason}")
    bump("handoffs")
    _notify(
        f"Handoff: @{_notify_safe(handle, 64)} needs you. "
        f"Reason: {_notify_safe(notify_reason)}. "
        f"Stage: {_notify_safe(stage_, 32)}. Conversation {conv_id}.",
        conv_id=conv_id, event=event, live=live,
    )


def _budget_gate(*, state, db, row, row_id, handle, live, bump, dry) -> Optional[str]:
    """The reply budget. None when a reply is allowed, else the refusal reason.

    Extracted so it can run TWICE: once in pass 1, where a refusal keeps the
    conversation out of the fair queue entirely (requirement: a conversation that
    cannot be answered must not consume a slot in the ordering), and once in
    pass 2 immediately before the model call. The second check is not
    ceremonial — the fair queue can hold a candidate for a whole model turn, and
    DAILY_REPLY_CAP_GLOBAL is a tenant-wide sum with no per-conversation
    reservation, so a reply we sent to someone else in this very tick can be what
    exhausts it.
    """
    allowed, why = state.reply_budget(db, row)
    if allowed:
        return None
    bump("skipped_budget")
    print(f"  @{handle}: reply budget says no ({why}) — skipping")
    # The per-conversation refusals self-clear: `gap` is 45 seconds and
    # `conv_cap` is 30 replies to ONE person in a day. Paging on those trains
    # the operator to ignore the channel.
    #
    # `global_cap` is a different animal. It is ONE tenant-wide number summed
    # across every conversation, checked before the model call with no
    # per-conversation reservation, so exhausting it silences EVERY live
    # conversation at once until UTC midnight — mid-deal, with nothing sent
    # and no state change. That refusal reached nobody: one stdout line the
    # scheduler truncates away. It is an incident, so it is alerted and it is
    # written to the row an operator actually reads.
    if why == "global_cap":
        if live:
            state.note(
                db, row_id,
                note=(f"reply refused: tenant-wide daily cap "
                      f"({state.DAILY_REPLY_CAP_GLOBAL}) reached; every "
                      f"conversation is silenced until UTC midnight"),
            )
        else:
            dry("RECORD a tenant-wide cap refusal")
        _notify(
            f"Instagram DMs stopped: the tenant-wide daily reply cap "
            f"({state.DAILY_REPLY_CAP_GLOBAL}) is exhausted, so every live "
            f"conversation is getting silence until UTC midnight. "
            f"@{_notify_safe(handle, 64)} was refused mid-thread.",
            conv_id="tenant", event="global_cap", live=live,
        )
    return why


def _handle_conversation(*, conv, conv_id, account_id, handle, key, db, brain,
                         state, closer, detect_red_flags, args, deadline,
                         model_calls_spent) -> dict:
    """One conversation, screened and — if the budget allows — answered.

    The two halves run separately in `_poll` (screen EVERYONE, then answer the
    fair-ordered head). This is the single-conversation composition of them, kept
    because the gate ORDER is the contract: every cheap gate before a model call
    is spent, and the budget checked before the call rather than after.
    """
    delta, candidate = _screen_conversation(
        conv=conv, conv_id=conv_id, account_id=account_id, handle=handle,
        key=key, db=db, brain=brain, state=state,
        detect_red_flags=detect_red_flags, args=args, deadline=deadline,
    )
    if candidate is None:
        return delta

    # ── 9. run budgets, checked BEFORE the call, not after ──────────────────
    if model_calls_spent >= args.max_model_calls:
        delta["budget_exhausted"] = 1
        delta["starved"] = 1
        delta["stop_run"] = True
        print(f"  @{handle}: model-call budget spent "
              f"({model_calls_spent}/{args.max_model_calls}) — stopping this run")
        return delta
    if time.monotonic() > deadline:
        delta["budget_exhausted"] = 1
        delta["starved"] = 1
        delta["stop_run"] = True
        print(f"  @{handle}: run deadline reached ({RUN_DEADLINE_SECONDS}s) — stopping")
        return delta

    _accumulate(delta, _answer_conversation(
        candidate=candidate, key=key, db=db, brain=brain, state=state,
        closer=closer, args=args, deadline=deadline,
    ))
    return delta


def _screen_conversation(*, conv, conv_id, account_id, handle, key, db, brain,
                         state, detect_red_flags, args, deadline
                         ) -> tuple[dict, Optional[_Candidate]]:
    """The ZERO-MODEL half. Returns (summary delta, candidate or None).

    A candidate is a conversation with a fresh inbound message that is allowed a
    reply right now and is waiting on nothing but a model call.

    THIS RUNS FOR EVERY IN-SCOPE CONVERSATION. Before 2026-08-21 the model-call
    budget `break`-ed the whole scan, so an opt-out sitting below two chatty
    threads was never read: no red-flag handoff, no seen bookkeeping, no counter,
    no trace. Rationing free work bought nothing and lost the one message class
    that must never be missed.
    """
    delta: dict[str, Any] = {}
    live = bool(args.live)

    def bump(name: str, n: int = 1) -> None:
        delta[name] = delta.get(name, 0) + n

    def dry(what: str) -> None:
        print(f"  [dry-run] WOULD {what}")

    # ── 0. the SCAN deadline, BEFORE any network or database work ───────────
    # Checked here rather than at step 9 because step 3's thread GET is the
    # expensive part of a degraded run: urllib timeout=30, up to --limit times,
    # which overruns the scheduler's own 600s kill long before step 9 is reached.
    # `deadline` here is the SCAN deadline, held back from the run deadline by
    # SCAN_RESERVE_SECONDS so pass 2 can still afford a model turn.
    if time.monotonic() > deadline:
        delta["budget_exhausted"] = 1
        delta["stop_run"] = True
        print(f"  @{handle}: scan deadline reached — stopping the scan")
        return delta, None

    # ── 1. state row (created on turn 1, long before a CRM lead exists) ──────
    row = state.get_or_create(db, conv=conv)
    row_id = str(row["id"])
    stage = str(row["stage"])
    # Handed back so the caller can stamp the examined-watermark in ONE place
    # keyed off the outcome, rather than at each of this function's many exits —
    # where the next `return delta` added would silently forget to.
    delta["_row_id"] = row_id

    # ── 2. paused? terminal stages set automation_paused, so this is the one
    #      check that covers booked / handed_off / disqualified as well. ──────
    if int(row.get("automation_paused") or 0):
        bump("skipped_paused")
        print(f"  @{handle}: paused (stage={stage}) — skipping")
        return delta, None

    # ── 2b. cheap pre-filter: has the thread moved since we last LOOKED? ─────
    # Saves the per-conversation messages GET on a quiet inbox.
    #
    # This used to compare `updatedTime` against `last_outbound_at` only, which
    # meant it engaged solely for threads we had already answered. Every thread
    # we had never replied to had last_outbound_at = NULL and was therefore
    # re-fetched on EVERY tick, forever. Live on 2026-08-21: 47 of 50 threads,
    # ~1.2s per GET, deadline hit at conversation 25 — half the inbox unread on
    # every run, which is the whole problem under a mass influx.
    #
    # The watermark (migration bravo__011) is stamped after a thread reaches a
    # conclusion, whether or not we spoke. Unchanged since then → nothing new to
    # answer → skip without any HTTP. Unparseable stamps fall through to the real
    # check rather than skipping, so a bad timestamp costs a fetch, not a
    # prospect.
    updated = _parse_iso(conv.get("updatedTime"))
    seen_at = _parse_iso(row.get("provider_updated_time"))
    if updated and seen_at and updated <= seen_at:
        bump("skipped_unchanged")
        return delta, None

    # Kept as defence in depth: even on the first pass after this migration,
    # a thread whose newest event is our own reply is not ours to answer.
    last_out = _parse_iso(row.get("last_outbound_at"))
    if updated and last_out and updated <= last_out:
        bump("skipped_our_turn")
        return delta, None

    # ── 3. fetch the FULL thread (newest window, oldest-first) ──────────────
    msgs = _fetch_thread(key, conv_id, account_id)
    if not msgs:
        # Zernio answers `status: success, hasMore: false, messages: []` for a
        # number of live threads whose conversation record still advertises a
        # lastMessage — 10 of the freshest 12 on this account. There is nothing
        # to read and nothing to answer, but it is NOT the same fact as "the last
        # word was ours", and folding the two into one counter would report that
        # the bot had already replied to ten people it has never spoken to.
        bump("skipped_no_messages")
        return delta, None

    # ── 4. attribute turns by `direction`, never by senderId vs accountId ────
    # The dropped count is kept, not discarded: it is what tells the model that
    # the recap in LEAD MEMORY is its only view of the opening of this thread.
    turns, dropped_turns = brain.transcript_window(
        msgs, participant_id=str(row["participant_id"]))

    # ── 5. is it even our turn? THE self-reply-loop fix. ─────────────────────
    if not brain.needs_reply(turns):
        bump("skipped_our_turn")
        return delta, None

    newest_inbound = brain.latest_inbound(turns)
    if newest_inbound is None:  # needs_reply() already proved otherwise
        bump("skipped_our_turn")
        return delta, None

    # ── 6. already answered this exact message? ──────────────────────────────
    if (newest_inbound.message_id
            and newest_inbound.message_id == str(row.get("last_processed_message_id") or "")):
        bump("skipped_seen")
        return delta, None

    # ── 7. red flags: a human takes these, always ────────────────────────────
    # THIS IS WHY THE SCAN IS NO LONGER RATIONED. An opt-out costs zero model
    # calls to honour, and under the old interleaved walk it was simply never
    # reached once two chattier threads above it had spent the budget.
    flags = detect_red_flags("", newest_inbound.text)
    blocking = [f for f in flags if f in HANDOFF_RED_FLAGS]
    if blocking:
        reason = f"red flag: {', '.join(blocking)}"
        _handoff(state=state, db=db, row_id=row_id, handle=handle, conv_id=conv_id,
                 reason=reason, notify_reason=reason, stage_=stage, live=live,
                 bump=bump,
                 event="opt_out" if "opt_out" in blocking else "handoff")
        bump("skipped_red_flag")
        print(f"  @{handle}: {reason} — handed to CC, nothing sent")
        return delta, None

    # ── 8. reply budget (SQL-side; fails CLOSED on an unreadable timestamp) ──
    # Checked HERE, before the fair queue is built, so that a conversation which
    # cannot be answered — paused, terminal, inside MIN_REPLY_GAP_SECONDS, over
    # either daily cap — never takes a slot in the ordering from someone who can.
    if _budget_gate(state=state, db=db, row=row, row_id=row_id, handle=handle,
                    live=live, bump=bump, dry=dry) is not None:
        return delta, None

    # ── 8b. the queue position: how long has THIS prospect been waiting? ─────
    now = _now()
    waiting_since = _waiting_since(newest_inbound=newest_inbound, conv=conv, now=now)
    return delta, _Candidate(
        conv=conv, conv_id=conv_id, account_id=account_id, handle=handle,
        row=row, row_id=row_id, stage=stage, turns=turns,
        dropped_turns=dropped_turns, newest_inbound=newest_inbound,
        waiting_since=waiting_since,
        # Clamped at zero for REPORTING only; the sort runs on the raw stamp, so
        # a future-dated message still sorts late instead of jumping the queue.
        waited_seconds=max(0.0, (now - waiting_since).total_seconds()),
        delta=delta,
    )


def _answer_conversation(*, candidate: _Candidate, key, db, brain, state, closer,
                         args, deadline) -> dict:
    """Spend ONE model turn on a candidate the fair queue chose, and act on it.

    Everything this needs was already paid for in pass 1 — the state row, the
    transcript, the newest inbound turn — so nothing here re-reads Zernio before
    the model call.
    """
    delta: dict[str, Any] = {"_row_id": candidate.row_id}
    live = bool(args.live)
    conv = candidate.conv
    conv_id = candidate.conv_id
    handle = candidate.handle
    account_id = candidate.account_id
    row = candidate.row
    row_id = candidate.row_id
    stage = candidate.stage
    turns = candidate.turns
    dropped_turns = candidate.dropped_turns
    newest_inbound = candidate.newest_inbound

    def bump(name: str, n: int = 1) -> None:
        delta[name] = delta.get(name, 0) + n

    def dry(what: str) -> None:
        print(f"  [dry-run] WOULD {what}")

    def handoff(row_id_: str, *, reason: str, notify_reason: str, stage_: str,
                event: str = "handoff") -> None:
        _handoff(state=state, db=db, row_id=row_id_, handle=handle, conv_id=conv_id,
                 reason=reason, notify_reason=notify_reason, stage_=stage_,
                 live=live, bump=bump, event=event)

    # ── 8 (again). The fair queue can hold a candidate for a whole model turn,
    #     and DAILY_REPLY_CAP_GLOBAL is a tenant-wide sum: the reply we just sent
    #     to someone else in THIS tick can be the one that exhausts it. Re-check
    #     immediately before spending, not only at screening time. ────────────
    if _budget_gate(state=state, db=db, row=row, row_id=row_id, handle=handle,
                    live=live, bump=bump, dry=dry) is not None:
        return delta

    # ── 10. the model turn ───────────────────────────────────────────────────
    replies_today = int(row.get("replies_today") or 0)
    if str(row.get("replies_today_date") or "") != _now().strftime("%Y-%m-%d"):
        replies_today = 0
    carried = brain.Extracted(
        name=row.get("extracted_name"), email=row.get("extracted_email"),
        phone=row.get("extracted_phone"), business=row.get("extracted_business"),
        need=row.get("extracted_need"), timeline=row.get("extracted_timeline"),
    )
    # What we know about how to sell THIS person: budget signals, what they have
    # objected to, what we already pitched, and the recap of the turns that have
    # scrolled out of the window above. Without it a prospect who comes back
    # after a week is re-qualified from zero.
    carried_memory = brain.LeadMemory.from_row(row)
    # The timeout is derived from what is LEFT of the run, not left on the
    # brain's 90s default: decide() may spend two subprocesses, so an unbounded
    # default made the true worst case 55 + 2x90 = 235s against a 60-second tick.
    model_timeout = int(max(
        MODEL_TIMEOUT_FLOOR_SECONDS,
        min(MODEL_TIMEOUT_CEILING_SECONDS, deadline - time.monotonic()),
    ))
    decision = brain.decide(
        turns,
        current_stage=stage,
        participant_display_name=_display_name(conv, handle),
        extracted_so_far=carried,
        memory_so_far=carried_memory,
        dropped_turns=dropped_turns,
        replies_left_today=max(
            0, state.DAILY_REPLY_CAP_PER_CONVERSATION - replies_today),
        timeout=model_timeout,
    )
    bump("model_calls")

    # ── 11. a failure is counted and logged, NEVER papered over with a
    #        template. Nothing is sent and the message stays unconsumed so the
    #        next run retries it. ─────────────────────────────────────────────
    if not decision.ok:
        # Gated on --live like every other write. record_failure ESCALATES: the
        # second consecutive guardrail reject sets stage='handed_off',
        # handoff_pending=1 and automation_paused=1, which is terminal and only
        # reversible by hand. Two preview runs must not be able to retire a live
        # lead — least of all while _notify() is deliberately suppressed.
        if live:
            after = state.record_failure(
                db, row_id, kind=str(decision.failure),
                detail=str(decision.failure_detail or ""),
            )
        else:
            dry(f"COUNT A FAILURE ({decision.failure}) against this conversation")
            after = dict(row)
        if decision.failure == "model_unavailable":
            bump("failures_model")
        elif decision.failure != "empty_transcript":
            bump("failures_guardrail")
        print(f"  @{handle}: model turn FAILED ({decision.failure}) — nothing sent",
              file=sys.stderr)
        if decision.violations:
            print(f"      violations: {list(decision.violations)}", file=sys.stderr)
        if int(after.get("handoff_pending") or 0) and not int(row.get("handoff_pending") or 0):
            bump("handoffs")
            _notify(
                f"Handoff: @{handle} needs you. Reason: "
                f"{after.get('handoff_reason') or 'repeated automation failures'}. "
                f"Stage: {after.get('stage')}. Conversation {conv_id}.",
                conv_id=conv_id, event="handoff",
                            live=args.live,
            )
        if decision.failure == "empty_transcript" and live:
            state.record_inbound(
                db, row_id, message_id=newest_inbound.message_id,
                at_iso=newest_inbound.created_at or _iso(_now()),
            )
        return delta

    # ── 12. extraction: COALESCE in SQL, email first-write-wins ─────────────
    # Also gated: apply_extraction writes with coalesce (permanently, for the
    # life of the conversation) and raises its own terminal handoff when a
    # second, different address arrives.
    if live:
        # The rolling lead memory rides the same --live gate, and runs FIRST so
        # that apply_extraction stays the call whose returned row decides the
        # email_changed handoff below. Written before the send, like the
        # extraction: it is what the NEXT turn reads, and a send that fails must
        # still leave us knowing what this turn learned. Coalescing, so a turn
        # that learned nothing new erases nothing.
        state.apply_memory(db, row_id, memory=decision.memory)
        after = state.apply_extraction(
            db, row_id, extracted=decision.extracted,
            email_source_message_id=newest_inbound.message_id or None,
        )
    else:
        after = dict(row)
    if int(after.get("handoff_pending") or 0) and not int(row.get("handoff_pending") or 0):
        # The DAO raises the flag when a SECOND, different address arrives.
        bump("handoffs")
        _notify(
            f"Handoff: @{handle} needs you. Reason: "
            f"{after.get('handoff_reason') or 'email_changed'}. "
            f"Stage: {after.get('stage')}. Conversation {conv_id}.",
            conv_id=conv_id, event="handoff",
                    live=args.live,
        )
        print(f"  @{handle}: {after.get('handoff_reason')} — handed to CC, nothing sent")
        return delta
    row = after

    # ── 13. the model asked for a human ─────────────────────────────────────
    # Routed through the handoff() helper above, which is the copy that was
    # already correctly gated on --live. Two spellings of the same act is how one
    # of them ended up mutating a real conversation from a preview run.
    if decision.action == "handoff":
        reason = str(decision.handoff_reason or "model requested a handoff")
        handoff(row_id, reason=reason, notify_reason=reason, stage_="handed_off")
        print(f"  @{handle}: HANDOFF ({reason}) — nothing sent")
        return delta

    # ── 14. hold: the right answer is silence ───────────────────────────────
    if decision.action == "hold":
        if live:
            try:
                state.set_stage(db, row_id, stage=decision.stage, reason="model hold")
            except state.IllegalTransition as exc:
                print(f"  [warn] @{handle}: {exc}", file=sys.stderr)
        else:
            dry(f"MOVE THE STAGE {stage} -> {decision.stage}")
        # A hold onto a terminal stage ENDS the conversation: set_stage pauses
        # the automation for any terminal value. Silently, until this call.
        _flag_terminal_ending(
            state=state, db=db, row_id=row_id, handle=handle, conv_id=conv_id,
            new_stage=decision.stage, previous_stage=stage, live=live,
            action="hold", bump=bump,
        )
        # Consume the message even though nothing was sent. Without this the
        # hold decision is never recorded against the inbound id, so the same
        # DM is re-decided on EVERY poll — a fresh ~27s model call each tick,
        # forever, on a shared subscription quota. Silence is a decision about
        # that message; it has to be remembered like any other.
        # Still gated on --live: a dry run that consumes ids makes the next live
        # run skip the very DM it was meant to answer, which is what swallowed
        # CC's first real test.
        if args.live:
            state.record_inbound(
                db, row_id, message_id=newest_inbound.message_id,
                at_iso=newest_inbound.created_at or _iso(_now()),
            )
        print(f"  @{handle}: HOLD (stage={decision.stage}) — nothing sent")
        return delta

    reply = decision.reply or ""
    if not reply:
        # Unreachable per the brain's invariant 2; asserted rather than assumed
        # because sending an empty DM is worse than a loud stop.
        raise RuntimeError(
            f"brain returned action={decision.action!r} with an empty reply — "
            "invariant 2 violated"
        )

    # ── 15. send gate (defence in depth; the scan is already scoped) ─────────
    if args.only_handle and handle.lower() != args.only_handle.lower():
        print(f"  @{handle}: held (--only-handle {args.only_handle})")
        return delta

    # ── 16. a dry run must never consume a message id ───────────────────────
    if not args.live:
        print(f"  @{handle}: WOULD REPLY  stage {stage} -> {decision.stage}  "
              f"action={decision.action}  confidence={decision.confidence}")
        _print_reply(reply)
        if decision.extracted.as_dict() != carried.as_dict():
            fresh = {k: v for k, v in decision.extracted.as_dict().items() if v}
            if fresh:
                print(f"      extracted: {fresh}")
        if decision.memory.as_dict() != carried_memory.as_dict():
            learned = {k: v for k, v in decision.memory.as_dict().items() if v}
            if learned:
                print(f"      memory: {learned}")
        if decision.violations:
            print(f"      violations: {list(decision.violations)}")
        return delta

    # ── 17. send ─────────────────────────────────────────────────────────────
    # _request only raises on an HTTPError or an HTML body. Zernio's JSON is a
    # status envelope, so a 200 carrying {"status":"error"} — rate limit, expired
    # IG token, 24-hour messaging window closed, conversation archived — sails
    # through as success. Discarding this response meant recording the DM as
    # delivered, consuming the inbound id so it could never be retried, and
    # printing "REPLIED" while the prospect received nothing.
    send_resp = _request(
        key,
        f"/v1/inbox/conversations/{conv_id}/messages",
        method="POST",
        body={"accountId": account_id, "message": reply},
    )
    send_status = str((send_resp or {}).get("status", "")).strip().lower()
    if send_status in ("error", "failed", "failure"):
        bump("errors")
        detail = str(
            (send_resp or {}).get("error")
            or (send_resp or {}).get("message")
            or send_resp
        )[:300]
        print(f"  [error] @{handle}: Zernio accepted the request but reported "
              f"{send_status}: {detail}", file=sys.stderr)
        # Do NOT record_outbound and do NOT consume the inbound id: the reply did
        # not land, so the next poll must be free to try again. record_failure
        # counts it and escalates to a human once failures stack, so a persistent
        # send outage surfaces instead of retrying into silence forever.
        state.record_failure(
            db, row_id, kind="send_failed", detail=f"zernio:{send_status}: {detail}"
        )
        return delta

    # ── 18. persist the moment the reply is earned, not at the end of the run.
    #        Holding it in memory until a final save meant a run that outlasted
    #        the cron interval let the next run read pre-reply state and message
    #        the same person twice. record_outbound FIRST: it is what closes the
    #        double-send window. ──────────────────────────────────────────────
    row = state.record_outbound(db, row_id, decision=decision, message_sent=reply)
    state.record_inbound(
        db, row_id, message_id=newest_inbound.message_id,
        at_iso=newest_inbound.created_at or _iso(_now()),
    )
    bump("replied")
    print(f"  @{handle}: REPLIED (stage {stage} -> {decision.stage})")
    _print_reply(reply)

    # The DM went out and the conversation is over: record_outbound paused the
    # row for any terminal stage. Nobody has been told yet.
    _flag_terminal_ending(
        state=state, db=db, row_id=row_id, handle=handle, conv_id=conv_id,
        new_stage=str(decision.stage), previous_stage=stage, live=live,
        action="reply", bump=bump,
    )

    # ── 19. CRM projection. A failure here must never look like a send
    #        failure — the DM already went out. ─────────────────────────────
    try:
        status, lead_id = _upsert_lead(conv, newest_inbound.text, f"stage {decision.stage}")
        if status == "created":
            bump("leads_created")
            print(f"  @{handle}: lead created")
        if lead_id and not row.get("lead_id"):
            row = state.link_crm_lead(db, row_id, lead_id=lead_id)
    except Exception as exc:  # noqa: BLE001 — counted and traced, never swallowed
        bump("errors")
        traceback.print_exc()
        print(f"  [error] CRM lead for @{handle}: {exc}", file=sys.stderr)

    # ── 20. the close loop ───────────────────────────────────────────────────
    if decision.action == "book":
        _run_close(
            db=db, row=row, decision=decision, state=state, closer=closer,
            handle=handle, conv_id=conv_id, args=args, bump=bump,
        )
    return delta


def _run_close(*, db, row, decision, state, closer, handle, conv_id, args, bump) -> None:
    """Booking is armed only by --book. Without it the request becomes a handoff.

    The operator has not authorised autonomous booking of real meetings, and
    book(apply=True) mails a stranger a Google invite — the first irreversible
    outward effect in the whole pipeline.
    """
    if not args.book or closer is None:
        state.request_handoff(db, str(row["id"]), reason="book_requested_unarmed")
        bump("handoffs")
        _notify(
            f"Handoff: @{handle} needs you. Reason: ready to book, but the poller "
            f"is not armed for booking (--book off). Stage: {row.get('stage')}. "
            f"Conversation {conv_id}.",
            conv_id=conv_id, event="handoff",
                    live=args.live,
        )
        print(f"  @{handle}: ready to book — poller unarmed, handed to CC")
        return

    if not decision.extracted.email:
        state.request_handoff(db, str(row["id"]), reason="book_without_email")
        bump("handoffs")
        _notify(
            f"Handoff: @{handle} needs you. Reason: booking requested with no "
            f"verified email address. Stage: {row.get('stage')}. "
            f"Conversation {conv_id}.",
            conv_id=conv_id, event="handoff",
                    live=args.live,
        )
        print(f"  @{handle}: booking requested without an email — handed to CC")
        return

    bump("bookings_attempted")
    result = closer.close(db, row, extracted=decision.extracted, apply=True)
    if result.applied:
        bump("bookings_applied")
        print(f"  @{handle}: BOOKED {result.slot_label} "
              f"(email {result.email_status})")
    if not result.ok:
        bump("handoffs")
        # The DM promising the invite was sent at step 17, BEFORE this ran. A
        # failure here means the prospect has been told an invite is coming and
        # will not get one, so the row has to reach the queue a human reads.
        # close()'s own _fail() writes nothing to the database for any failure
        # before the claim — calendar_unverified and no_slots both land there —
        # so booking_status stayed 'none', automation_paused 0, handoff_pending 0
        # and the only signal was a Telegram that dedups into silence on repeat.
        # request_handoff is idempotent, so a row the closer already parked with
        # fail_booking is unharmed.
        try:
            state.request_handoff(
                db, str(row["id"]),
                reason=f"booking failed at {result.stage_of_failure}",
            )
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            traceback.print_exc()
            print(f"  [error] @{handle}: could not queue the failed booking for a "
                  f"human: {exc}", file=sys.stderr)
        print(f"  [error] @{handle}: booking failed at {result.stage_of_failure}: "
              f"{result.error}", file=sys.stderr)
        _notify(
            f"Booking failed: @{handle} at step {result.stage_of_failure}. "
            f"{result.error}. Conversation {conv_id}.",
            conv_id=conv_id, event="booking_failed",
                    live=args.live,
        )


if __name__ == "__main__":
    sys.exit(main())
