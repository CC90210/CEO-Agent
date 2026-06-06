"""One-shot CRM reconciliation: demote OASIS leads that are tagged
`stage = outreach` but have ZERO evidence anyone ever reached out to them.

Why this exists: CSV imports landed in `stage = outreach` regardless of
whether the lead had been contacted. The dashboard pipeline reads stage
literally — these leads showed in the "Outreach" column, distorting the
funnel and burning CC's attention. Reality is they're untouched cold
contacts; their correct stage is `new_contact`.

A lead has zero evidence of contact when BOTH:
  - 0 rows in lead_interactions for that lead_id
  - data.last_contacted_at is null

Anything with either signal stays in outreach (real prior contact via
Gmail reconciler, manual log, etc.).

Idempotent: re-running after a fresh CSV import correctly demotes any
newly-stuck leads; previously-corrected rows already carry the
correction note + are in new_contact so they're skipped.

Run:
  python scripts/_demote_misplaced_outreach.py --dry-run   # preview
  python scripts/_demote_misplaced_outreach.py             # apply
  python scripts/_demote_misplaced_outreach.py --tenant <uuid>  # other tenant
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "lib"))

from secret_loader import load_env  # type: ignore  # noqa: E402


OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"


def _supabase():
    env = load_env()
    from supabase import create_client
    return create_client(env["BRAVO_SUPABASE_URL"], env["BRAVO_SUPABASE_SERVICE_ROLE_KEY"])


def find_candidates(client, tenant_id: str) -> list[dict]:
    leads = (
        client.table("tenant_records")
        .select("id,data")
        .eq("tenant_id", tenant_id)
        .eq("entity_type", "lead")
        .limit(500)
        .execute()
        .data
        or []
    )
    outreach = [r for r in leads if (r.get("data") or {}).get("stage") == "outreach"]
    if not outreach:
        return []
    ids = [r["id"] for r in outreach]
    counts: dict[str, int] = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        rows = (
            client.table("lead_interactions")
            .select("lead_id")
            .in_("lead_id", chunk)
            .limit(2000)
            .execute()
            .data
            or []
        )
        for row in rows:
            counts[row["lead_id"]] = counts.get(row["lead_id"], 0) + 1
    return [
        r
        for r in outreach
        if counts.get(r["id"], 0) == 0
        and not (r.get("data") or {}).get("last_contacted_at")
    ]


def demote(client, rows: list[dict], dry_run: bool) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    note_line = (
        f"[{stamp}] stage corrected: outreach->new_contact "
        f"(no logged interactions or last_contacted_at; never actually outreached)"
    )
    updated = 0
    for r in rows:
        d = dict(r.get("data") or {})
        # Re-run safety: skip rows that already carry the correction note.
        if note_line in (d.get("notes") or ""):
            continue
        d["stage"] = "new_contact"
        if d.get("status") == "contacted":
            d["status"] = "new"
        existing = (d.get("notes") or "").strip()
        d["notes"] = (existing + "\n\n" + note_line).strip() if existing else note_line
        if not dry_run:
            client.table("tenant_records").update({"data": d}).eq("id", r["id"]).execute()
        updated += 1
    return updated


def main() -> int:
    p = argparse.ArgumentParser(description="Demote stage-misplaced outreach leads")
    p.add_argument("--tenant", default=OASIS_TENANT_ID, help="tenant UUID")
    p.add_argument("--dry-run", action="store_true", help="preview, no writes")
    args = p.parse_args()

    client = _supabase()
    candidates = find_candidates(client, args.tenant)
    if not candidates:
        print("no candidates to demote.")
        return 0
    print(f"candidates: {len(candidates)} lead(s)")
    for r in candidates[:5]:
        d = r.get("data") or {}
        print(
            f"  {r['id'][:8]} | {(d.get('name') or '(blank)')[:25]:<25} | "
            f"{(d.get('email') or '')[:35]}"
        )
    if len(candidates) > 5:
        print(f"  ... and {len(candidates) - 5} more")
    n = demote(client, candidates, dry_run=args.dry_run)
    verb = "would demote" if args.dry_run else "demoted"
    print(f"\n{verb} {n} lead(s) outreach -> new_contact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
