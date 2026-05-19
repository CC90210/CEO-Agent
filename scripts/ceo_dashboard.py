#!/usr/bin/env python3
"""
CEO Dashboard — Unified KPI Aggregator
Aggregates revenue, pipeline, content, and client health into a single digest.
All credentials loaded from .env.agents (never hardcoded).

Usage:
    python scripts/ceo_dashboard.py briefing          # Morning briefing (5 North Star metrics)
    python scripts/ceo_dashboard.py revenue            # Revenue dashboard
    python scripts/ceo_dashboard.py pipeline           # Pipeline dashboard
    python scripts/ceo_dashboard.py content            # Content dashboard
    python scripts/ceo_dashboard.py full               # Full CEO dashboard
    python scripts/ceo_dashboard.py --json <command>   # JSON output for agents
"""

import argparse
import csv
import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MRR_GOAL_USD = 5000.0
MRR_TARGET_DATE = datetime.date(2026, 6, 18)  # North Star per CLAUDE.md WHY section (extended 2026-05-18 from May 30)
STRIPE_API = "https://api.stripe.com/v1"
STRIPE_VERSION = "2025-01-27.acacia"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Monthly content targets per platform (posts/week)
CONTENT_TARGETS: dict[str, int] = {
    "x": 7,
    "instagram": 4,
    "linkedin": 3,
    "tiktok": 3,
    "threads": 5,
}

