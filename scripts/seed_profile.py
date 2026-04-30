#!/usr/bin/env python3
"""seed_profile.py — seed (or update) the OASIS Command Center operator profile.

Idempotent. Run once per operator. CC's profile is the default — if no args
are passed, it seeds Conaugh McKenna's profile with $5K target, all 6 agents
enabled, manifesto loaded, sales script V1 pinned, and today's primary lead
(Jonathan Hutton at Basque Landscaping).

Usage:
  # Seed CC's profile (default)
  python scripts/seed_profile.py

  # Seed a different operator
  python scripts/seed_profile.py \
      --email someone@example.com \
      --full-name "Some One" \
      --brand "Their Brand" \
      --mrr-target 10000

  # Just refresh today's plan + primary lead (don't touch profile)
  python scripts/seed_profile.py --plan-only

Env: BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
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


CC_DEFAULTS = {
    "email": "conaugh@oasisai.work",
    "full_name": "Conaugh McKenna",
    "display_name": "CC",
    "brand": "OASIS AI",
    "role": "operator",
    "mrr_target_usd": 5000.00,
    "mrr_current_usd": 3322.00,
    "mrr_target_date": "2026-05-15",
    "agents_enabled": ["bravo", "codex", "atlas", "maven", "aura", "hermes"],
    "primary_agent": "bravo",
    "primary_script_version": "cold_call_v1",
    "deal_architecture_version": "v1",
}

CC_MANIFESTO_PATH = ROOT / "memory" / "poems" / "sub_agents_collective_intelligence.md"


def load_manifesto_body() -> str:
    if not CC_MANIFESTO_PATH.exists():
        return ""
    text = CC_MANIFESTO_PATH.read_text(encoding="utf-8")
    # Strip frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    # Drop the H1 if present
    lines = [l for l in text.splitlines() if not l.strip().startswith("#")]
    # Drop the leading blockquote intro
    out = []
    skip_blockquote = True
    for line in lines:
        if skip_blockquote and line.strip().startswith(">"):
            continue
        skip_blockquote = False
        out.append(line)
    return "\n".join(out).strip()


def db() -> "Client":
    url = os.environ.get("BRAVO_SUPABASE_URL")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def upsert_profile(client: "Client", spec: dict, manifesto: str) -> dict:
    payload = {**spec, "manifesto": manifesto}
    # Try update by email; if no row, insert
    existing = (
        client.table("user_profiles").select("id").eq("email", spec["email"]).limit(1).execute()
    )
    if existing.data:
        r = (
            client.table("user_profiles")
            .update(payload)
            .eq("email", spec["email"])
            .execute()
        )
        return r.data[0] if r.data else existing.data[0]
    r = client.table("user_profiles").insert(payload).execute()
    return r.data[0]


def find_jonathan(client: "Client") -> str | None:
    """Find Jonathan Hutton (Basque Landscaping) lead id."""
    r = (
        client.table("leads")
        .select("id,name,company,phone")
        .or_("company.ilike.%basque%,name.ilike.%hutton%")
        .limit(5)
        .execute()
    )
    for row in r.data or []:
        if "basque" in (row.get("company") or "").lower() or "hutton" in (row.get("name") or "").lower():
            return row["id"]
    return None


CC_TODAY_PLAN = {
    "mission": "27 cold calls + Jonathan phone close + 10 follow-ups + 3 partner reach-outs.",
    "primary_lead_play": (
        "Tuesday: real conversation, qualified, agreed to book. Two follow-up texts already sent — "
        "no booking yet. Next move is the phone, not a third text. "
        "Call between 1:30 and 1:45 PM. Two rings, voicemail if no answer. "
        "If he picks up: book the call before you hang up — Tuesday 2pm or Thursday 11am."
    ),
    "target_calls": 27,
    "target_emails": 10,
    "target_bookings": 1,
    "schedule": [
        {
            "time_label": "10:30 — 10:45",
            "title": "Stats check + workspace setup",
            "body": "Open Command Center on second monitor. Phone charged. Headset on. Water + coffee. No notifications.",
            "intensity": "normal",
        },
        {
            "time_label": "10:45 — 11:30",
            "title": "Script practice + warm-up role-play",
            "body": "Read the script aloud 3× standing up. Then 5 throwaway practice dials before the real list.",
            "intensity": "intense",
        },
        {
            "time_label": "11:30 — 1:00",
            "title": "Cold call block #1 — Hamilton list (12 calls)",
            "body": "Pull the 9 unflagged Hamilton leads. Add 3 fresh ones. 12 dials, target 3 conversations, 1 booking.",
            "intensity": "intense",
        },
        {
            "time_label": "1:00 — 1:30",
            "title": "Lunch + retro",
            "body": "Eat. Step outside. Mentally replay best/worst calls. Note one objection that caught you.",
            "intensity": "break",
        },
        {
            "time_label": "1:30 — 2:00",
            "title": "Jonathan Hutton — phone call",
            "body": "Use the play card on Today. One ring. Voicemail script ready. If he picks up, book it before you hang up.",
            "intensity": "intense",
        },
        {
            "time_label": "2:00 — 3:30",
            "title": "Cold call block #2 — net-new (15 calls)",
            "body": "Switch verticals. Collingwood/Barrie professionals — accountants, advisors, brokers. 15 dials, 5+ conversations, 1+ booking.",
            "intensity": "intense",
        },
        {
            "time_label": "3:30 — 4:00",
            "title": "Email batch — 10 follow-ups",
            "body": "python scripts/outreach_batch.py --json — send 10 OASIS Value-Add follow-ups with the new 14-day pilot framing.",
            "intensity": "normal",
        },
        {
            "time_label": "4:00 — 5:00",
            "title": "Content — record one video",
            "body": "Manifesto excerpt. 60-sec iPhone vertical. Hand to Maven: cd ../CMO-Agent && python scripts/content_pipeline.py.",
            "intensity": "normal",
        },
        {
            "time_label": "5:00 — 5:30",
            "title": "Pipeline review",
            "body": "Open Pipeline page. Confirm every call shows. Update Jonathan's status. Score: dials / conversations / bookings.",
            "intensity": "normal",
        },
        {
            "time_label": "5:30 — 6:30",
            "title": "Gym / break",
            "body": "Non-negotiable. Phone DND except Telegram critical alerts.",
            "intensity": "break",
        },
        {
            "time_label": "6:30 — 7:30",
            "title": "Strategic partner outreach — 3 targets",
            "body": "Tier 1 partner pitch. One business coach, one accountant with SMB book, one marketing agency. Recruitment, not selling.",
            "intensity": "intense",
        },
        {
            "time_label": "7:30 — 8:00",
            "title": "Day retro + state sync",
            "body": "python scripts/state_sync.py --note. Pre-stage tomorrow's 30 leads. Sleep at 11.",
            "intensity": "normal",
        },
    ],
}


def upsert_today_plan(client: "Client", profile_id: str, jonathan_lead_id: str | None) -> dict:
    today_iso = date.today().isoformat()
    payload = {
        "profile_id": profile_id,
        "plan_date": today_iso,
        "primary_lead_id": jonathan_lead_id,
        **CC_TODAY_PLAN,
    }
    existing = (
        client.table("daily_plans")
        .select("id")
        .eq("profile_id", profile_id)
        .eq("plan_date", today_iso)
        .limit(1)
        .execute()
    )
    if existing.data:
        r = (
            client.table("daily_plans")
            .update(payload)
            .eq("id", existing.data[0]["id"])
            .execute()
        )
        return r.data[0] if r.data else existing.data[0]
    r = client.table("daily_plans").insert(payload).execute()
    return r.data[0]


def seed_integration_baseline(client: "Client", profile_id: str) -> None:
    """Mark known-healthy integrations so the Settings page isn't all gray on day 1."""
    services = [
        ("supabase", "healthy", None),
        ("stripe", "healthy", None),
        ("gmail", "healthy", None),
        ("telegram", "healthy", None),
        ("browser_harness", "degraded", "Chrome remote-debugging not yet attached"),
        ("n8n_inbound", "unconfigured", "Webhook secret not yet issued or n8n workflow not pointing here"),
    ]
    for service, status, err in services:
        client.rpc(
            "ping_integration",
            {
                "p_profile_id": profile_id,
                "p_service": service,
                "p_status": status,
                "p_error": err,
                "p_metadata": {},
            },
        ).execute()


