"""
Revenue Engine - OASIS Business Operations CLI
Combines Stripe subscription data with Supabase manual tracking.
All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/revenue_engine.py mrr
  python scripts/revenue_engine.py dashboard
  python scripts/revenue_engine.py sync-stripe
  python scripts/revenue_engine.py log-revenue --type payment --amount 500 --source manual --client "Bennett" --notes "March retainer"
  python scripts/revenue_engine.py log-month --month 2026-03 --mrr 2691 --new-clients 0 --churned 0 --pipeline 5000 --leads 50
  python scripts/revenue_engine.py history [--months 6]
  python scripts/revenue_engine.py forecast
  python scripts/revenue_engine.py clients
  python scripts/revenue_engine.py goal
  python scripts/revenue_engine.py --json <any command>
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

# -- Constants -----------------------------------------------------------------

MRR_GOAL_USD = 5000.0
STRIPE_API = "https://api.stripe.com/v1"

# Stripe events we care about for sync
REVENUE_EVENT_TYPES = {
    "charge.succeeded",
    "invoice.paid",
    "customer.subscription.created",
    "customer.subscription.deleted",
}


# -- Credential loading ---------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root. Exits on missing file."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars: dict[str, str] = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


# -- Stripe client --------------------------------------------------------------

class StripeUnavailable(Exception):
    """Raised when Stripe credentials are absent or requests fail."""


def _stripe_get(secret_key: str, endpoint: str, params: dict | None = None, account_id: str | None = None) -> dict:
    """GET from Stripe REST API. Raises StripeUnavailable on any failure."""
    try:
        import requests
    except ImportError:
        raise StripeUnavailable("'requests' package not installed")

    headers = {"Stripe-Version": "2025-01-27.acacia"}
    if account_id:
        headers["Stripe-Account"] = account_id

    try:
        resp = requests.get(
            f"{STRIPE_API}/{endpoint}",
            auth=(secret_key, ""),
            headers=headers,
            params=params or {},
            timeout=15,
        )
    except Exception as exc:
        raise StripeUnavailable(f"Network error: {exc}") from exc

    if resp.status_code != 200:
        error_msg = resp.json().get("error", {}).get("message", resp.text[:200])
        raise StripeUnavailable(f"Stripe {resp.status_code}: {error_msg}")

    return resp.json()


def _stripe_get_all(secret_key: str, endpoint: str, params: dict | None = None, account_id: str | None = None) -> list[dict]:
    """Auto-paginate a Stripe list endpoint, returning all items."""
    items: list[dict] = []
    p = dict(params or {})
    p.setdefault("limit", 100)

    while True:
        page = _stripe_get(secret_key, endpoint, p, account_id=account_id)
        items.extend(page.get("data", []))
        if not page.get("has_more"):
            break
        p["starting_after"] = page["data"][-1]["id"]

    return items


# -- Supabase client ------------------------------------------------------------

def get_supabase(env_vars: dict[str, str]):
    """Return a Supabase client for the bravo project. Exits on missing credentials."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: 'supabase' package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print(
            "ERROR: BRAVO_SUPABASE_URL and BRAVO_SUPABASE_SERVICE_ROLE_KEY required in .env.agents",
            file=sys.stderr,
        )
        sys.exit(1)

    return create_client(url, key)


# -- MRR calculation ------------------------------------------------------------

def _mrr_from_stripe(secret_key: str, account_id: str | None = None) -> tuple[float, list[dict]]:
    """
    Pull active Stripe subscriptions and return (total_mrr_usd, subscription_rows).
    Converts annual billing to a monthly equivalent.
    """
    subs = _stripe_get_all(secret_key, "subscriptions", {"status": "active"}, account_id=account_id)
    rows: list[dict] = []
    total = 0.0

    for sub in subs:
        customer = sub.get("customer", "")
        customer_email = sub.get("customer_email") or ""

        for item in sub.get("items", {}).get("data", []):
            price = item.get("price", {})
            unit_amount = price.get("unit_amount") or 0
            currency = price.get("currency", "usd")
            interval = (price.get("recurring") or {}).get("interval", "month")
            interval_count = (price.get("recurring") or {}).get("interval_count", 1)

            # Normalise to USD (Stripe amounts are in cents)
            # CAD->USD approximate rate (updated periodically)
            CAD_TO_USD = 0.72  # Conservative estimate
            amount_cents = unit_amount * item.get("quantity", 1)

            if interval == "year":
                monthly_local = (amount_cents / 100) / (12 * interval_count)
            elif interval == "month":
                monthly_local = (amount_cents / 100) / interval_count
            elif interval == "week":
                monthly_local = (amount_cents / 100) * (52 / 12) / interval_count
            else:
                monthly_local = amount_cents / 100

            # Convert non-USD currencies
            if currency.lower() == "cad":
                monthly_usd = monthly_local * CAD_TO_USD
            elif currency.lower() == "usd":
                monthly_usd = monthly_local
            else:
                monthly_usd = monthly_local  # Fallback: treat as USD

            total += monthly_usd
            rows.append({
                "subscription_id": sub["id"],
                "customer_id": customer,
                "customer_email": customer_email,
                "monthly_usd": round(monthly_usd, 2),
                "interval": interval,
                "currency": currency,
                "status": sub.get("status"),
            })

    return round(total, 2), rows