MONTHLY_OVERHEAD_USD = 184.0  # Claude $140 + Supabase $25 + Hostinger $14 + buffer


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root. Never reads .env directly."""
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}

    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


# ---------------------------------------------------------------------------
# Stripe helpers
# ---------------------------------------------------------------------------

def _stripe_get(
    secret_key: str,
    endpoint: str,
    params: Optional[dict] = None,
    account_id: Optional[str] = None,
) -> dict:
    """GET from Stripe REST API. Returns empty dict on failure (graceful degradation)."""
    try:
        import requests
    except ImportError:
        return {}

    headers: dict[str, str] = {"Stripe-Version": STRIPE_VERSION}
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
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _stripe_get_all(
    secret_key: str,
    endpoint: str,
    params: Optional[dict] = None,
    account_id: Optional[str] = None,
) -> list[dict]:
    """Auto-paginate a Stripe list endpoint."""
    items: list[dict] = []
    p = dict(params or {})
    p.setdefault("limit", 100)

    while True:
        page = _stripe_get(secret_key, endpoint, p, account_id=account_id)
        data = page.get("data", [])
        items.extend(data)
        if not page.get("has_more"):
            break
        if not data:
            break
        p["starting_after"] = data[-1]["id"]

    return items


def _stripe_mrr(secret_key: str, account_id: Optional[str] = None) -> float:
    """Calculate monthly recurring revenue from active subscriptions in USD."""
    CAD_TO_USD = 0.72
    subs = _stripe_get_all(secret_key, "subscriptions", {"status": "active"}, account_id)
    total = 0.0

    for sub in subs:
        for item in sub.get("items", {}).get("data", []):
            price = item.get("price", {})
            unit_amount = price.get("unit_amount") or 0
            currency = price.get("currency", "usd").lower()
            recurring = price.get("recurring") or {}
            interval = recurring.get("interval", "month")
            interval_count = max(recurring.get("interval_count", 1), 1)
            quantity = item.get("quantity", 1)

            amount_cents = unit_amount * quantity
            amount_usd = (amount_cents / 100.0) * (CAD_TO_USD if currency == "cad" else 1.0)

            if interval == "year":
                amount_usd = amount_usd / 12.0
            elif interval == "day":
                amount_usd = amount_usd * 30.0
            elif interval == "week":
                amount_usd = amount_usd * 4.33
            elif interval == "month":
                amount_usd = amount_usd / interval_count

            total += amount_usd

    return round(total, 2)


def _stripe_balance(secret_key: str) -> float:
    """Get available Stripe balance in USD."""
    data = _stripe_get(secret_key, "balance")
    available = data.get("available", [])
    total_cents = sum(
        entry.get("amount", 0) for entry in available if entry.get("currency") == "usd"
    )
    return round(total_cents / 100.0, 2)


# ---------------------------------------------------------------------------
# Supabase / lead pipeline helpers
# ---------------------------------------------------------------------------

def _read_lead_tracker() -> list[dict]:
    """Read LEAD_TRACKER.csv and return rows as list of dicts."""
    csv_path = PROJECT_ROOT / "memory" / "LEAD_TRACKER.csv"
    if not csv_path.exists():
        return []
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


PIPELINE_STAGES = {"Discovery", "Proposal Sent", "Negotiation", "Interest"}


def _pipeline_stats(leads: list[dict]) -> dict:
    """Calculate pipeline value, counts, and top leads from LEAD_TRACKER rows."""
    active: list[dict] = []
    for row in leads:
        stage = (row.get("stage") or row.get("Stage") or "").strip()
        if stage in PIPELINE_STAGES:
            active.append(row)

    total_value = 0.0
    by_stage: dict[str, int] = {}
    for row in active:
        stage = (row.get("stage") or row.get("Stage") or "").strip()
        by_stage[stage] = by_stage.get(stage, 0) + 1
        val_str = (row.get("value") or row.get("Value") or row.get("deal_value") or "0").replace("$", "").replace(",", "").strip()
        try:
            total_value += float(val_str)
        except ValueError:
            pass

    top_leads = sorted(
        active,
        key=lambda r: float(
            (r.get("value") or r.get("Value") or "0").replace("$", "").replace(",", "").strip() or "0"
        ),
        reverse=True,
    )[:3]

    return {
        "total_pipeline": round(total_value, 2),
        "active_count": len(active),
        "by_stage": by_stage,
        "top_leads": top_leads,
    }


# ---------------------------------------------------------------------------
# Content helpers (read-only — calls Maven's late_tool.py via subprocess)
# ---------------------------------------------------------------------------
# Maven (CMO-Agent) owns social publishing as of 2026-04-26. Bravo's CEO
# dashboard still needs the "X posts published this week" metric, so we
# subprocess to Maven's copy of late_tool.py for read-only stats. Override
# Maven's location with the MAVEN_REPO env var if your machine differs.

def _content_this_week() -> dict[str, int]:
    """Count posts published this week by platform via Maven's late_tool.py."""
    from sibling_repos import script_in
    script = script_in("maven", "scripts", "late_tool.py")
    if script is None or not script.exists():
        # Maven not installed on this machine — return empty rather than error.
        return {}

    try:
        result = subprocess.run(
            [sys.executable, str(script), "posts", "--status", "published", "--json"],
            capture_output=True, text=True, timeout=20,
         creationflags=WINDOWLESS_FLAGS)
        posts = json.loads(result.stdout) if result.returncode == 0 else []
    except Exception:
        return {}

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    week_start = now - datetime.timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    counts: dict[str, int] = {}
    for post in posts:
        published_at_str = (
            post.get("publishedAt") or post.get("published_at") or post.get("scheduledAt") or ""
        )
        if not published_at_str:
            continue
        try:
            # Handle ISO 8601 with or without Z
            published_at = datetime.datetime.fromisoformat(
                published_at_str.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            continue

        if published_at >= week_start:
            platform = (post.get("platform") or post.get("account_platform") or "unknown").lower()
            counts[platform] = counts.get(platform, 0) + 1

    return counts


# ---------------------------------------------------------------------------
# Memory file helpers
# ---------------------------------------------------------------------------

def _days_to_target() -> int:
    today = datetime.date.today()
    return max((MRR_TARGET_DATE - today).days, 0)


def _mrr_from_memory() -> float:
    """Last-resort: scan SESSION_LOG or STATE for a known MRR figure."""
    state_path = PROJECT_ROOT / "brain" / "STATE.md"
    if not state_path.exists():
        return 0.0
    content = state_path.read_text(encoding="utf-8", errors="ignore")
    import re
    # Look for patterns like "$2,982" or "MRR: $2,982" or "Net MRR: $2,982"
    matches = re.findall(r"\$([0-9][0-9,]+)", content)
    for m in matches:
        try:
            val = float(m.replace(",", ""))
            if 500 <= val <= 20000:  # plausible MRR range
                return val
        except ValueError:
            continue
    return 0.0


def _trend_arrow(current: float, previous: float) -> str:
    if current > previous * 1.01:
        return "^"
    if current < previous * 0.99:
        return "v"
    return "-"


def _progress_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


# ---------------------------------------------------------------------------
# Dashboard sections
# ---------------------------------------------------------------------------

def _build_north_star(env: dict, as_json: bool) -> dict:
    """Gather all 5 North Star metrics."""
    stripe_key = env.get("STRIPE_SECRET_KEY") or env.get("STRIPE_API_KEY") or ""

    # --- MRR ---
    stripe_mrr = 0.0
    stripe_available = stripe_key != ""
    net_mrr = 0.0
    mrr_source = "fallback"
    try:
        from revenue_engine import calculate_mrr, get_supabase  # type: ignore

        db = get_supabase(env)
        mrr_data = calculate_mrr(env, db)
        stripe_mrr = float(mrr_data.get("stripe_mrr") or 0.0)
        stripe_available = bool(mrr_data.get("stripe_available"))
        net_mrr = float(mrr_data.get("total_mrr") or 0.0)
        mrr_source = "revenue_engine"
    except Exception:
        # Fallback only: keep the briefing usable if Supabase/Stripe are down,
        # but revenue_engine remains the source of truth when available.
        if stripe_available:
            stripe_mrr = _stripe_mrr(stripe_key)
        manual_mrr = _mrr_from_memory() if stripe_mrr < 100 else 0.0
        net_mrr = stripe_mrr if stripe_mrr > 100 else manual_mrr
        mrr_source = "stripe" if stripe_mrr > 100 else "memory"

    # --- Pipeline ---
    # Source-of-truth is the Supabase `leads` table via lead_engine.py, NOT
    # the legacy memory/LEAD_TRACKER.csv (which has been dormant since the
    # migration to tenant_records). The 2026-05-18 brief told CC "0 active
    # leads in the briefing layer" because this function was still reading
    # the dead CSV with a stage-name vocabulary (Discovery/Proposal/...)
    # that doesn't match the canonical new/contacted/qualified/won statuses.
    pipeline = {"total_pipeline": 0.0, "active_count": 0, "by_stage": {}}
    lead_engine = PROJECT_ROOT / "scripts" / "lead_engine.py"
    if lead_engine.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(lead_engine), "--json", "pipeline"],
                capture_output=True, text=True, timeout=20,
                creationflags=(0x08000000 if sys.platform == "win32" else 0),
            )
            if result.returncode == 0 and result.stdout.strip().startswith("{"):
                pdata = json.loads(result.stdout)
                # lead_engine returns { new: {count, avg_score, total_value?}, contacted: {...}, ... }
                ACTIVE_STAGES = {"new", "contacted", "qualified", "proposal"}
                by_stage: dict[str, int] = {}
                active_count = 0
                total_value = 0.0
                for stage, stats in pdata.items():
                    if not isinstance(stats, dict):
                        continue
                    cnt = int(stats.get("count", 0) or 0)
                    by_stage[stage] = cnt
                    if stage in ACTIVE_STAGES:
                        active_count += cnt
                        total_value += float(stats.get("total_value", 0) or 0)
                pipeline = {
                    "total_pipeline": round(total_value, 2),
                    "active_count": active_count,
                    "by_stage": by_stage,
                }
        except Exception:
            pass

    # --- Client health (via client_health.py if available) ---
    # NOTE: argparse on client_health.py puts --json on the TOP-LEVEL parser,
    # so it must come BEFORE the subcommand verb. The old `report --json`
    # order errored out silently with exit 0 + help text, leaving CC's brief
    # showing "0 alerts, score 0" when there were actually 2 at-risk clients.
    client_health_avg = 0.0
    clients_at_risk = 0
    client_script = PROJECT_ROOT / "scripts" / "client_health.py"
    if client_script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(client_script), "--json", "report"],
                capture_output=True, text=True, timeout=20,
                creationflags=(0x08000000 if sys.platform == "win32" else 0),
            )
            if result.returncode == 0:
                health_data = json.loads(result.stdout)
                # client_health.py --json report returns a LIST of clients
                # directly (not wrapped in {"clients": [...]}). Be tolerant
                # of both shapes — the wrapped form was assumed for months
                # but was never actually produced, which is why CC's brief
                # showed avg_score=0 / at_risk=0 even with 2 RED clients.
                if isinstance(health_data, list):
                    clients = health_data
                else:
                    clients = health_data.get("clients", [])
                scores = [c.get("score", 0) for c in clients if isinstance(c, dict)]
                if scores:
                    client_health_avg = round(sum(scores) / len(scores), 1)
                    clients_at_risk = sum(1 for s in scores if s < 55)
        except Exception:
            pass

    # --- Cash position ---
    cash_stripe = _stripe_balance(stripe_key) if stripe_available else 0.0

    # --- Content velocity ---
    content_counts = _content_this_week()
    total_posts = sum(content_counts.values())
    total_target = sum(CONTENT_TARGETS.values())

    days_left = _days_to_target()
    mrr_pct = round((net_mrr / MRR_GOAL_USD) * 100, 1) if MRR_GOAL_USD > 0 else 0.0

    data = {
        "date": datetime.date.today().isoformat(),
        "mrr": {
            "value": net_mrr,
            "target": MRR_GOAL_USD,
            "pct": mrr_pct,
            "days_to_target": days_left,
            "source": mrr_source,
        },
        "pipeline": {
            "total_value": pipeline["total_pipeline"],
            "active_leads": pipeline["active_count"],
            "by_stage": pipeline["by_stage"],
        },
        "client_health": {
            "avg_score": client_health_avg,
            "at_risk": clients_at_risk,
        },
        "cash": {
            "stripe_balance": cash_stripe,
            "note": "Add bank balance manually for complete picture",
        },
        "content": {
            "posts_this_week": total_posts,
            "target": total_target,
            "by_platform": content_counts,
        },
    }

    return data


