"""daily_plan_generator.py — build today's daily_plan_items for the operator's Daily Plan tab.

Part of the SunBiz second-meeting (2026-05-25) expansion.
Migration dependency: 069 (adds daily_plan_items table + category enum to tenant schema).

Reads:
  - tenant_records (leads, applications, funded_deals)
  - application_lender_threads (offer_received status)
  - lead_documents (to check bank statement presence for shop_today category)
  - daily_plan_items (idempotency guard)

Writes:
  - daily_plan_items upserted on (tenant_id, plan_date, lead_id, category)
  - Deletes stale 'open' rows from prior days (cleanup pass)

Categories generated (in one pass per category per tenant):
  1. priority_call    — top 5 leads by score not contacted in 7+ days
  2. missing_info     — leads/applications with empty required fields or stage='missing_info'
  3. stuck            — applications at 'shopping' for 5+ days with no thread responses
  4. new_offer        — application_lender_threads at status='offer_received' not yet reviewed
  5. shop_today       — applications status='application_in' with bank statement but no threads
  6. renewal_eligible — funded deals at 40-50% through term (mirrors renewal_reminder logic)

Idempotency:
  - Upsert on (tenant_id, plan_date, lead_id, category) — safe to re-run multiple times per day.
  - Old 'open' rows from yesterday (or earlier) are deleted at the start of each run.

Environment:
  - DAILY_PLAN_TENANT_SLUG=sun  → restricts processing to the named tenant slug.
    Omit to process every tenant with an active manifest.

Schedule recommendation (cron):
  0 6 * * * cd /home/sunbiz && python scripts/daily_plan_generator.py once
Or via claude-bridge-ping cron poller with manifest key: daily_plan_generator_once

CLI:
  python scripts/daily_plan_generator.py once
  python scripts/daily_plan_generator.py loop --interval 86400
  python scripts/daily_plan_generator.py tail --count 50
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────
# Paths + constants
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
LOG_PATH = STATE_DIR / "daily_plan_generator.log"

DAEMON_NAME = "daily_plan_generator"

PRIORITY_CALL_LIMIT = 5
PRIORITY_CALL_DAYS_SINCE_CONTACT = 7
STUCK_APP_DAYS = 5
RENEWAL_WINDOW_LOW_PCT = 40.0
RENEWAL_WINDOW_HIGH_PCT = 50.0

# Required fields that, when missing, qualify a lead as 'missing_info'
REQUIRED_LEAD_FIELDS = {"monthly_revenue", "time_in_business_months", "fico"}


# ─────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] [{DAEMON_NAME}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    print(line.rstrip())


# ─────────────────────────────────────────────────────────────────────
# Env + Supabase client (service-role)
# ─────────────────────────────────────────────────────────────────────


def _load_env() -> dict[str, str]:
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
        return load_env()
    except Exception:
        return {}


def _supabase():
    env = _load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        _log("missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        return None
    try:
        from supabase import create_client  # type: ignore
        return create_client(url, key)
    except Exception as e:
        _log(f"supabase client init failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# Tenant resolution
# ─────────────────────────────────────────────────────────────────────


def _resolve_tenant_ids(sb, slug_filter: str) -> list[str]:
    try:
        q = sb.table("tenant_manifests").select("tenant_id, slug")
        if slug_filter:
            q = q.eq("slug", slug_filter)
        rows = q.execute()
        return [r["tenant_id"] for r in (rows.data or []) if r.get("tenant_id")]
    except Exception as e:
        _log(f"tenant resolution failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────
# Upsert helper
# ─────────────────────────────────────────────────────────────────────


def _upsert_item(
    sb,
    tenant_id: str,
    plan_date: str,
    lead_id: str,
    category: str,
    extra_data: Optional[dict[str, Any]] = None,
) -> bool:
    try:
        sb.table("daily_plan_items").upsert(
            {
                "tenant_id": tenant_id,
                "plan_date": plan_date,
                "lead_id": lead_id,
                "category": category,
                "status": "open",
                "source": "daily_plan_generator",
                "data": extra_data or {},
            },
            on_conflict="tenant_id,plan_date,lead_id,category",
        ).execute()
        return True
    except Exception as e:
        _log(f"upsert failed tenant={tenant_id} lead={lead_id} cat={category}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
# Stale-row cleanup (prior open items from earlier plan dates)
# ─────────────────────────────────────────────────────────────────────


def _cleanup_stale_rows(sb, tenant_id: str, today: str) -> int:
    """Delete open plan rows from before today. Returns count deleted."""
    try:
        result = (
            sb.table("daily_plan_items")
            .delete()
            .eq("tenant_id", tenant_id)
            .eq("status", "open")
            .lt("plan_date", today)
            .execute()
        )
        count = len(result.data) if result.data else 0
        return count
    except Exception as e:
        _log(f"cleanup failed tenant={tenant_id}: {e}")
        return 0


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _days_since(ts_iso: Optional[str]) -> Optional[float]:
    """Return days since the given ISO timestamp, or None if unparseable."""
    if not ts_iso:
        return None
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except (ValueError, AttributeError):
        return None


def _compute_term_progress(funded_at_iso: Optional[str], term_days: Any) -> Optional[float]:
    """Return fraction [0.0, 1.0+] through term, or None on bad inputs."""
    if not funded_at_iso or not isinstance(term_days, (int, float)) or term_days <= 0:
        return None
    try:
        funded_at = datetime.fromisoformat(funded_at_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    elapsed = (datetime.now(timezone.utc) - funded_at).total_seconds()
    return elapsed / (term_days * 86400.0)


def _has_missing_required(data: dict[str, Any]) -> bool:
    """True if any required field is absent, None, or empty-string."""
    for field in REQUIRED_LEAD_FIELDS:
        val = data.get(field)
        if val is None or val == "" or val == 0:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────
# Category 1: priority_call — top 5 leads not contacted in 7+ days
# ─────────────────────────────────────────────────────────────────────


def _gen_priority_call(sb, tenant_id: str, today: str) -> int:
    try:
        rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .order("data->score", desc=True)
            .execute()
        )
    except Exception as e:
        _log(f"priority_call fetch failed tenant={tenant_id}: {e}")
        return 0

    inserted = 0
    for row in rows.data or []:
        if inserted >= PRIORITY_CALL_LIMIT:
            break
        lead_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        days = _days_since(data.get("last_contacted_at"))
        if days is not None and days < PRIORITY_CALL_DAYS_SINCE_CONTACT:
            continue
        if _upsert_item(sb, tenant_id, today, lead_id, "priority_call", {
            "score": data.get("score"),
            "business_name": data.get("business_name"),
            "last_contacted_at": data.get("last_contacted_at"),
        }):
            inserted += 1

    return inserted


# ─────────────────────────────────────────────────────────────────────
# Category 2: missing_info
# ─────────────────────────────────────────────────────────────────────


def _gen_missing_info(sb, tenant_id: str, today: str) -> int:
    inserted = 0

    # Leads with stage='missing_info' or empty required fields
    try:
        lead_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .execute()
        )
    except Exception as e:
        _log(f"missing_info lead fetch failed tenant={tenant_id}: {e}")
        lead_rows = type("R", (), {"data": []})()

    for row in lead_rows.data or []:
        lead_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        if data.get("stage") == "missing_info" or _has_missing_required(data):
            if _upsert_item(sb, tenant_id, today, lead_id, "missing_info", {
                "stage": data.get("stage"),
                "business_name": data.get("business_name"),
                "missing_fields": [f for f in REQUIRED_LEAD_FIELDS if not data.get(f)],
            }):
                inserted += 1

    # Applications with status='missing_info'
    try:
        app_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "application")
            .execute()
        )
    except Exception as e:
        _log(f"missing_info app fetch failed tenant={tenant_id}: {e}")
        app_rows = type("R", (), {"data": []})()

    for row in app_rows.data or []:
        app_id = row.get("id", "")
        data = row.get("data") or {}
        if data.get("status") == "missing_info":
            if _upsert_item(sb, tenant_id, today, app_id, "missing_info", {
                "status": data.get("status"),
                "business_name": data.get("business_name"),
            }):
                inserted += 1

    return inserted


# ─────────────────────────────────────────────────────────────────────
# Category 3: stuck — applications at 'shopping' for 5+ days with no responses
# ─────────────────────────────────────────────────────────────────────


def _gen_stuck(sb, tenant_id: str, today: str) -> int:
    try:
        app_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "application")
            .execute()
        )
    except Exception as e:
        _log(f"stuck fetch failed tenant={tenant_id}: {e}")
        return 0

    # Gather application IDs that have at least one thread response
    try:
        responded_threads = (
            sb.table("application_lender_threads")
            .select("application_id")
            .eq("tenant_id", tenant_id)
            .not_.in_("status", ["sent", "no_response", "pending"])
            .execute()
        )
        has_response_ids = {r["application_id"] for r in (responded_threads.data or []) if r.get("application_id")}
    except Exception:
        has_response_ids = set()

    inserted = 0
    for row in app_rows.data or []:
        app_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        if data.get("status") != "shopping":
            continue
        if app_id in has_response_ids:
            continue
        days = _days_since(data.get("updated_at") or data.get("created_at"))
        if days is not None and days < STUCK_APP_DAYS:
            continue
        if _upsert_item(sb, tenant_id, today, app_id, "stuck", {
            "status": data.get("status"),
            "business_name": data.get("business_name"),
            "days_since_update": round(days, 1) if days is not None else None,
        }):
            inserted += 1

    return inserted


# ─────────────────────────────────────────────────────────────────────
# Category 4: new_offer — threads at offer_received not yet in today's plan
# ─────────────────────────────────────────────────────────────────────


def _gen_new_offer(sb, tenant_id: str, today: str) -> int:
    try:
        threads = (
            sb.table("application_lender_threads")
            .select("id, application_id, lender_id, data")
            .eq("tenant_id", tenant_id)
            .eq("status", "offer_received")
            .execute()
        )
    except Exception as e:
        _log(f"new_offer fetch failed tenant={tenant_id}: {e}")
        return 0

    # Check which thread IDs already have a plan item today (use thread id as lead_id key)
    try:
        existing = (
            sb.table("daily_plan_items")
            .select("lead_id")
            .eq("tenant_id", tenant_id)
            .eq("plan_date", today)
            .eq("category", "new_offer")
            .execute()
        )
        existing_ids = {r["lead_id"] for r in (existing.data or [])}
    except Exception:
        existing_ids = set()

    inserted = 0
    for thread in threads.data or []:
        thread_id = thread.get("id", "")
        if thread_id in existing_ids:
            continue
        thread_data = thread.get("data") or {}
        if _upsert_item(sb, tenant_id, today, thread_id, "new_offer", {
            "application_id": thread.get("application_id"),
            "lender_id": thread.get("lender_id"),
            "offer_summary": thread_data.get("offer_summary"),
        }):
            inserted += 1

    return inserted


# ─────────────────────────────────────────────────────────────────────
# Category 5: shop_today — applications with bank statement but no threads
# ─────────────────────────────────────────────────────────────────────


def _gen_shop_today(sb, tenant_id: str, today: str) -> int:
    try:
        app_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "application")
            .execute()
        )
    except Exception as e:
        _log(f"shop_today app fetch failed tenant={tenant_id}: {e}")
        return 0

    # Applications that already have threads queued
    try:
        threaded = (
            sb.table("application_lender_threads")
            .select("application_id")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        threaded_ids = {r["application_id"] for r in (threaded.data or []) if r.get("application_id")}
    except Exception:
        threaded_ids = set()

    # Applications with at least one bank_statement document
    try:
        docs = (
            sb.table("lead_documents")
            .select("application_id")
            .eq("tenant_id", tenant_id)
            .eq("document_type", "bank_statements_3mo")
            .execute()
        )
        has_bank_statement = {r["application_id"] for r in (docs.data or []) if r.get("application_id")}
    except Exception:
        # Fallback: check via tenant_records storage pattern in data blob
        has_bank_statement = set()

    inserted = 0
    for row in app_rows.data or []:
        app_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        if data.get("status") != "application_in":
            continue
        if app_id in threaded_ids:
            continue

        # Check bank statement presence: from lead_documents table OR from data blob
        has_doc = app_id in has_bank_statement
        if not has_doc:
            # Fallback: check data.documents list
            docs_list = data.get("documents") or []
            has_doc = any(
                isinstance(d, dict) and d.get("type") in (
                    "bank_statements_3mo", "bank_statement"
                )
                for d in docs_list
            )
        if not has_doc:
            continue

        if _upsert_item(sb, tenant_id, today, app_id, "shop_today", {
            "status": data.get("status"),
            "business_name": data.get("business_name"),
        }):
            inserted += 1

    return inserted


# ─────────────────────────────────────────────────────────────────────
# Category 6: renewal_eligible — funded deals at 40-50% through term
#   (mirrors renewal_reminder.py logic so the two daemons agree)
# ─────────────────────────────────────────────────────────────────────


def _gen_renewal_eligible(sb, tenant_id: str, today: str) -> int:
    try:
        rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "funded_deal")
            .execute()
        )
    except Exception as e:
        _log(f"renewal_eligible fetch failed tenant={tenant_id}: {e}")
        return 0

    # Resolve per-tenant threshold
    try:
        manifests = (
            sb.table("tenant_manifests")
            .select("settings")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        settings = (manifests.data[0].get("settings") or {}) if manifests.data else {}
        threshold_pct = float(settings.get("renewal_eligibility_threshold_pct") or RENEWAL_WINDOW_LOW_PCT)
    except Exception:
        threshold_pct = RENEWAL_WINDOW_LOW_PCT

    inserted = 0
    for row in rows.data or []:
        deal_id = row.get("id", "")
        data: dict[str, Any] = row.get("data") or {}
        if data.get("status") != "funded":
            continue
        term_days = data.get("term_days")
        progress = _compute_term_progress(data.get("funded_at"), term_days)
        if progress is None:
            continue
        progress_pct = progress * 100.0
        if not (threshold_pct <= progress_pct <= RENEWAL_WINDOW_HIGH_PCT):
            continue
        if _upsert_item(sb, tenant_id, today, deal_id, "renewal_eligible", {
            "progress_pct": round(progress_pct, 1),
            "term_days": term_days,
            "business_name": data.get("business_name"),
            "funded_amount": data.get("funded_amount"),
            "lender_name": data.get("lender_name"),
        }):
            inserted += 1

    return inserted


# ─────────────────────────────────────────────────────────────────────
# Core tick
# ─────────────────────────────────────────────────────────────────────


def tick() -> int:
    sb = _supabase()
    if not sb:
        _log("supabase unavailable — skipping tick")
        return 0

    env = _load_env()
    slug_filter = (env.get("DAILY_PLAN_TENANT_SLUG") or "").strip()

    tenant_ids = _resolve_tenant_ids(sb, slug_filter)
    if not tenant_ids:
        _log("no tenants found — nothing to process")
        return 0

    today = date.today().isoformat()
    grand_total = 0

    for tid in tenant_ids:
        # Cleanup stale open rows first
        cleaned = _cleanup_stale_rows(sb, tid, today)
        if cleaned:
            _log(f"tenant={tid[:8]}...: purged {cleaned} stale open rows from prior days")

        counts = {
            "priority_call": _gen_priority_call(sb, tid, today),
            "missing_info": _gen_missing_info(sb, tid, today),
            "stuck": _gen_stuck(sb, tid, today),
            "new_offer": _gen_new_offer(sb, tid, today),
            "shop_today": _gen_shop_today(sb, tid, today),
            "renewal_eligible": _gen_renewal_eligible(sb, tid, today),
        }
        total = sum(counts.values())
        grand_total += total
        _log(
            f"tenant={tid[:8]}..., date={today}: "
            f"{counts['priority_call']} priority calls, "
            f"{counts['missing_info']} missing info, "
            f"{counts['stuck']} stuck, "
            f"{counts['new_offer']} new offers, "
            f"{counts['shop_today']} shop today, "
            f"{counts['renewal_eligible']} renewal eligible"
        )

    _log(f"tick complete — {grand_total} total plan items upserted")
    return grand_total


# ─────────────────────────────────────────────────────────────────────
# Daemon subcommands
# ─────────────────────────────────────────────────────────────────────


def loop(interval: int) -> int:
    interval = max(3600, int(interval))
    _log(f"daily_plan_generator up; tick interval = {interval}s")
    while True:
        try:
            tick()
        except Exception as e:
            _log(f"tick crashed: {e}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("daily_plan_generator shutting down (SIGINT)")
            return 0


def tail_cmd(count: int) -> int:
    if not LOG_PATH.exists():
        print("(no log yet)")
        return 0
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-count:]
    except OSError as e:
        print(f"read failed: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="daily_plan_generator — build today's operator Daily Plan"
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("once", help="Run one tick and exit").set_defaults(
        func=lambda _a: 0 if tick() is not None else 1
    )

    lp = sub.add_parser("loop", help="Run continuously")
    lp.add_argument(
        "--interval",
        type=int,
        default=86400,
        help="seconds between ticks (default: 86400 = 24h)",
    )
    lp.set_defaults(func=lambda a: loop(a.interval))

    tl = sub.add_parser("tail", help="Print the last N log lines")
    tl.add_argument("--count", type=int, default=50)
    tl.set_defaults(func=lambda a: tail_cmd(a.count))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
