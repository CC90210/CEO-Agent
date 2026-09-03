#!/usr/bin/env python3
"""sync_mrr.py — daily MRR auto-sync from revenue_engine to Turso.

Computes Net MRR via revenue_engine.calculate_mrr() (Stripe subscriptions
+ manual retainer entries from revenue_events) and writes the result to
two Turso locations so the OASIS Agent Command Center dashboard
self-heals every day without operator intervention:

  1. user_profiles.mrr_current_usd  — drives the live "Net MRR" widget.
     The Vercel dashboard reads this on every page load.
  2. mrr_snapshots (one row per tenant per day) — drives the 30-day
     trajectory chart. Backstops the Vercel snapshot-mrr cron, which
     has been silently 401-ing since 2026-05-08 when a CRON_SECRET
     auth gate landed.

Idempotent. Safe to re-run. Designed to be invoked by cron_engine.py
SEED_JOBS at 03:30 UTC daily — early enough that the (eventually-fixed)
Vercel snapshot at 04:00 UTC sees today's value if it fires, but
self-sufficient if Vercel stays broken.

Usage:
    python scripts/core/sync_mrr.py                        # CC's tenant, write
    python scripts/core/sync_mrr.py --dry-run              # compute + report, no write
    python scripts/core/sync_mrr.py --operator other@x.io  # different operator
    python scripts/core/sync_mrr.py --json                 # machine-readable output
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from revenue_engine import calculate_mrr, get_supabase, load_env  # type: ignore[import-not-found]


def sync(operator_email: str, *, dry_run: bool, as_json: bool) -> dict:
    env = load_env()
    db = get_supabase(env)

    mrr = calculate_mrr(env, db)
    total = float(mrr["total_mrr"])
    today = dt.date.today().isoformat()

    # Refuse to launder a degraded read into the system of record. The manual
    # component is ~99% of total MRR, so when revenue_engine could only carry
    # it forward from a snapshot, writing that figure to
    # user_profiles.mrr_current_usd would make a stale number indistinguishable
    # from a live one for Atlas and every dashboard downstream. Nothing is lost
    # by skipping — the cached value is what is already on file — and failing
    # here surfaces via the hourly cron health check instead of going quiet.
    manual_stale = mrr.get("manual_stale")
    if manual_stale:
        result = {"ok": False, "error": f"refusing to write degraded MRR — {manual_stale}",
                  "total_mrr": total, "manual_stale": manual_stale}
        print(json.dumps(result) if as_json
              else f"ERROR: {result['error']}", file=sys.stderr)
        return result

    profile_q = (
        db.table("user_profiles")
        .select("id,tenant_id,mrr_current_usd,mrr_target_usd")
        .eq("email", operator_email)
        .limit(1)
        .execute()
    )
    if not profile_q.data:
        result = {"ok": False, "error": f"no user_profiles row for email={operator_email}"}
        print(json.dumps(result) if as_json else f"ERROR: {result['error']}", file=sys.stderr)
        return result

    profile = profile_q.data[0]
    previous = float(profile.get("mrr_current_usd") or 0)
    tenant_id = profile["tenant_id"]
    changed = abs(previous - total) > 0.005

    snapshot_payload = {
        "tenant_id": tenant_id,
        "snapshot_date": today,
        "mrr_usd": total,
        "target_usd": float(profile.get("mrr_target_usd") or 10000),
        "source": "sync_mrr",
        "metadata": {
            "stripe_mrr": mrr["stripe_mrr"],
            "manual_mrr": mrr["manual_mrr"],
            "note": "Auto-synced by scripts/core/sync_mrr.py",
        },
    }

    if not dry_run:
        if changed:
            db.table("user_profiles").update({"mrr_current_usd": total}).eq("id", profile["id"]).execute()
        existing_snap = (
            db.table("mrr_snapshots")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("snapshot_date", today)
            .limit(1)
            .execute()
        )
        if existing_snap.data:
            db.table("mrr_snapshots").update(snapshot_payload).eq("id", existing_snap.data[0]["id"]).execute()
        else:
            db.table("mrr_snapshots").insert(snapshot_payload).execute()

    result = {
        "ok": True,
        "operator_email": operator_email,
        "tenant_id": tenant_id,
        "dry_run": dry_run,
        "previous_mrr_current_usd": previous,
        "new_mrr_current_usd": total,
        "changed": changed,
        "snapshot_date": today,
        "breakdown": {
            "stripe_mrr": mrr["stripe_mrr"],
            "manual_mrr": mrr["manual_mrr"],
        },
    }
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        verb = "DRY-RUN" if dry_run else ("CHANGED" if changed else "no-op")
        print(
            f"sync_mrr [{verb}] {operator_email}: "
            f"${previous:.2f} -> ${total:.2f} "
            f"(stripe ${mrr['stripe_mrr']:.2f} + manual ${mrr['manual_mrr']:.2f}) "
            f"snapshot={today}"
        )
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Sync revenue_engine MRR -> user_profiles + mrr_snapshots.")
    p.add_argument(
        "--operator",
        default=os.environ.get("OPERATOR_EMAIL", "conaugh@oasisai.work"),
        help="Operator email (defaults to OPERATOR_EMAIL env or conaugh@oasisai.work)",
    )
    p.add_argument("--dry-run", action="store_true", help="Compute + report; do not write")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()
    result = sync(args.operator, dry_run=args.dry_run, as_json=args.json)
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