def _format_briefing(data: dict) -> str:
    mrr = data["mrr"]
    pipeline = data["pipeline"]
    health = data["client_health"]
    cash = data["cash"]
    content = data["content"]

    pct = mrr["pct"]
    bar = _progress_bar(pct)

    content_status = "on pace" if content["posts_this_week"] >= content["target"] else f"BEHIND by {content['target'] - content['posts_this_week']}"

    pipeline_note = ""
    if pipeline["total_value"] > 0:
        pipeline_note = f"  Weighted (x50%): ${pipeline['total_value'] * 0.5:,.0f} expected"

    health_note = ""
    if health["avg_score"] > 0:
        risk_note = f"  ⚠️  {health['at_risk']} client(s) below 55 — check alerts" if health["at_risk"] > 0 else "  All clients healthy"
        health_note = f"  Avg: {health['avg_score']}/100\n{risk_note}"
    else:
        health_note = "  Run: python scripts/client_health.py report"

    by_platform_lines = []
    for platform, count in content["by_platform"].items():
        target = CONTENT_TARGETS.get(platform, 0)
        indicator = "OK" if count >= target else f"BEHIND -{target - count}"
        by_platform_lines.append(f"  {platform.capitalize():<12} {count}/{target}  {indicator}")
    if not by_platform_lines:
        by_platform_lines.append("  No published posts found this week")

    separator = "=" * 54
    lines = [
        separator,
        f"CEO BRIEFING -- {data['date']}",
        separator,
        "",
        "NET MRR",
        f"  ${mrr['value']:,.0f} / ${mrr['target']:,.0f}  ({pct}%)  |  {mrr['days_to_target']} days to target",
        f"  {bar}",
        "",
        "PIPELINE",
        f"  ${pipeline['total_value']:,.0f} across {pipeline['active_leads']} active leads",
    ]
    if pipeline_note:
        lines.append(pipeline_note)

    lines += [
        "",
        "CLIENT HEALTH",
        health_note,
        "",
        "CASH POSITION",
        f"  Stripe available: ${cash['stripe_balance']:,.2f}",
        f"  {cash['note']}",
        "",
        "CONTENT THIS WEEK",
        f"  Total: {content['posts_this_week']}/{content['target']} posts  ({content_status})",
    ]
    lines += by_platform_lines
    lines.append("")
    lines.append(separator)

    return "\n".join(lines)


