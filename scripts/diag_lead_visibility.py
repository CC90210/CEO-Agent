"""
One-off diagnostic for the 'where did my imported leads go?' question.

Counts tenant_records by (tenant slug, entity_type, stage/status) so we
can see exactly which tenant owns the import and whether the stage
values are in the post-migration-064 visible set.

Usage:
  python scripts/diag_lead_visibility.py
"""

from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from apply_migration import load_env  # noqa: E402

VISIBLE_LEAD_STAGES = {
    "hot_lead", "missing_info", "follow_up", "sent_application",
    "viewed_application", "signed_application", "submitted",
    "declined", "default",
}
VISIBLE_APP_STATUSES = {
    "application_in", "shopping", "missing_info", "requested_docs",
    "docs_out", "login", "funded", "follow_ups", "declined", "dead_file",
}


def main() -> int:
    env = load_env()
    try:
        from supabase import create_client
    except ImportError:
        print("supabase package not installed", file=sys.stderr)
        return 1
    client = create_client(
        env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"]
    )

    # 1. List all tenants so we can label tenant_ids.
    tenants_q = client.table("tenants").select("id, slug, name").execute()
    tenants = {t["id"]: t for t in (tenants_q.data or [])}
    print("TENANTS:")
    for t in tenants.values():
        print(f"  {t['slug']:12s} {t['id']}  {t.get('name') or ''}")
    print()

    # 2. For each tenant, count tenant_records by entity_type + stage/status.
    for tenant in tenants.values():
        tid = tenant["id"]
        slug = tenant["slug"]
        # Pull all entity_type='lead' rows
        leads_q = (
            client.table("tenant_records")
            .select("id, data, created_at")
            .eq("tenant_id", tid)
            .eq("entity_type", "lead")
            .limit(5000)
            .execute()
        )
        apps_q = (
            client.table("tenant_records")
            .select("id, data, created_at")
            .eq("tenant_id", tid)
            .eq("entity_type", "application")
            .limit(5000)
            .execute()
        )
        leads = leads_q.data or []
        apps = apps_q.data or []
        if not leads and not apps:
            continue

        print(f"=== tenant: {slug} ({tid}) ===")
        print(f"  total leads:        {len(leads)}")
        print(f"  total applications: {len(apps)}")

        # Lead stage breakdown
        lead_stages: dict[str, int] = {}
        invisible_leads = 0
        for r in leads:
            stage = ((r.get("data") or {}).get("stage") or "").strip() or "(empty)"
            lead_stages[stage] = lead_stages.get(stage, 0) + 1
            if stage not in VISIBLE_LEAD_STAGES and stage != "(empty)":
                invisible_leads += 1
        if lead_stages:
            print(f"  lead stages:")
            for st, n in sorted(lead_stages.items(), key=lambda x: -x[1]):
                visible = "[ok]" if st in VISIBLE_LEAD_STAGES else "[HIDDEN]"
                print(f"    {st:30s} {n:5d}  {visible}")
            if invisible_leads:
                print(f"  >>> {invisible_leads} leads have stages NOT in the visible set")

        # Application status breakdown
        app_statuses: dict[str, int] = {}
        invisible_apps = 0
        for r in apps:
            status = ((r.get("data") or {}).get("status") or "").strip() or "(empty)"
            app_statuses[status] = app_statuses.get(status, 0) + 1
            if status not in VISIBLE_APP_STATUSES and status != "(empty)":
                invisible_apps += 1
        if app_statuses:
            print(f"  application statuses:")
            for st, n in sorted(app_statuses.items(), key=lambda x: -x[1]):
                visible = "[ok]" if st in VISIBLE_APP_STATUSES else "[HIDDEN]"
                print(f"    {st:30s} {n:5d}  {visible}")
            if invisible_apps:
                print(f"  >>> {invisible_apps} apps have statuses NOT in the visible set")

        # Source breakdown — which imports came from where
        sources: dict[str, int] = {}
        for r in leads + apps:
            src = ((r.get("data") or {}).get("source") or "").strip() or "(none)"
            sources[src] = sources.get(src, 0) + 1
        print(f"  source breakdown:")
        for src, n in sorted(sources.items(), key=lambda x: -x[1])[:10]:
            print(f"    {src:30s} {n:5d}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