def _mrr_manual_from_supabase(db) -> float:
    """
    Sum manual recurring entries from revenue_events:
    type='subscription_start' with no matching 'subscription_cancel' for the same client.
    Falls back to 0.0 if table does not exist.
    """
    try:
        starts = (
            db.table("revenue_events")
            .select("client_name, amount_usd, metadata")
            .eq("type", "subscription_start")
            .execute()
        )
        cancels = (
            db.table("revenue_events")
            .select("client_name")
            .eq("type", "subscription_cancel")
            .execute()
        )

        cancelled_clients = {row["client_name"] for row in (cancels.data or [])}

        total = sum(
            float(row["amount_usd"] or 0)
            for row in (starts.data or [])
            if row["client_name"] not in cancelled_clients
        )
        return round(total, 2)
    except Exception:
        return 0.0


def calculate_mrr(env_vars: dict[str, str], db) -> dict:
    """
    Returns a dict with stripe_mrr, manual_mrr, total_mrr, stripe_available, stripe_subs.
    Stripe failure is non-fatal - falls back to Supabase-only data.
    """
    stripe_mrr = 0.0
    stripe_subs: list[dict] = []
    stripe_available = False
    stripe_error = ""

    # Try org key + OASIS account first (org keys don't expire like secret keys)
    org_key = env_vars.get("STRIPE_ORG_KEY")
    oasis_acct = env_vars.get("STRIPE_OASIS_ACCT_ID")
    stripe_key = env_vars.get("STRIPE_SECRET_KEY")

    if org_key and oasis_acct:
        try:
            stripe_mrr, stripe_subs = _mrr_from_stripe(org_key, account_id=oasis_acct)
            stripe_available = True
        except StripeUnavailable as exc:
            stripe_error = f"Org key failed: {exc}"
    if not stripe_available and stripe_key:
        try:
            stripe_mrr, stripe_subs = _mrr_from_stripe(stripe_key)
            stripe_available = True
            stripe_error = ""
        except StripeUnavailable as exc:
            stripe_error = str(exc)
    if not stripe_available and not stripe_error:
        stripe_error = "No Stripe keys configured in .env.agents"

    manual_mrr = _mrr_manual_from_supabase(db)
    total_mrr = round(stripe_mrr + manual_mrr, 2)

    return {
        "stripe_mrr": stripe_mrr,
        "manual_mrr": manual_mrr,
        "total_mrr": total_mrr,
        "stripe_available": stripe_available,
        "stripe_error": stripe_error,
        "stripe_subs": stripe_subs,
    }


# -- Pipeline + lead stats from Supabase ---------------------------------------