def _format_revenue(env: dict) -> str:
    stripe_key = env.get("STRIPE_SECRET_KEY") or env.get("STRIPE_API_KEY") or ""

    # Attempt multi-account MRR breakdown
    accounts = {
        "OASIS": env.get("STRIPE_ACCOUNT_OASIS_ID", ""),
        "PropFlow": env.get("STRIPE_ACCOUNT_PROPFLOW_ID", ""),
        "Nostalgic": env.get("STRIPE_ACCOUNT_NOSTALGIC_ID", ""),
    }

    rows = []
    total = 0.0
    for brand, acct_id in accounts.items():
        if stripe_key:
            mrr = _stripe_mrr(stripe_key, acct_id if acct_id else None)
        else:
            mrr = 0.0
        rows.append((brand, mrr))
        total += mrr

    lines = [
        "=" * 54,
        f"REVENUE DASHBOARD -- {datetime.date.today().isoformat()}",
        "=" * 54,
        "",
        f"{'Brand':<20} {'MRR':>10}",
        "-" * 34,
    ]
    for brand, mrr in rows:
        lines.append(f"{brand:<20} ${mrr:>9,.2f}")

    lines += [
        "-" * 34,
        f"{'NET MRR TOTAL':<20} ${total:>9,.2f}",
        f"{'TARGET':<20} ${MRR_GOAL_USD:>9,.2f}",
        f"{'GAP':<20} ${max(MRR_GOAL_USD - total, 0):>9,.2f}",
        "",
        f"OVERHEAD:  ${MONTHLY_OVERHEAD_USD:,.2f}/mo  ({round(MONTHLY_OVERHEAD_USD / MRR_GOAL_USD * 100, 1)}% of target)",
        f"NET AFTER OVERHEAD: ${max(total - MONTHLY_OVERHEAD_USD, 0):,.2f}/mo",
        "",
        "Run `python scripts/revenue_engine.py history` for 6-month trend.",
        "=" * 54,
    ]
    return "\n".join(lines)


