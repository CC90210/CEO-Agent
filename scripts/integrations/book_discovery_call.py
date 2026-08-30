#!/usr/bin/env python3
"""book_discovery_call.py — availability → Google Meet → pre-call brief.

The booking half of the OASIS AI intake funnel. A lead completes
/f/oasis-ai-cc/ai-audit, gets scored, and if they asked for a call this places
it in CC's calendar with a Meet link and writes him a one-page brief so he never
joins a call cold.

Three verbs, each usable alone:

    slots    free windows in CC's calendar inside working hours
    brief    the pre-call brief for a lead, from their funnel answers
    book     slots -> create the Meet event -> write the brief -> log the
             interaction. The whole path.

WHY NOT google_tool.py: it has calendar list/create/delete but no availability
verb, and no notion of working hours or buffers. `create --meet` is reused
verbatim rather than reimplemented — this wraps it, it does not replace it.

Times are CC's local timezone (America/Toronto) throughout. A booking engine
that reasons in UTC books 4am calls; that class of bug already cost a 04:00 ET
Pow Wow ping on a long weekend (see schedule_helpers.py).

Usage:
    python scripts/integrations/book_discovery_call.py slots --days 5 --json
    python scripts/integrations/book_discovery_call.py brief --lead-id <uuid>
    python scripts/integrations/book_discovery_call.py book --lead-id <uuid> \
        --start "2026-08-04T14:00" [--apply]
"""
from __future__ import annotations

CAPABILITY_META = {
    "category": "sales.booking",
    "lifecycle": "active",
    # external_write, not read_only: `book --apply` creates a calendar event AND
    # emails the attendee a Google invite — an outward effect on a real
    # prospect. `slots` and `brief` are read-only, but a module is classified by
    # its most dangerous path, not its safest.
    # (Valid values are destructive | external_write | local_write | read_only —
    # read from the graph validator, after an invented "mutating" was rejected.)
    "risk": "external_write",
    "triggers": [
        "book a discovery call", "check my availability", "free slots",
        "pre-call brief", "lead brief", "schedule a google meet",
    ],
    "owner": "bravo",
    "project": "oasis",
    # Deliberately hidden from the bridge tool surface: booking a call on CC's
    # calendar and inviting a prospect must go through operator intent, not a
    # chat turn. Run it from the CLI or a cron with an explicit --apply.
    "bridge": {"visible": False},
}

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402
from email_engine import load_env, get_supabase  # noqa: E402

# CC operates from Montreal QC (relocated 2026-07). Toronto == same offset and
# is the tz already used by schedule_helpers, so crons and bookings agree.
TZ = ZoneInfo("America/Toronto")

WORK_START_H = 9          # 09:00 local
WORK_END_H = 17           # last call ENDS by 17:00
CALL_MINUTES = 30
BUFFER_MINUTES = 15       # never butt a discovery call against another event
LEAD_TIME_HOURS = 12      # no same-morning bookings; CC needs to see the brief

BRIEF_DIR = PROJECT_ROOT / "memory" / "lead_briefs"

GOOGLE_TOOL = PROJECT_ROOT / "scripts" / "integrations" / "google_tool.py"

# google_tool.EXIT_EVENT_WITHOUT_MEET: the event EXISTS but has no Meet room.
# Distinct from 1 (nothing was created) because the recovery is different — a
# real event has to be cancelled, not simply retried.
EXIT_EVENT_WITHOUT_MEET = 3


# ── helpers ──────────────────────────────────────────────────────────────────

def _run(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(GOOGLE_TOOL), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, cwd=str(PROJECT_ROOT),
                       creationflags=WINDOWLESS_FLAGS)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _parse_iso_local(s: str) -> datetime:
    """Accept 'YYYY-MM-DDTHH:MM' (local) or a full ISO string with offset."""
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def _event_window(event: Any) -> Optional[tuple[datetime, datetime]]:
    """One Google event -> the (start, end) it occupies, local. None if unusable.

    A TIMED event blocks exactly its own window. An all-day entry (start.date,
    no dateTime) blocks the WHOLE day — the conservative reading, because
    offering a slot inside an unknown-duration event would double-book CC and a
    missed slot costs nothing.
    """
    if not isinstance(event, dict):
        return None
    start_raw = (event.get("start") or {}).get("dateTime")
    end_raw = (event.get("end") or {}).get("dateTime")
    if start_raw:
        try:
            start = _parse_iso_local(str(start_raw))
            end = (_parse_iso_local(str(end_raw)) if end_raw
                   else start + timedelta(minutes=CALL_MINUTES))
        except ValueError:
            return None
        return (start, end) if end > start else (start, start + timedelta(minutes=1))

    day_raw = (event.get("start") or {}).get("date")
    if not day_raw:
        return None
    try:
        day = datetime.fromisoformat(str(day_raw)).replace(tzinfo=TZ)
    except ValueError:
        return None
    return day.replace(hour=0, minute=0), day.replace(hour=23, minute=59)


