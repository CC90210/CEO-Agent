#!/usr/bin/env python3
"""seed_plan_template.py — seed (or update) plan templates for an operator.

Two kinds:
  weekday  — Monday through Friday recurring schedule
  weekend  — Saturday + Sunday recurring schedule

Idempotent. Re-running updates the existing template instead of creating a duplicate.

Usage:
  python scripts/seed_plan_template.py              # seed both for CC
  python scripts/seed_plan_template.py --kind weekday
  python scripts/seed_plan_template.py --email someone@example.com --kind weekend
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # type: ignore

load_dotenv(ROOT / ".env.agents")

try:
    from supabase import create_client, Client  # type: ignore
except ImportError:
    print("ERROR: pip install supabase", file=sys.stderr)
    sys.exit(2)


WEEKDAY_TEMPLATE = {
    "mission": "27 cold calls + primary lead close + 10 follow-ups + 3 partner reach-outs.",
    "target_calls": 27,
    "target_emails": 10,
    "target_bookings": 1,
    "schedule": [
        {"time_label": "08:00 — 09:00", "title": "Morning routine + gym", "body": "Body is the platform. Phone DND.", "intensity": "break"},
        {"time_label": "09:00 — 09:30", "title": "Stats check + workspace setup", "body": "Open Command Center. Phone charged. Headset on. Water + coffee. No notifications.", "intensity": "normal"},
        {"time_label": "09:30 — 10:15", "title": "Script practice + Mirror Run", "body": "Read the script aloud 3× standing up. Then 5 throwaway practice dials before the real list.", "intensity": "intense"},
        {"time_label": "10:15 — 12:00", "title": "Cold call block #1 (12+ calls)", "body": "Pull the day's eligible leads from the Pipeline. Target: 12 dials, 3 conversations, 1 booking.", "intensity": "intense"},
        {"time_label": "12:00 — 12:30", "title": "Lunch + retro", "body": "Eat. Step outside. Replay best/worst calls. Note any objection that caught you.", "intensity": "break"},
        {"time_label": "12:30 — 13:00", "title": "Primary lead — phone call", "body": "Use the play card on Today. One ring. Voicemail script ready. If they pick up, book it before you hang up.", "intensity": "intense"},
        {"time_label": "13:00 — 14:30", "title": "Cold call block #2 (15+ calls)", "body": "Switch verticals. 15 dials, 5+ conversations, 1+ booking.", "intensity": "intense"},
        {"time_label": "14:30 — 15:00", "title": "Email batch — 10 follow-ups", "body": "Open /pipeline → filter contacted → write 10 personalized Value-Add follow-ups with the new 14-day pilot framing. Send per-lead via scripts/outreach_engine.py send --lead-id <id>.", "intensity": "normal"},
        {"time_label": "15:00 — 16:00", "title": "Content — 1 piece shipped", "body": "Record a 60-sec iPhone vertical OR write a long-form post. Hand to Maven for the pipeline.", "intensity": "normal"},
        {"time_label": "16:00 — 16:30", "title": "Pipeline review + KPI log", "body": "Open Pipeline. Confirm every call shows. Update statuses. Score: dials / conversations / bookings.", "intensity": "normal"},
        {"time_label": "16:30 — 17:30", "title": "Strategic partner outreach (3 targets)", "body": "Tier 1 partner pitch. Recruitment, not selling. One business coach, one accountant, one agency.", "intensity": "intense"},
        {"time_label": "17:30 — 18:00", "title": "End of day + state sync", "body": "python scripts/state_sync.py --note. Pre-stage tomorrow's leads. Sleep at 11.", "intensity": "normal"},
    ],
}

WEEKEND_TEMPLATE = {
    "mission": "Plan the week + ship 2 content pieces + recover.",
    "target_calls": 0,
    "target_emails": 0,
    "target_bookings": 0,
    "schedule": [
        {"time_label": "09:00 — 10:00", "title": "Slow morning", "body": "No phone. Read or walk. Mind needs the rest.", "intensity": "break"},
        {"time_label": "10:00 — 11:30", "title": "Weekly retro", "body": "Drill #5: review the week's call recordings, KPIs, notes. Three questions: what worked, what broke, what objection caught you most.", "intensity": "intense"},
        {"time_label": "11:30 — 13:00", "title": "Content block — 2 pieces", "body": "Long-form post + 1 video. Built once, distributed across the week via Maven.", "intensity": "intense"},
        {"time_label": "13:00 — 14:30", "title": "Lunch + DJ practice / hobby", "body": "Mind off work. Body off chair.", "intensity": "break"},
        {"time_label": "14:30 — 16:00", "title": "Next-week planning", "body": "Review Pipeline, set Monday's primary lead, queue tomorrow's content. Adjust weekday template if last week's data demanded it.", "intensity": "normal"},
        {"time_label": "16:00 — 17:00", "title": "Codebase / dashboard polish", "body": "30-60 min on the AGS — small wins compound.", "intensity": "normal"},
        {"time_label": "17:00 onwards", "title": "Off", "body": "Friends, family, gym, food. Build a life worth working for.", "intensity": "break"},
    ],
}


def db() -> "Client":
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing BRAVO_SUPABASE_URL / BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def upsert_template(client: "Client", profile_id: str, tenant_id: str, kind: str, payload: dict) -> dict:
    existing = (
        client.table("plan_templates")
        .select("id")
        .eq("profile_id", profile_id)
        .eq("kind", kind)
        .limit(1)
        .execute()
    )
    body = {
        "profile_id": profile_id,
        "tenant_id": tenant_id,
        "kind": kind,
        "enabled": True,
        **payload,
    }
    if existing.data:
        r = client.table("plan_templates").update(body).eq("id", existing.data[0]["id"]).execute()
        return r.data[0] if r.data else existing.data[0]
    r = client.table("plan_templates").insert(body).execute()
    return r.data[0]


def main() -> int:
    p = argparse.ArgumentParser(description="Seed plan templates")
    p.add_argument("--email", default="conaugh@oasisai.work")
    p.add_argument("--kind", choices=["weekday", "weekend", "both"], default="both")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    client = db()
    profile_r = client.table("user_profiles").select("id, tenant_id").eq("email", args.email).limit(1).execute()
    if not profile_r.data:
        print(f"ERROR: no user_profile for {args.email}", file=sys.stderr)
        return 1
    profile = profile_r.data[0]
    profile_id, tenant_id = profile["id"], profile["tenant_id"]

    out = {}
    if args.kind in ("weekday", "both"):
        wd = upsert_template(client, profile_id, tenant_id, "weekday", WEEKDAY_TEMPLATE)
        out["weekday"] = wd["id"]
    if args.kind in ("weekend", "both"):
        we = upsert_template(client, profile_id, tenant_id, "weekend", WEEKEND_TEMPLATE)
        out["weekend"] = we["id"]

    if args.json:
        print(json.dumps({"ok": True, **out}, indent=2))
    else:
        print(f"Seeded plan templates for {args.email}:")
        for k, v in out.items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