def _format_pipeline() -> str:
    leads = _read_lead_tracker()
    pipeline = _pipeline_stats(leads)

    lines = [
        "=" * 54,
        f"PIPELINE DASHBOARD -- {datetime.date.today().isoformat()}",
        "=" * 54,
        "",
        f"Total pipeline value:   ${pipeline['total_pipeline']:,.0f}",
        f"Active leads:           {pipeline['active_count']}",
        f"Weighted (x50%):        ${pipeline['total_pipeline'] * 0.5:,.0f} expected",
        "",
        "BY STAGE",
    ]
    for stage in ["Interest", "Discovery", "Proposal Sent", "Negotiation"]:
        count = pipeline["by_stage"].get(stage, 0)
        lines.append(f"  {stage:<20} {count} lead(s)")

    lines.append("")
    lines.append("TOP LEADS")
    for i, lead in enumerate(pipeline["top_leads"], 1):
        name = (
            lead.get("name") or lead.get("Name") or lead.get("company") or "Unknown"
        )
        stage = (lead.get("stage") or lead.get("Stage") or "").strip()
        val = (lead.get("value") or lead.get("Value") or "$0").strip()
        next_action = (
            lead.get("next_action") or lead.get("next_step") or lead.get("NextAction") or "—"
        )
        lines.append(f"  {i}. {name:<20} {stage:<18} {val:<10} Next: {next_action}")

    lines += ["", "Source: memory/LEAD_TRACKER.csv", "=" * 54]
    return "\n".join(lines)