def read_calendar(days: int) -> tuple[bool, list[tuple[datetime, datetime]]]:
    """(read_ok, busy windows). The read STATUS is the half that was missing.

    Two changes, both of which shipped as defects:

    1. TIMED EVENTS WERE INVISIBLE. This used to parse google_tool's human
       output with `\\s*(\\d{4}-\\d{2}-\\d{2})\\s+(.*)`, which requires
       whitespace after the date. google_tool prints
       `e['start']['dateTime']` first, i.e. `2026-08-25T14:00:00-04:00  Client
       call`, so the regex saw a `T` and hit `continue` for every real meeting.
       Only all-day entries ever matched. The clash check that free_slots() and
       ig_closer both depend on was therefore blind to exactly the events it
       exists to avoid. Reading `--json` removes the parser from the equation:
       the tool already hands back the raw events with real start AND end times.

    2. AN EMPTY LIST MEANT TWO OPPOSITE THINGS. `[]` was returned both for "the
       calendar was read and holds nothing" and for "the read FAILED", and
       ig_closer.verify_calendar_readable() then inferred readability from
       `bool(busy_windows(...))`. With timed events invisible, a fully booked
       week produced [] and the closer refused to book at all; with one all-day
       entry it "verified" a calendar it had not really read. The caller needs
       the status, so it is returned rather than inferred.
    """
    rc, out, err = _run(["calendar", "list", "--max", "80", "--json"])
    if rc != 0:
        print(f"[book] calendar read failed: {err[:200]}", file=sys.stderr)
        return False, []
    try:
        events = json.loads(out or "[]")
    except (ValueError, TypeError) as exc:
        print(f"[book] calendar output was not JSON ({exc}); treating the "
              f"calendar as UNREAD rather than empty", file=sys.stderr)
        return False, []
    if not isinstance(events, list):
        print("[book] calendar output was not a list of events; treating the "
              "calendar as UNREAD", file=sys.stderr)
        return False, []

    # `days` is a real filter, not decoration: `calendar list` returns whatever
    # is next on the calendar, which on a sparse calendar reaches months ahead.
    # Carrying those forward makes every clash check scan irrelevant windows.
    now = datetime.now(TZ)
    horizon = (now + timedelta(days=days + 1)).replace(hour=23, minute=59)

    busy: list[tuple[datetime, datetime]] = []
    for event in events:
        window = _event_window(event)
        if window is None:
            continue
        start, end = window
        if start > horizon or end < now - timedelta(days=1):
            continue
        busy.append((start, end))
    return True, busy


def busy_windows(days: int) -> list[tuple[datetime, datetime]]:
    """Existing events as (start, end) local. Falls back to 'no known events'
    rather than inventing availability if the calendar cannot be read.

    Callers that need to tell "no events" from "no read" must use
    read_calendar() — this shape cannot express the difference and never could.
    """
    return read_calendar(days)[1]


def free_slots(days: int = 5, limit: int = 12) -> list[dict[str, str]]:
    """Bookable 30-minute windows inside working hours, weekdays only."""
    busy = busy_windows(days)
    now = datetime.now(TZ)
    earliest = now + timedelta(hours=LEAD_TIME_HOURS)

    out: list[dict[str, str]] = []
    for d in range(days + 1):
        day = (now + timedelta(days=d)).replace(
            hour=WORK_START_H, minute=0, second=0, microsecond=0)
        if day.weekday() >= 5:           # Sat/Sun — CC does not take calls
            continue
        cursor = day
        end_of_day = day.replace(hour=WORK_END_H)
        while cursor + timedelta(minutes=CALL_MINUTES) <= end_of_day:
            slot_end = cursor + timedelta(minutes=CALL_MINUTES)
            if cursor < earliest:
                cursor += timedelta(minutes=CALL_MINUTES)
                continue
            pad = timedelta(minutes=BUFFER_MINUTES)
            clash = any(not (slot_end + pad <= b0 or cursor - pad >= b1)
                        for b0, b1 in busy)
            if not clash:
                out.append({
                    "start": cursor.isoformat(timespec="minutes"),
                    "end": slot_end.isoformat(timespec="minutes"),
                    "label": cursor.strftime("%a %d %b, %-I:%M %p")
                    if sys.platform != "win32"
                    else cursor.strftime("%a %d %b, %I:%M %p").replace(" 0", " "),
                })
                if len(out) >= limit:
                    return out
            cursor += timedelta(minutes=CALL_MINUTES)
    return out