def _pipeline_stats(db) -> dict:
    """Read pipeline and lead summary from monthly_metrics (most recent month)."""
    try:
        result = (
            db.table("monthly_metrics")
            .select("*")
            .order("month", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return {
                "pipeline": float(row.get("pipeline_value") or 0),
                "leads": int(row.get("total_leads") or 0),
                "conversion_rate": float(row.get("conversion_rate") or 0),
                "avg_deal_size": float(row.get("avg_deal_size") or 0),
                "month": row.get("month", ""),
            }
    except Exception:
        pass
    return {"pipeline": 0.0, "leads": 0, "conversion_rate": 0.0, "avg_deal_size": 0.0, "month": ""}


def _last_payment(db) -> dict:
    """Return the most recent succeeded payment from revenue_events."""
    try:
        result = (
            db.table("revenue_events")
            .select("amount_usd, client_name, created_at")
            .eq("type", "payment")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return {
                "amount": float(row.get("amount_usd") or 0),
                "client": row.get("client_name", "unknown"),
                "date": (row.get("created_at") or "")[:10],
            }
    except Exception:
        pass
    return {"amount": 0.0, "client": "-", "date": "-"}


# -- Command: mrr --------------------------------------------------------------

def cmd_mrr(env_vars: dict[str, str], db, args) -> dict:
    mrr = calculate_mrr(env_vars, db)

    if getattr(args, "output_json", False):
        return mrr

    print("=== MRR Breakdown ===\n")
    if mrr["stripe_available"]:
        print(f"  Stripe MRR:  ${mrr['stripe_mrr']:,.2f}  ({len(mrr['stripe_subs'])} active subscription(s))")
    else:
        print(f"  Stripe MRR:  unavailable - {mrr['stripe_error']}")
    print(f"  Manual MRR:  ${mrr['manual_mrr']:,.2f}  (Supabase tracked)")
    print(f"  -------------------------------------")
    print(f"  Total MRR:   ${mrr['total_mrr']:,.2f}")
    gap = max(0.0, MRR_GOAL_USD - mrr["total_mrr"])
    pct = (mrr["total_mrr"] / MRR_GOAL_USD * 100) if MRR_GOAL_USD else 0
    print(f"\n  Goal:        ${MRR_GOAL_USD:,.0f}  ({pct:.1f}% there)")
    if gap > 0:
        avg = mrr["total_mrr"] / max(len(mrr["stripe_subs"]), 1)
        clients_needed = int(gap / avg) + 1 if avg else "?"
        print(f"  Gap:         ${gap:,.2f} - need ~{clients_needed} clients at ${avg:,.0f}/mo avg")
    return mrr


# -- Command: dashboard --------------------------------------------------------

def cmd_dashboard(env_vars: dict[str, str], db, args) -> dict:
    mrr = calculate_mrr(env_vars, db)
    pipeline = _pipeline_stats(db)
    last = _last_payment(db)

    gap = max(0.0, MRR_GOAL_USD - mrr["total_mrr"])
    pct = (mrr["total_mrr"] / MRR_GOAL_USD * 100) if MRR_GOAL_USD else 0
    avg_deal = pipeline["avg_deal_size"] or (mrr["total_mrr"] / max(len(mrr["stripe_subs"]), 1))
    clients_needed = int(gap / avg_deal) + 1 if avg_deal else "?"

    data = {
        "mrr": mrr["total_mrr"],
        "mrr_goal": MRR_GOAL_USD,
        "mrr_pct": round(pct, 1),
        "gap": round(gap, 2),
        "clients_needed": clients_needed,
        "avg_deal": round(avg_deal, 2),
        "pipeline": pipeline["pipeline"],
        "leads": pipeline["leads"],
        "conversion_rate": pipeline["conversion_rate"],
        "last_payment": last,
        "stripe_available": mrr["stripe_available"],
    }

    if getattr(args, "output_json", False):
        return data

    print("=== OASIS Revenue Dashboard ===\n")
    stripe_note = "" if mrr["stripe_available"] else "  [Stripe unavailable - Supabase only]"
    print(f"  MRR:         ${mrr['total_mrr']:,.2f} / ${MRR_GOAL_USD:,.0f}  ({pct:.1f}%){stripe_note}")
    if gap > 0:
        print(f"  Gap:         ${gap:,.2f} - need ~{clients_needed} clients at ${avg_deal:,.0f}/mo avg")
    else:
        print(f"  Goal reached! ${mrr['total_mrr']:,.2f} MRR")

    if pipeline["pipeline"] > 0:
        print(f"  Pipeline:    ${pipeline['pipeline']:,.0f}  ({pipeline['leads']} leads)")
    if pipeline["conversion_rate"] > 0:
        print(f"  Conversion:  {pipeline['conversion_rate']:.1f}%")

    if last["amount"] > 0:
        print(f"  Last Payment: ${last['amount']:,.2f} from {last['client']} on {last['date']}")
    else:
        print(f"  Last Payment: none recorded")

    return data


# -- Command: sync-stripe ------------------------------------------------------

def cmd_sync_stripe(env_vars: dict[str, str], db, args) -> dict:
    org_key = env_vars.get("STRIPE_ORG_KEY")
    oasis_acct = env_vars.get("STRIPE_OASIS_ACCT_ID")
    stripe_key = env_vars.get("STRIPE_SECRET_KEY")

    # Prefer org key (doesn't expire)
    if org_key and oasis_acct:
        active_key = org_key
        active_acct = oasis_acct
    elif stripe_key:
        active_key = stripe_key
        active_acct = None
    else:
        msg = "No Stripe keys configured in .env.agents - cannot sync"
        if getattr(args, "output_json", False):
            return {"error": msg, "inserted": 0}
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    try:
        events = _stripe_get_all(active_key, "events", {"limit": 100}, account_id=active_acct)
    except StripeUnavailable as exc:
        msg = str(exc)
        if getattr(args, "output_json", False):
            return {"error": msg, "inserted": 0}
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Map Stripe event types to our revenue_events types
    type_map = {
        "charge.succeeded": "payment",
        "invoice.paid": "invoice_paid",
        "customer.subscription.created": "subscription_start",
        "customer.subscription.deleted": "subscription_cancel",
    }

    inserted = 0
    skipped = 0
    errors = 0

    for event in events:
        event_type = event.get("type", "")
        if event_type not in REVENUE_EVENT_TYPES:
            continue

        obj = event.get("data", {}).get("object", {})
        stripe_event_id = event.get("id", "")
        created_ts = event.get("created", 0)
        created_at = datetime.datetime.utcfromtimestamp(created_ts).isoformat() + "Z"

        # Derive amount in USD
        amount_usd = 0.0
        if event_type in ("charge.succeeded", "invoice.paid"):
            cents = obj.get("amount_paid") or obj.get("amount") or 0
            amount_usd = round(cents / 100, 2)

        # Derive client info
        client_email = (
            obj.get("customer_email")
            or obj.get("receipt_email")
            or ""
        )
        client_name = obj.get("customer_name") or obj.get("description") or ""

        row = {
            "type": type_map[event_type],
            "amount_usd": amount_usd,
            "source": "stripe",
            "client_name": client_name,
            "client_email": client_email,
            "stripe_event_id": stripe_event_id,
            "metadata": json.dumps({"stripe_type": event_type, "object_id": obj.get("id", "")}),
            "created_at": created_at,
        }

        try:
            db.table("revenue_events").insert(row).execute()
            inserted += 1
        except Exception as exc:
            err_str = str(exc)
            # Duplicate stripe_event_id - UNIQUE constraint fires - safe to skip
            if "duplicate" in err_str.lower() or "unique" in err_str.lower():
                skipped += 1
            else:
                errors += 1

    result = {"inserted": inserted, "skipped_duplicates": skipped, "errors": errors}

    if getattr(args, "output_json", False):
        return result

    print(f"Stripe sync complete.")
    print(f"  Inserted: {inserted} new event(s)")
    print(f"  Skipped:  {skipped} duplicate(s)")
    if errors:
        print(f"  Errors:   {errors}")
    return result


# -- Command: log-revenue ------------------------------------------------------

def cmd_log_revenue(env_vars: dict[str, str], db, args) -> dict:
    row = {
        "type": args.type,
        "amount_usd": float(args.amount),
        "source": args.source,
        "client_name": args.client or "",
        "client_email": args.email or "",
        "stripe_event_id": None,
        "metadata": json.dumps({"notes": args.notes or ""}),
    }

    result = db.table("revenue_events").insert(row).execute()
    inserted = result.data[0] if result.data else row

    if getattr(args, "output_json", False):
        return inserted

    print(f"Revenue event logged.")
    print(f"  Type:   {args.type}")
    print(f"  Amount: ${float(args.amount):,.2f}")
    print(f"  Client: {args.client or '-'}")
    if args.notes:
        print(f"  Notes:  {args.notes}")
    return inserted


# -- Command: log-month --------------------------------------------------------

def cmd_log_month(env_vars: dict[str, str], db, args) -> dict:
    total_leads = args.leads or 0
    new_clients = args.new_clients or 0
    conversion = round((new_clients / total_leads * 100), 1) if total_leads > 0 else 0.0
    avg_deal = round(args.mrr / new_clients, 2) if new_clients > 0 else 0.0

    row = {
        "month": args.month + "-01" if len(args.month) == 7 else args.month,
        "mrr": float(args.mrr),
        "new_clients": new_clients,
        "churned_clients": args.churned or 0,
        "pipeline_value": float(args.pipeline or 0),
        "total_leads": total_leads,
        "conversion_rate": conversion,
        "avg_deal_size": avg_deal,
    }

    result = (
        db.table("monthly_metrics")
        .upsert(row, on_conflict="month")
        .execute()
    )
    saved = result.data[0] if result.data else row

    if getattr(args, "output_json", False):
        return saved

    print(f"Monthly metrics saved for {args.month}.")
    print(f"  MRR:        ${float(args.mrr):,.2f}")
    print(f"  New clients: {new_clients}")
    print(f"  Churned:     {args.churned or 0}")
    print(f"  Pipeline:    ${float(args.pipeline or 0):,.2f}")
    print(f"  Leads:       {total_leads}")
    print(f"  Conversion:  {conversion:.1f}%")
    return saved


# -- Command: history ----------------------------------------------------------

def cmd_history(env_vars: dict[str, str], db, args) -> list[dict]:
    months = getattr(args, "months", 6)

    try:
        result = (
            db.table("monthly_metrics")
            .select("*")
            .order("month", desc=True)
            .limit(months)
            .execute()
        )
        rows = list(reversed(result.data or []))
    except Exception as exc:
        if getattr(args, "output_json", False):
            return []
        print(f"ERROR reading monthly_metrics: {exc}", file=sys.stderr)
        return []

    if getattr(args, "output_json", False):
        return rows

    if not rows:
        print("No monthly history recorded yet.")
        print("  Use: python scripts/revenue_engine.py log-month --month 2026-03 --mrr 2691 ...")
        return rows

    print(f"=== Monthly MRR History (last {months} months) ===\n")
    print(f"  {'Month':<10}  {'MRR':>9}  {'New':>4}  {'Churn':>5}  {'Pipeline':>10}  {'Leads':>5}  {'Conv%':>6}")
    print(f"  {'-'*10}  {'-'*9}  {'-'*4}  {'-'*5}  {'-'*10}  {'-'*5}  {'-'*6}")
    for row in rows:
        print(
            f"  {row.get('month',''):<10}  "
            f"${float(row.get('mrr') or 0):>8,.2f}  "
            f"{int(row.get('new_clients') or 0):>4}  "
            f"{int(row.get('churned_clients') or 0):>5}  "
            f"${float(row.get('pipeline_value') or 0):>9,.0f}  "
            f"{int(row.get('total_leads') or 0):>5}  "
            f"{float(row.get('conversion_rate') or 0):>5.1f}%"
        )
    return rows


# -- Command: forecast ---------------------------------------------------------

def cmd_forecast(env_vars: dict[str, str], db, args) -> dict:
    mrr_data = calculate_mrr(env_vars, db)
    pipeline = _pipeline_stats(db)

    current_mrr = mrr_data["total_mrr"]
    pipeline_val = pipeline["pipeline"]
    conversion = pipeline["conversion_rate"] / 100 if pipeline["conversion_rate"] else 0.10

    # Weighted pipeline contribution: pipeline * conversion_rate
    pipeline_mrr = round(pipeline_val * conversion, 2)
    projected_mrr = round(current_mrr + pipeline_mrr, 2)
    gap = max(0.0, MRR_GOAL_USD - projected_mrr)

    # Months to goal at current net new MRR rate
    # Use last 3 months avg growth from history if available
    try:
        history = (
            db.table("monthly_metrics")
            .select("mrr, new_clients")
            .order("month", desc=True)
            .limit(3)
            .execute()
        )
        rows = history.data or []
        if len(rows) >= 2:
            mrrs = [float(r.get("mrr") or 0) for r in rows]
            avg_monthly_growth = (mrrs[0] - mrrs[-1]) / (len(mrrs) - 1)
        else:
            avg_monthly_growth = 0.0
    except Exception:
        avg_monthly_growth = 0.0

    months_to_goal = None
    if avg_monthly_growth > 0 and gap > 0:
        months_to_goal = int(gap / avg_monthly_growth) + 1

    result = {
        "current_mrr": current_mrr,
        "pipeline_mrr": pipeline_mrr,
        "projected_mrr": projected_mrr,
        "gap_after_pipeline": round(gap, 2),
        "avg_monthly_growth": round(avg_monthly_growth, 2),
        "months_to_goal": months_to_goal,
        "goal": MRR_GOAL_USD,
    }

    if getattr(args, "output_json", False):
        return result

    print("=== MRR Forecast ===\n")
    print(f"  Current MRR:          ${current_mrr:,.2f}")
    print(f"  Pipeline contribution: ${pipeline_mrr:,.2f}  ({pipeline_val:,.0f} pipeline x {conversion*100:.0f}% conversion)")
    print(f"  Projected MRR:        ${projected_mrr:,.2f}")
    print(f"  Remaining gap:        ${gap:,.2f}")
    if avg_monthly_growth > 0:
        print(f"  Avg monthly growth:   ${avg_monthly_growth:,.2f}/mo  (3-month avg)")
    if months_to_goal is not None:
        target_date = datetime.date.today() + datetime.timedelta(days=30 * months_to_goal)
        print(f"  At this rate:         ~{months_to_goal} month(s) to goal  ({target_date.strftime('%B %Y')})")
    else:
        print(f"  Growth rate unknown - log more monthly history to forecast timeline")

    return result


# -- Command: clients ----------------------------------------------------------

def cmd_clients(env_vars: dict[str, str], db, args) -> list[dict]:
    org_key = env_vars.get("STRIPE_ORG_KEY")
    oasis_acct = env_vars.get("STRIPE_OASIS_ACCT_ID")
    stripe_key = env_vars.get("STRIPE_SECRET_KEY")
    clients: list[dict] = []
    stripe_subs_fetched = False

    if org_key and oasis_acct:
        try:
            _, subs = _mrr_from_stripe(org_key, account_id=oasis_acct)
            stripe_subs_fetched = True
        except StripeUnavailable:
            pass
    if not stripe_subs_fetched and stripe_key:
        try:
            _, subs = _mrr_from_stripe(stripe_key)
            stripe_subs_fetched = True
        except StripeUnavailable:
            pass
    if stripe_subs_fetched:
        for sub in subs:
            clients.append({
                "source": "stripe",
                "client": sub["customer_email"] or sub["customer_id"],
                "monthly_usd": sub["monthly_usd"],
                "status": sub["status"],
                "subscription_id": sub["subscription_id"],
            })
    elif not getattr(args, "output_json", False):
        print("  [Stripe unavailable]")

    # Also pull manual subscription_start from Supabase
    try:
        result = (
            db.table("revenue_events")
            .select("client_name, client_email, amount_usd, created_at")
            .eq("type", "subscription_start")
            .order("created_at", desc=True)
            .execute()
        )
        cancels = (
            db.table("revenue_events")
            .select("client_name")
            .eq("type", "subscription_cancel")
            .execute()
        )
        cancelled = {r["client_name"] for r in (cancels.data or [])}

        for row in (result.data or []):
            if row["client_name"] not in cancelled:
                clients.append({
                    "source": "manual",
                    "client": row.get("client_name") or row.get("client_email") or "unknown",
                    "monthly_usd": float(row.get("amount_usd") or 0),
                    "status": "active",
                    "subscription_id": None,
                })
    except Exception:
        pass

    if getattr(args, "output_json", False):
        return clients

    if not clients:
        print("No active clients found in Stripe or Supabase.")
        return clients

    print(f"=== Active Clients ({len(clients)} total) ===\n")
    total = 0.0
    for c in clients:
        tag = f"[{c['source']}]"
        sub_id = f"  {c['subscription_id']}" if c.get("subscription_id") else ""
        print(f"  {tag:<10} {c['client']:<35}  ${c['monthly_usd']:>8,.2f}/mo{sub_id}")
        total += c["monthly_usd"]
    print(f"\n  Total: ${total:,.2f}/mo")
    return clients


# -- Command: goal -------------------------------------------------------------

def cmd_goal(env_vars: dict[str, str], db, args) -> dict:
    mrr_data = calculate_mrr(env_vars, db)
    current = mrr_data["total_mrr"]
    pct = (current / MRR_GOAL_USD * 100) if MRR_GOAL_USD else 0
    gap = max(0.0, MRR_GOAL_USD - current)

    # Build progress bar (30 chars wide)
    filled = int(pct / 100 * 30)
    bar = "#" * filled + "-" * (30 - filled)

    result = {
        "current_mrr": current,
        "goal": MRR_GOAL_USD,
        "pct": round(pct, 1),
        "gap": round(gap, 2),
        "deadline": "2026-05-15",
    }

    if getattr(args, "output_json", False):
        return result

    print("=== $5,000 MRR Goal - OASIS AI Solutions ===\n")
    print(f"  Progress:  [{bar}]  {pct:.1f}%")
    print(f"  Current:   ${current:,.2f}")
    print(f"  Goal:      ${MRR_GOAL_USD:,.0f}")
    print(f"  Gap:       ${gap:,.2f}")
    print(f"  Deadline:  May 15, 2026")

    if gap <= 0:
        print("\n  GOAL ACHIEVED. Only good things from now on.")
    else:
        # Days remaining to deadline
        deadline = datetime.date(2026, 5, 15)
        days_left = (deadline - datetime.date.today()).days
        if days_left > 0:
            daily_needed = gap / days_left
            print(f"\n  {days_left} days remaining - need ${daily_needed:,.2f}/day in new MRR")

    return result


# -- argparse setup -------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Revenue Engine - OASIS business operations CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s mrr
  %(prog)s dashboard
  %(prog)s sync-stripe
  %(prog)s log-revenue --type payment --amount 500 --source manual --client "Bennett" --notes "March retainer"
  %(prog)s log-month --month 2026-03 --mrr 2691 --new-clients 0 --churned 0 --pipeline 5000 --leads 50
  %(prog)s history --months 6
  %(prog)s forecast
  %(prog)s clients
  %(prog)s goal
  %(prog)s --json dashboard
        """,
    )

    # Top-level --json flag (must come before subcommand in practice; also added per-subcommand)
    parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON for agent consumption")

    # Shared parent so every subparser inherits --json
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command", help="Command")

    sub.add_parser("mrr", parents=[parent], help="Calculate current MRR")
    sub.add_parser("dashboard", parents=[parent], help="Full business dashboard")
    sub.add_parser("sync-stripe", parents=[parent], help="Pull recent Stripe events into revenue_events")

    p_lr = sub.add_parser("log-revenue", parents=[parent], help="Log a revenue event manually")
    p_lr.add_argument("--type", required=True,
                      choices=["payment", "refund", "subscription_start", "subscription_cancel", "invoice_paid", "other"],
                      help="Event type")
    p_lr.add_argument("--amount", type=float, required=True, help="Amount in USD")
    p_lr.add_argument("--source", default="manual", help="Source (default: manual)")
    p_lr.add_argument("--client", help="Client name")
    p_lr.add_argument("--email", help="Client email")
    p_lr.add_argument("--notes", help="Free-text notes")

    p_lm = sub.add_parser("log-month", parents=[parent], help="Log monthly metrics snapshot")
    p_lm.add_argument("--month", required=True, help="Month in YYYY-MM format (e.g. 2026-03)")
    p_lm.add_argument("--mrr", type=float, required=True, help="MRR for this month in USD")
    p_lm.add_argument("--new-clients", type=int, default=0)
    p_lm.add_argument("--churned", type=int, default=0)
    p_lm.add_argument("--pipeline", type=float, default=0.0, help="Pipeline value in USD")
    p_lm.add_argument("--leads", type=int, default=0)

    p_hist = sub.add_parser("history", parents=[parent], help="Show monthly MRR trend")
    p_hist.add_argument("--months", type=int, default=6, help="Number of months to show (default: 6)")

    sub.add_parser("forecast", parents=[parent], help="Project MRR trajectory toward goal")
    sub.add_parser("clients", parents=[parent], help="List active clients with monthly amounts")
    sub.add_parser("goal", parents=[parent], help="Show $5,000 MRR goal progress")

    return parser


# -- Entry point ----------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    db = get_supabase(env_vars)

    dispatch = {
        "mrr": cmd_mrr,
        "dashboard": cmd_dashboard,
        "sync-stripe": cmd_sync_stripe,
        "log-revenue": cmd_log_revenue,
        "log-month": cmd_log_month,
        "history": cmd_history,
        "forecast": cmd_forecast,
        "clients": cmd_clients,
        "goal": cmd_goal,
    }

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    result = handler(env_vars, db, args)

    # --json output for any command that returned early from its handler
    if getattr(args, "output_json", False) and result is not None:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
