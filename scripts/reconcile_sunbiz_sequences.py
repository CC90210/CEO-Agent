"""
Reconcile drip_sequences in the live Sun Biz tenant against the
post-migration-064 seed in lib/sunbiz-default-sequences.ts.

The seed file is the source of truth for NEW tenants. Existing Sun Biz
tenant rows were seeded earlier (pre-064) and don't get touched when the
seed file is edited. This script reads the seed, then upserts each
sequence into the live drip_sequences table for Sun Biz — inserting
when missing, updating trigger_filter/steps when name matches but
content drifted, leaving untouched when already correct.

The seed list is hardcoded here (mirrors lib/sunbiz-default-sequences.ts)
because we don't run a Node interpreter from BEA. Keep in sync — if the
TS file gains a new sequence, add it here too.

Idempotent. Safe to re-run.

Usage:
  python scripts/reconcile_sunbiz_sequences.py            # apply changes
  python scripts/reconcile_sunbiz_sequences.py --dry-run  # report only
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from apply_migration import load_env  # noqa: E402


# Mirror of SUNBIZ_DEFAULT_SEQUENCES in lib/sunbiz-default-sequences.ts.
# Names are the upsert key — change carefully.
SEQUENCES: list[dict] = [
    {
        "name": "Follow-up sequence",
        "description": "Fires when a lead reaches the follow_up stage. 3-touch SMS+email cadence to get them on a call.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "follow_up"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [
            {"channel": "sms", "delay_minutes": 10, "from_label": "Solara"},
            {"channel": "email", "delay_minutes": 60 * 24, "from_label": "Solara"},
            {"channel": "sms", "delay_minutes": 60 * 24 * 3, "from_label": "Solara"},
        ],
    },
    {
        "name": "Viewed application nudge",
        "description": "Fires when a lead opens their personalized application link. Nudges them through the form.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "viewed_application"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [
            {"channel": "sms", "delay_minutes": 30, "from_label": "Solara"},
            {"channel": "email", "delay_minutes": 60 * 24, "from_label": "Solara"},
        ],
    },
    {
        "name": "Submitted — underwriting wait",
        "description": "Fires when a lead's application is fully submitted. Sets expectations + asks them to stay reachable.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "submitted"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [{"channel": "sms", "delay_minutes": 15, "from_label": "Solara"}],
    },
    {
        "name": "Declined — 1-month check-back",
        "description": "Professional 1-month re-engagement for leads declined after bank-statement review. Doesn't burn the bridge.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "declined"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [{"channel": "email", "delay_minutes": 60 * 24 * 30, "from_label": "Solara"}],
    },
    {
        "name": "Missing info — chase + book call",
        "description": "Fires when a lead lands in missing_info. Two-touch cadence to request the outstanding info and book a call.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "missing_info"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [
            {"channel": "sms", "delay_minutes": 30, "from_label": "Solara"},
            {"channel": "email", "delay_minutes": 60 * 24 * 2, "from_label": "Solara"},
        ],
    },
    {
        "name": "Sent application — 24h reminder",
        "description": "Fires when an application link goes out. If the lead hasn't clicked through, send a soft 24h reminder.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "sent_application"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [{"channel": "sms", "delay_minutes": 60 * 24, "from_label": "Solara"}],
    },
    {
        "name": "Signed application — bank statements nag",
        "description": "Fires when a lead signs the application but hasn't uploaded bank statements yet.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "signed_application"},
        "one_per_lead": True,
        "enabled": True,
        "steps": [
            {"channel": "sms", "delay_minutes": 60 * 12, "from_label": "Solara"},
            {"channel": "email", "delay_minutes": int(60 * 24 * 1.5), "from_label": "Solara"},
        ],
    },
    {
        "name": "Default — 60-day soft check-in (DISABLED by default)",
        "description": "Sensitive: fires 60 days after a lead's funded_deal defaults. Soft check-in only.",
        "trigger_event": "BRAVO_RECORD_STATUS_CHANGED",
        "trigger_filter": {"entity": "lead", "field": "stage", "to": "default"},
        "one_per_lead": True,
        "enabled": False,  # sensitive — operator must opt in
        "steps": [{"channel": "email", "delay_minutes": 60 * 24 * 60, "from_label": "Solara"}],
    },
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    env = load_env()
    from supabase import create_client
    client = create_client(env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"])

    # Resolve Sun Biz tenant via tenant_manifests first, fall back to slug='submissions'.
    tm = client.table("tenant_manifests").select("tenant_id").eq("slug", "sun").maybe_single().execute()
    sun_tenant_id = (tm.data or {}).get("tenant_id") if tm else None
    if not sun_tenant_id:
        t = client.table("tenants").select("id").eq("slug", "submissions").maybe_single().execute()
        sun_tenant_id = (t.data or {}).get("id") if t else None
    if not sun_tenant_id:
        print("[reconcile] Sun Biz tenant not found — nothing to reconcile.")
        return 0
    print(f"[reconcile] tenant_id={sun_tenant_id}  dry_run={args.dry_run}")

    existing = (
        client.table("drip_sequences")
        .select("id, name, trigger_event, trigger_filter, steps, enabled, one_per_lead")
        .eq("tenant_id", sun_tenant_id)
        .execute()
    )
    by_name = {row["name"]: row for row in (existing.data or [])}
    print(f"[reconcile] {len(by_name)} existing sequence(s) on Sun Biz")

    inserted = updated = unchanged = 0
    for seq in SEQUENCES:
        existing_row = by_name.get(seq["name"])
        payload = {
            "tenant_id": sun_tenant_id,
            "name": seq["name"],
            "description": seq["description"],
            "trigger_event": seq["trigger_event"],
            "trigger_filter": seq["trigger_filter"],
            "steps": seq["steps"],
            "enabled": seq["enabled"],
            "one_per_lead": seq["one_per_lead"],
        }
        if not existing_row:
            print(f"  + INSERT  {seq['name']}")
            if not args.dry_run:
                client.table("drip_sequences").insert(payload).execute()
            inserted += 1
            continue
        drift = (
            existing_row.get("trigger_event") != seq["trigger_event"]
            or json.dumps(existing_row.get("trigger_filter"), sort_keys=True) != json.dumps(seq["trigger_filter"], sort_keys=True)
            or json.dumps(existing_row.get("steps"), sort_keys=True) != json.dumps(seq["steps"], sort_keys=True)
        )
        if drift:
            print(f"  ~ UPDATE  {seq['name']}")
            if not args.dry_run:
                client.table("drip_sequences").update(payload).eq("id", existing_row["id"]).execute()
            updated += 1
        else:
            unchanged += 1

    print(f"[reconcile] DONE — inserted={inserted}  updated={updated}  unchanged={unchanged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
