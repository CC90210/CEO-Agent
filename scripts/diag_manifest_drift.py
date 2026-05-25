"""
Check whether tenant_manifests DB row for slug='sun' matches the
in-code SUN_SEED. The DB row wins at runtime — if it's stale, all
the seeds.ts edits this session don't take effect for the live tenant.

Usage:
  python scripts/diag_manifest_drift.py
"""

from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from apply_migration import load_env  # noqa: E402


def main() -> int:
    env = load_env()
    from supabase import create_client
    client = create_client(env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"])

    res = (
        client.table("tenant_manifests")
        .select("slug, tenant_id, version, manifest, updated_at")
        .eq("slug", "sun")
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        print("[sun] NO ROW in tenant_manifests — runtime falls back to in-code SUN_SEED. OK.")
        return 0

    row = res.data
    manifest = row.get("manifest") or {}
    nav = manifest.get("nav") or []
    pages = manifest.get("pages") or []
    print(f"[sun] tenant_id={row.get('tenant_id')}")
    print(f"[sun] version={row.get('version')}  updated_at={row.get('updated_at')}")
    print(f"[sun] nav items: {len(nav)}")
    for n in nav:
        print(f"  - {n.get('href'):40s} {n.get('label'):20s} group={n.get('group')}")
    print(f"[sun] pages: {len(pages)}")
    for p in pages:
        kind = p.get("kind")
        path = p.get("path") or "(root)"
        print(f"  - {path:25s} kind={kind:18s} label={p.get('label')}")

    # Detect specific markers from this session's seed edits:
    nav_hrefs = {(n.get("href") or "") for n in nav}
    page_kinds = {(p.get("kind") or "") for p in pages}
    page_paths = {(p.get("path") or "") for p in pages}

    print()
    print("=== drift check vs in-code SUN_SEED ===")
    expected_nav_hrefs = {
        "/t/sun", "/agent", "/t/sun/reasoning", "/t/sun/playbook",
        "/t/sun/leads", "/t/sun/shopping-out", "/t/sun/applications",
        "/t/sun/offers", "/t/sun/renewals", "/t/sun/commissions", "/t/sun/lenders",
        "/t/sun/import", "/forms", "/sequences",
        "/team", "/automations", "/t/sun/settings",
    }
    expected_page_kinds = {
        "dashboard", "reasoning", "pipeline", "pipeline_entity",
        "shopping_out", "offers_v2", "renewals_v2", "lenders_v2",
        "kanban", "table", "markdown", "import", "settings",
    }
    expected_page_paths = {
        "", "reasoning", "pipeline", "leads", "applications",
        "shopping-out", "offers", "funded-deals", "renewals",
        "commissions", "lenders", "import", "settings", "playbook",
    }

    missing_nav = expected_nav_hrefs - nav_hrefs
    extra_nav = nav_hrefs - expected_nav_hrefs
    missing_kinds = expected_page_kinds - page_kinds
    missing_paths = expected_page_paths - page_paths

    if not missing_nav and not extra_nav and not missing_kinds and not missing_paths:
        print("[sun] DB row MATCHES in-code SUN_SEED — no drift.")
        return 0

    print(f"[sun] DRIFT DETECTED:")
    if missing_nav:
        print(f"  missing nav hrefs (in seed, not in DB): {sorted(missing_nav)}")
    if extra_nav:
        print(f"  extra nav hrefs (in DB, not in seed):   {sorted(extra_nav)}")
    if missing_kinds:
        print(f"  missing page kinds: {sorted(missing_kinds)}")
    if missing_paths:
        print(f"  missing page paths: {sorted(missing_paths)}")
    print()
    print("FIX: upsert the SUN_SEED JSON into tenant_manifests.manifest via the")
    print("     dashboard's manifest editor at /t/sun/editor, or apply a")
    print("     direct upsert through supabase_admin.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
