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


def busy_windows(days: int) -> list[tuple[datetime, datetime]]:
    """Existing events as (start, end) local. Falls back to 'no known events'
    rather than inventing availability if the calendar cannot be read.

    NOTE: google_tool's `calendar list` prints `YYYY-MM-DD  Title` — date only,
    no times. All-day and untimed entries therefore block the WHOLE day. That is
    the conservative reading: offering a slot inside an unknown-duration event
    would double-book CC, and a missed slot costs nothing.
    """
    rc, out, err = _run(["calendar", "list", "--max", "80"])
    if rc != 0:
        print(f"[book] calendar read failed: {err[:200]}", file=sys.stderr)
        return []

    # `days` is a real filter, not decoration: `calendar list` returns whatever
    # is next on the calendar, which on a sparse calendar reaches months ahead.
    # Carrying those forward makes every clash check scan irrelevant windows.
    now = datetime.now(TZ)
    horizon = (now + timedelta(days=days + 1)).replace(hour=23, minute=59)

    busy: list[tuple[datetime, datetime]] = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})\s+(.*)", line)
        if not m:
            continue
        day = datetime.fromisoformat(m.group(1)).replace(tzinfo=TZ)
        if day > horizon or day < now - timedelta(days=1):
            continue
        busy.append((day.replace(hour=0, minute=0),
                     day.replace(hour=23, minute=59)))
    return busy


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

def book(db, lead_id: str, start_iso: str, apply: bool) -> dict:
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

    args = ["calendar", "create", "--title", title,
            "--start", start.isoformat(timespec="minutes"),
            "--end", end.isoformat(timespec="minutes"),
            "--meet", "--timezone", "America/Toronto",
            "--description",
            f"Discovery call booked from the OASIS AI audit funnel.\n\n"
            f"Lead: {lead.get('name')} <{lead.get('email')}>\n"
            f"Brief: memory/lead_briefs/{lead_id}.md"]
    if lead.get("email"):
        args += ["--attendees", str(lead["email"])]

    rc, out, err = _run(args, timeout=180)
    if rc != 0:
        result.update(ok=False, error=f"calendar create failed: {err[:250]}")
        return result
    result["applied"] = True
    result["calendar_output"] = out[:300]

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