def main() -> int:
    p = argparse.ArgumentParser(description="Seed OASIS Command Center operator profile")
    p.add_argument("--email", default=CC_DEFAULTS["email"])
    p.add_argument("--full-name", default=CC_DEFAULTS["full_name"])
    p.add_argument("--display-name", default=CC_DEFAULTS["display_name"])
    p.add_argument("--brand", default=CC_DEFAULTS["brand"])
    p.add_argument("--mrr-target", type=float, default=CC_DEFAULTS["mrr_target_usd"])
    p.add_argument("--mrr-current", type=float, default=CC_DEFAULTS["mrr_current_usd"])
    p.add_argument("--mrr-target-date", default=CC_DEFAULTS["mrr_target_date"])
    p.add_argument("--plan-only", action="store_true", help="Only refresh today's plan, skip profile upsert")
    p.add_argument("--no-plan", action="store_true", help="Skip today's plan seed")
    p.add_argument("--json", action="store_true")

    args = p.parse_args()

    client = db()

    if args.plan_only:
        # Look up existing profile
        existing = (
            client.table("user_profiles").select("id").eq("email", args.email).limit(1).execute()
        )
        if not existing.data:
            print(f"ERROR: no profile for {args.email}, can't seed plan-only", file=sys.stderr)
            return 1
        profile_id = existing.data[0]["id"]
    else:
        spec = {
            "email": args.email,
            "full_name": args.full_name,
            "display_name": args.display_name,
            "brand": args.brand,
            "role": CC_DEFAULTS["role"],
            "mrr_target_usd": args.mrr_target,
            "mrr_current_usd": args.mrr_current,
            "mrr_target_date": args.mrr_target_date,
            "agents_enabled": CC_DEFAULTS["agents_enabled"],
            "primary_agent": CC_DEFAULTS["primary_agent"],
            "primary_script_version": CC_DEFAULTS["primary_script_version"],
            "deal_architecture_version": CC_DEFAULTS["deal_architecture_version"],
        }
        manifesto = load_manifesto_body() if args.email == CC_DEFAULTS["email"] else ""
        profile = upsert_profile(client, spec, manifesto)
        profile_id = profile["id"]
        seed_integration_baseline(client, profile_id)

    plan = None
    if not args.no_plan:
        jonathan_id = find_jonathan(client) if args.email == CC_DEFAULTS["email"] else None
        plan = upsert_today_plan(client, profile_id, jonathan_id)

    if args.json:
        print(
            json.dumps(
                {"ok": True, "profile_id": profile_id, "plan_id": plan["id"] if plan else None},
                indent=2,
                default=str,
            )
        )
    else:
        print(f"Profile seeded: {profile_id}")
        if plan:
            print(f"Today's plan seeded: {plan['id']}")
        print()
        print("Set OPERATOR_EMAIL in Vercel env so the dashboard finds this profile:")
        print(f"  OPERATOR_EMAIL={args.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