# ── lead + brief ─────────────────────────────────────────────────────────────

def load_lead(db, lead_id: str) -> tuple[Optional[dict], Optional[dict]]:
    """Return (lead_row, latest ai-audit interaction metadata)."""
    lead = (db.table("leads").select("*").eq("id", lead_id).limit(1)
            .execute().data or [None])[0]
    inter = (db.table("lead_interactions")
             .select("metadata,created_at,content")
             .eq("lead_id", lead_id).eq("agent_source", "ai_audit_funnel")
             .order("created_at", desc=True).limit(1).execute().data or [])
    return lead, (inter[0] if inter else None)


LABELS = {
    "sales_leadgen": "Sales & lead gen", "customer_support": "Customer support",
    "workflow_automation": "Workflow automation", "agent_fleet": "Custom AI agent fleet",
    "pre_revenue": "Pre-revenue", "under_10k": "Under $10K/mo", "10k_50k": "$10K–$50K/mo",
    "50k_250k": "$50K–$250K/mo", "250k_plus": "$250K+/mo",
    "none_yet": "No budget set", "under_2k": "Under $2K/mo", "2k_5k": "$2K–$5K/mo",
    "5k_15k": "$5K–$15K/mo", "15k_plus": "$15K+/mo",
    "immediate": "Immediately", "30_days": "Next 30 days", "quarter": "This quarter",
    "exploring": "Just exploring",
    "never": "Never tried", "diy": "Built it themselves", "hired": "Hired someone — it failed",
    "tools": "Bought tools nobody uses",
    "solo": "Solo", "2_5": "2–5", "6_20": "6–20", "21_100": "21–100", "100_plus": "100+",
}


def _L(v: Any) -> str:
    return LABELS.get(v, str(v)) if v else "—"


def build_brief(lead: dict, meta: Optional[dict], when: Optional[str] = None) -> str:
    a = ((meta or {}).get("metadata") or {}).get("answers") or {}
    md = (meta or {}).get("metadata") or {}
    score = md.get("score")
    reasons = md.get("reasons") or []

    angle = {
        "agent_fleet": "They want the whole operation running itself — anchor on the OASIS fleet model, not a point tool.",
        "sales_leadgen": "Revenue-adjacent. Lead the ROI conversation with response-time-to-lead.",
        "customer_support": "Deflection maths: cost per ticket × volume. Easy to quantify on the call.",
        "workflow_automation": "The unglamorous middle. Ask what they re-type between two systems.",
    }.get(a.get("automation_goal"), "Goal unstated — open by asking what a bad week looks like.")

    warn = []
    if a.get("timeframe") == "exploring":
        warn.append("No timeline. Do not pitch scope — diagnose only.")
    if a.get("budget") == "none_yet":
        warn.append("No budget set. Establish cost-of-inaction before any number.")
    if a.get("tried_before") == "hired":
        warn.append("Burned by a previous vendor. Ask what specifically broke BEFORE proposing.")

    return f"""---
tags: [lead-brief, ai-audit, pre-call]
lead_id: {lead.get('id')}
generated: {datetime.now(TZ).isoformat(timespec='seconds')}
---

# Pre-call brief — {a.get('company') or lead.get('company') or 'Unknown company'}

**{lead.get('name') or a.get('name') or '—'}** · {lead.get('email') or a.get('email') or '—'}{' · ' + str(a.get('website')) if a.get('website') else ''}
Score **{score if score is not None else '—'}/100** · status **{lead.get('status') or '—'}**{' · call ' + when if when else ''}

## What they said

| | |
|---|---|
| Wants automated | {_L(a.get('automation_goal'))} |
| Revenue | {_L(a.get('monthly_revenue'))} |
| Team | {_L(a.get('team_size'))} |
| Budget | {_L(a.get('budget'))} |
| Timeline | {_L(a.get('timeframe'))} |
| Tried before | {_L(a.get('tried_before'))} |

**In their words:** {a.get('bottleneck_detail') or '(they did not elaborate — ask this first)'}

## Why they scored what they scored

{chr(10).join(f'- {r}' for r in reasons) or '- (no strong signals either way)'}

## Angle

{angle}

{chr(10).join(f'> WATCH: {w}' for w in warn)}

## Open with

Not "so tell me about your business". Open on the thing they typed:
*"You said {(a.get('bottleneck_detail') or 'follow-up is slipping')[:90]}… how long has that been going on?"*

Then stay on the problem until they quantify it. Price comes after the number they lose, never before.
"""