def _format_content() -> str:
    counts = _content_this_week()
    total = sum(counts.values())
    target = sum(CONTENT_TARGETS.values())

    lines = [
        "=" * 54,
        f"CONTENT DASHBOARD -- {datetime.date.today().isoformat()}",
        "=" * 54,
        "",
        f"Posts this week: {total} / {target} target",
        "",
        f"{'Platform':<14} {'Published':>9}  {'Target':>6}  Status",
        "-" * 42,
    ]
    for platform, tgt in CONTENT_TARGETS.items():
        count = counts.get(platform, 0)
        status = "OK" if count >= tgt else f"BEHIND -{tgt - count}"
        lines.append(f"{platform.capitalize():<14} {count:>9}  {tgt:>6}  {status}")

    lines += [
        "-" * 42,
        f"{'TOTAL':<14} {total:>9}  {target:>6}",
        "",
        "Source: python ../CMO-Agent/scripts/late_tool.py posts --status published (Maven)",
        "=" * 54,
    ]
    return "\n".join(lines)


def _format_full(env: dict, north_star: dict) -> str:
    sections = [
        _format_briefing(north_star),
        "",
        _format_revenue(env),
        "",
        _format_pipeline(),
        "",
        _format_content(),
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CEO Dashboard — Unified KPI Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["briefing", "revenue", "pipeline", "content", "full"],
        help="Dashboard section to display",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as JSON for agent consumption",
    )
    args = parser.parse_args()

    env = load_env()

    if args.command == "briefing":
        data = _build_north_star(env, args.as_json)
        if args.as_json:
            print(json.dumps(data, indent=2))
        else:
            print(_format_briefing(data))

    elif args.command == "revenue":
        if args.as_json:
            stripe_key = env.get("STRIPE_SECRET_KEY") or env.get("STRIPE_API_KEY") or ""
            mrr = _stripe_mrr(stripe_key) if stripe_key else 0.0
            print(json.dumps({"mrr": mrr, "overhead": MONTHLY_OVERHEAD_USD, "net": round(mrr - MONTHLY_OVERHEAD_USD, 2)}, indent=2))
        else:
            print(_format_revenue(env))

    elif args.command == "pipeline":
        leads = _read_lead_tracker()
        pipeline = _pipeline_stats(leads)
        if args.as_json:
            print(json.dumps(pipeline, indent=2))
        else:
            print(_format_pipeline())

    elif args.command == "content":
        counts = _content_this_week()
        if args.as_json:
            print(json.dumps({"by_platform": counts, "total": sum(counts.values()), "target": sum(CONTENT_TARGETS.values())}, indent=2))
        else:
            print(_format_content())

    elif args.command == "full":
        data = _build_north_star(env, as_json=False)
        if args.as_json:
            revenue_data = {
                "mrr": data["mrr"]["value"],
                "overhead": MONTHLY_OVERHEAD_USD,
            }
            leads = _read_lead_tracker()
            pipeline = _pipeline_stats(leads)
            content_counts = _content_this_week()
            print(json.dumps({
                "north_star": data,
                "pipeline": pipeline,
                "content": {"by_platform": content_counts, "total": sum(content_counts.values())},
            }, indent=2))
        else:
            print(_format_full(env, data))


if __name__ == "__main__":
    main()
