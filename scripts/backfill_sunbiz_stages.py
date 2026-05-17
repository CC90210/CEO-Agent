"""backfill_sunbiz_stages.py — one-shot migration of pre-2026-05-17 stage values.

The SunBiz CRM rework on 2026-05-17 replaced the lead.stage and
application.status enums with the Salesforce-parity Opportunity Pipeline
vocabulary. Existing tenant_records rows in production still carry the
old values — they render as raw-string fallbacks in the new chevron
pipeline view, so the operator sees them as "uncategorized" and the
per-stage counts under-count reality.

This script:
  1. Selects every tenant_records row for the SunBiz tenant where the
     entity is lead / application / offer and the stage/status field
     contains a legacy enum value.
  2. Maps each legacy value to the closest Salesforce-parity stage.
  3. Writes the new value back to tenant_records.data.
  4. Logs every change to state/backfill_sunbiz_stages.log so the
     migration is auditable (and reversible if a mapping decision turns
     out wrong).

Usage:
  python scripts/backfill_sunbiz_stages.py --dry-run     # preview only
  python scripts/backfill_sunbiz_stages.py               # actually write

The script is idempotent — re-running after a successful write produces
zero further mutations (the second pass finds no legacy values).

Why a Python script instead of a SQL migration: tenant_records.data is
a jsonb blob, so the rewrite needs per-row inspection rather than a
straight UPDATE WHERE clause. Doing this in Python with the existing
supabase service-role client keeps the audit log + dry-run pattern
consistent with our other ops scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
LOG_PATH = STATE_DIR / "backfill_sunbiz_stages.log"

# SunBiz tenant id resolved from `tenants` table (slug='submissions').
SUNBIZ_TENANT_ID = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"

# Mapping: legacy stage/status value -> Salesforce-parity replacement.
#
# Lead Pipeline (lead.stage):
#   cold              -> imported            (pre-engagement fresh row)
#   qualified         -> hot_lead            (operator-vetted lead)
#   application_sent  -> sent_application    (snake_case canonicalisation)
#
# Opportunity Pipeline (application.status + offer.stage share the same
# new enum because the offer is a per-lender sub-detail of the same
# pipeline):
#   draft             -> submitted_to_underwriting (operator drafted, ready)
#   submitted         -> submitted_to_underwriting (was the "submitted to
#                                                   underwriting" semantic in
#                                                   the legacy flow too)
#   in_review         -> submitted_to_underwriting (lender currently reviewing)
#   approved          -> approved_open_offers      (term sheet on the way)
#   offered           -> approved_open_offers      (legacy offer-side)
#   contracts_out     -> contracts_ordered        (sent client a contract)
#   accepted          -> funded                   (Accept button used to flip
#                                                   to "accepted"; now flips
#                                                   straight to "funded")
#   no_offer          -> no_offers_available      (snake_case canonicalisation)
#   declined          -> dead_file                (operator passed on the deal)
#   expired           -> approved_never_funded    (offer aged out — was
#                                                   approved but never closed)
#   lost              -> dead_file                (legacy generic loss)
LEGACY_LEAD_MAP = {
    "cold": "imported",
    "qualified": "hot_lead",
    "application_sent": "sent_application",
}

LEGACY_OPP_MAP = {
    "draft": "submitted_to_underwriting",
    "submitted": "submitted_to_underwriting",
    "in_review": "submitted_to_underwriting",
    "approved": "approved_open_offers",
    "offered": "approved_open_offers",
    "contracts_out": "contracts_ordered",
    "accepted": "funded",
    "no_offer": "no_offers_available",
    "declined": "dead_file",
    "expired": "approved_never_funded",
    "lost": "dead_file",
}


def _log(line: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")
    print(line)


def _supabase():
    # Same loader the other CLI wrappers use. Lives in scripts/lib.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from lib.secret_loader import load_env  # noqa: E402

    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("supabase env not configured")
    from supabase import create_client  # type: ignore

    return create_client(url, key)


def plan_row_change(row: dict) -> tuple[str, str | None, str | None]:
    """Return (entity_type, field_name, new_value) or (et, None, None) if
    no change needed. field_name = 'stage' or 'status' depending on entity."""
    et = row.get("entity_type")
    data = row.get("data") or {}

    if et == "lead":
        cur = data.get("stage")
        if isinstance(cur, str) and cur in LEGACY_LEAD_MAP:
            return et, "stage", LEGACY_LEAD_MAP[cur]
        return et, None, None

    if et == "application":
        cur = data.get("status")
        if isinstance(cur, str) and cur in LEGACY_OPP_MAP:
            return et, "status", LEGACY_OPP_MAP[cur]
        return et, None, None

    if et == "offer":
        cur = data.get("stage")
        if isinstance(cur, str) and cur in LEGACY_OPP_MAP:
            return et, "stage", LEGACY_OPP_MAP[cur]
        return et, None, None

    return et or "?", None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="preview only; no writes")
    ap.add_argument("--tenant-id", default=SUNBIZ_TENANT_ID, help="tenant_id to backfill")
    args = ap.parse_args()

    sb = _supabase()

    rows_resp = (
        sb.table("tenant_records")
        .select("id, entity_type, data")
        .eq("tenant_id", args.tenant_id)
        .in_("entity_type", ["lead", "application", "offer"])
        .limit(2000)
        .execute()
    )
    rows = rows_resp.data or []
    _log(f"START backfill tenant={args.tenant_id} dry_run={args.dry_run} rows={len(rows)}")

    changes = []
    for row in rows:
        et, field, new_val = plan_row_change(row)
        if not field:
            continue
        old_val = (row.get("data") or {}).get(field)
        changes.append(
            {
                "id": row["id"],
                "entity_type": et,
                "field": field,
                "old": old_val,
                "new": new_val,
            }
        )

    if not changes:
        _log("NO_CHANGES — every row already on Salesforce-parity enum")
        return 0

    _log(f"PLANNED {len(changes)} change(s):")
    for c in changes:
        _log(f"  {c['entity_type']:12} {c['id']} {c['field']}: {c['old']!r} -> {c['new']!r}")

    if args.dry_run:
        _log("DRY_RUN — exiting without writes. Re-run without --dry-run to apply.")
        return 0

    written = 0
    for c in changes:
        # Re-read the row so we don't clobber concurrent edits.
        cur = (
            sb.table("tenant_records")
            .select("data")
            .eq("id", c["id"])
            .limit(1)
            .execute()
        )
        if not cur.data:
            _log(f"  SKIP {c['id']} (gone since plan)")
            continue
        data = cur.data[0].get("data") or {}
        if data.get(c["field"]) != c["old"]:
            _log(
                f"  SKIP {c['id']} (value changed since plan: "
                f"{data.get(c['field'])!r}, expected {c['old']!r})"
            )
            continue
        data[c["field"]] = c["new"]
        try:
            sb.table("tenant_records").update({"data": data}).eq("id", c["id"]).execute()
            written += 1
            _log(f"  WROTE {c['id']} {c['field']}: {c['old']!r} -> {c['new']!r}")
        except Exception as e:
            _log(f"  ERROR {c['id']}: {e}")

    _log(f"DONE — wrote {written}/{len(changes)} change(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