def write_brief(lead_id: str, body: str) -> Path:
    BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    p = BRIEF_DIR / f"{lead_id}.md"
    p.write_text(body, encoding="utf-8")
    return p


# ── book ─────────────────────────────────────────────────────────────────────

_MEET_LINE_RE = re.compile(r"^\s*Meet:\s*(\S+)\s*$", re.MULTILINE)
# google_tool prints "  Event-Id: <id>" on the per-event path (google_tool.py:552).
# Parsed rather than ignored so a booked meeting can be cancelled — see the note
# at the capture site. Only the per-event path prints it; the legacy static-room
# path does not, so a None here is expected under meet_scope="static".
_EVENT_ID_LINE_RE = re.compile(r"^\s*Event-Id:\s*(\S+)\s*$", re.MULTILINE)

# Google's requestId cap (google_tool.MEET_REQUEST_ID_MAX). Kept short and
# DERIVED, never random: Google treats requestId as the idempotency key, so a
# retried booking that reuses the key gets the room it already created instead of
# a second one.
_MEET_REQUEST_ID_MAX = 64


def meet_request_id(lead_id: str, start_iso: str) -> str:
    """Stable idempotency key for this lead's room at this start time."""
    digest = hashlib.sha256(f"{lead_id}|{start_iso}".encode()).hexdigest()
    return f"bdc-{digest[:40]}"


def book(db, lead_id: str, start_iso: str, apply: bool,
         meet_scope: str = "per_event") -> dict:
    lead, meta = load_lead(db, lead_id)
    if not lead:
        return {"ok": False, "error": f"lead {lead_id} not found"}

    start = _parse_iso_local(start_iso)
    end = start + timedelta(minutes=CALL_MINUTES)
    company = (((meta or {}).get("metadata") or {}).get("answers") or {}).get("company") \
        or lead.get("company") or lead.get("name") or "OASIS lead"
    title = f"OASIS AI — discovery call: {company}"
    when = start.strftime("%a %d %b %Y, %I:%M %p").replace(" 0", " ")

    brief_body = build_brief(lead, meta, when=when)
    result: dict[str, Any] = {"ok": True, "lead_id": lead_id, "title": title,
                              "start": start.isoformat(timespec="minutes"),
                              "end": end.isoformat(timespec="minutes"),
                              "applied": False}

    if not apply:
        result["dry_run"] = True
        result["brief_preview"] = brief_body[:400]
        return result

    brief_path = write_brief(lead_id, brief_body)
    result["brief"] = str(brief_path.relative_to(PROJECT_ROOT))

    # THE ROOM. `--meet` fills conferenceData from the single static
    # GOOGLE_MEET_LINK in the agents env — ONE url pasted onto every event this
    # repo has ever created. Two prospects booked an hour apart get the same
    # room, and either can walk into the other's call (or a paying client's)
    # from an invite email they never deleted. `--meet-per-event` asks Google to
    # mint a room for THIS event and reads it back off the API response; there
    # is no fallback between the two, deliberately, because a silent fallback is
    # how a shared room comes back unnoticed.
    #
    # `meet_scope="static"` is kept as an explicit escape hatch for an operator
    # whose Workspace refuses conference creation (google_tool exits 3 in that
    # case and the event still exists). It is never the default and no caller in
    # this repo passes it.
    meet_args = (["--meet"] if meet_scope == "static"
                 else ["--meet-per-event", "--meet-request-id",
                       meet_request_id(lead_id, start.isoformat(timespec="minutes"))])
    args = ["calendar", "create", "--title", title,
            "--start", start.isoformat(timespec="minutes"),
            "--end", end.isoformat(timespec="minutes"),
            *meet_args, "--timezone", "America/Toronto",
            "--description",
            f"Discovery call booked from the OASIS AI audit funnel.\n\n"
            f"Lead: {lead.get('name')} <{lead.get('email')}>\n"
            f"Brief: memory/lead_briefs/{lead_id}.md"]
    if lead.get("email"):
        args += ["--attendees", str(lead["email"])]

    rc, out, err = _run(args, timeout=180)
    if rc != 0:
        detail = f"calendar create failed: {err[:250]}"
        if rc == EXIT_EVENT_WITHOUT_MEET:
            # The EVENT EXISTS and Google has already mailed the invite; only the
            # room is missing. google_tool prints a machine-readable body on
            # stdout carrying the event id precisely so it can be cancelled, and
            # losing that here would leave a real meeting nobody can find.
            detail = (f"EVENT CREATED BUT IT HAS NO MEET ROOM — cancel it before "
                      f"retrying: {(out or err)[:250]}")
        result.update(ok=False, error=detail, calendar_output=(out or "")[:300])
        return result
    result["applied"] = True
    result["calendar_output"] = out[:300]
    # THE EVENT ID IS THE INVERSE. events.insert runs with sendUpdates:"all", so
    # by the time this line executes Google has already mailed a stranger an
    # invite — the single irreversible act in this pipeline. google_tool can undo
    # it (`calendar delete <id>`, which also mails the cancellation), but only if
    # somebody still has the id. Keeping just out[:300] of human-readable text
    # threw it away, leaving a real meeting on CC's calendar that no code could
    # find. An action with no inverse is a trapdoor; this is what gives it one.
    ident = _EVENT_ID_LINE_RE.search(out or "")
    result["event_id"] = ident.group(1).strip() if ident else None
    # The room that was actually created, read back off the tool's output rather
    # than assumed. The caller emails this to the prospect.
    minted = _MEET_LINE_RE.search(out or "")
    result["meet_link"] = minted.group(1) if minted else None
    if meet_scope != "static" and not result["meet_link"]:
        result.update(ok=False,
                      error="calendar create reported success but no Meet room "
                            "came back; the event may exist without a room")
        return result

    # Timeline entry so the booking is visible on the lead, not only in Google.
    try:
        db.table("lead_interactions").insert({
            "lead_id": lead_id,
            "tenant_id": lead.get("tenant_id"),
            "type": "meeting_scheduled",
            "channel": "calendar",
            "direction": "outbound",
            "subject": title,
            "content": f"Discovery call booked for {when} (30 min, Google Meet).",
            "content_preview": f"Discovery call {when}",
            "agent_source": "ai_audit_booking",
            "metadata": {"start": result["start"], "end": result["end"],
                         "brief": result.get("brief")},
        }).execute()
    except Exception as exc:  # noqa: BLE001
        result["interaction_warning"] = str(exc)[:200]

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Availability, Meet booking, pre-call brief")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("slots", help="free windows in CC's calendar")
    s.add_argument("--days", type=int, default=5)
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--json", action="store_true")

    b = sub.add_parser("brief", help="pre-call brief for a lead")
    b.add_argument("--lead-id", required=True)
    b.add_argument("--write", action="store_true", help="persist to memory/lead_briefs/")

    k = sub.add_parser("book", help="slots -> Meet event -> brief -> timeline")
    k.add_argument("--lead-id", required=True)
    k.add_argument("--start", required=True, help="local ISO, e.g. 2026-08-04T14:00")
    k.add_argument("--apply", action="store_true")
    k.add_argument("--json", action="store_true")

    a = ap.parse_args()

    if a.cmd == "slots":
        slots = free_slots(a.days, a.limit)
        if a.json:
            print(json.dumps({"slots": slots}, indent=2))
        elif not slots:
            print("no free slots in the window (calendar unreadable, or fully booked)")
        else:
            print(f"{len(slots)} bookable {CALL_MINUTES}-min slot(s):")
            for x in slots:
                print(f"  {x['label']:<28} {x['start']}")
        return

    db = get_supabase(load_env())

    if a.cmd == "brief":
        lead, meta = load_lead(db, a.lead_id)
        if not lead:
            print(f"lead {a.lead_id} not found", file=sys.stderr)
            raise SystemExit(1)
        body = build_brief(lead, meta)
        if a.write:
            print(f"wrote {write_brief(a.lead_id, body)}")
        else:
            print(body)
        return

    r = book(db, a.lead_id, a.start, a.apply)
    print(json.dumps(r, indent=2) if a.json else
          ("BOOKED" if r.get("applied") else "DRY RUN" if r.get("ok") else "FAILED")
          + f": {r.get('title')} @ {r.get('start')}"
          + (f"\n  {r.get('error')}" if r.get("error") else "")
          + (f"\n  brief: {r.get('brief')}" if r.get("brief") else ""))
    if not r.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
