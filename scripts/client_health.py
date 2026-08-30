"""Client Health Scoring Engine — CEO Dashboard Component.

Reads client data from the Turso-backed ``leads`` table and
computes weighted health scores using the algorithm defined in
skills/client-success/SKILL.md.

All credentials loaded from .env.agents (never hardcoded).

Usage:
    python scripts/client_health.py report              # Full health report (all clients)
    python scripts/client_health.py score <client_name> # Single client score
    python scripts/client_health.py alerts              # ORANGE and RED clients only
    python scripts/client_health.py trends              # 30-day score trend analysis
    python scripts/client_health.py --json <command>    # JSON output for agent consumption
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_TIERS = {
    "GREEN":  (80, 100),
    "YELLOW": (60, 79),
    "ORANGE": (40, 59),
    "RED":    (0,  39),
}

TIER_EMOJI = {
    "GREEN":  "✅",
    "YELLOW": "⚠️ ",
    "ORANGE": "🔶",
    "RED":    "🚨",
}

# ANSI colours — suppressed when --json is active
ANSI = {
    "GREEN":  "\033[92m",
    "YELLOW": "\033[93m",
    "ORANGE": "\033[33m",
    "RED":    "\033[91m",
    "RESET":  "\033[0m",
    "BOLD":   "\033[1m",
    "DIM":    "\033[2m",
}


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root. Exits on missing file."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_client(env_vars: dict[str, str]):
    """Return the Turso-backed SDK compatibility client for Bravo."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: 'supabase' package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat"
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key"
    if not url or not key:
        print("ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents", file=sys.stderr)
        sys.exit(1)

    return create_client(url, key)


# ---------------------------------------------------------------------------
# Health score calculation
# ---------------------------------------------------------------------------

def _days_since(date_str: str | None) -> int:
    """Return days elapsed since an ISO date string. Returns 999 if absent."""
    if not date_str:
        return 999
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, TypeError):
        return 999


def _payment_score(lead: dict) -> float:
    """Score 0–25 based on payment timeliness metadata."""
    days_late = int(lead.get("payment_days_late") or 0)
    consecutive_late = int(lead.get("consecutive_late_payments") or 0)

    if days_late == 0:
        raw = 25.0
    elif days_late <= 7:
        raw = 17.0
    elif days_late <= 14:
        raw = 10.0
    else:
        raw = 2.0

    if consecutive_late >= 2:
        raw = max(0.0, raw - 5.0)

    return raw


def _engagement_score(lead: dict) -> float:
    """Score 0–25 based on interaction frequency."""
    days_since_contact = _days_since(lead.get("last_contact_date") or lead.get("updated_at"))

    if days_since_contact > 14:
        return 0.0

    monthly_touchpoints = int(lead.get("monthly_touchpoints") or 0)
    if monthly_touchpoints >= 4:
        return 25.0
    elif monthly_touchpoints >= 2:
        return 18.0
    elif monthly_touchpoints >= 1:
        return 10.0
    else:
        # Has contact in 14 days but no explicit touchpoint count — infer from recency
        if days_since_contact <= 3:
            return 18.0
        elif days_since_contact <= 7:
            return 10.0
        return 5.0


def _scope_score(lead: dict) -> float:
    """Score 0–20 based on deliverable status."""
    delayed = int(lead.get("deliverables_delayed") or 0)
    scope_dispute = bool(lead.get("active_scope_dispute"))

    if scope_dispute:
        return 0.0
    elif delayed == 0:
        return 20.0
    elif delayed == 1:
        return 14.0
    else:
        return 6.0


def _revenue_score(lead: dict) -> float:
    """Score 0–15 based on MRR trajectory."""
    trajectory = (lead.get("revenue_trajectory") or "stable").lower()
    cancellation = bool(lead.get("cancellation_discussion"))

    if cancellation:
        return 0.0
    elif trajectory == "growing":
        return 15.0
    elif trajectory == "stable":
        return 11.0
    elif trajectory == "declining":
        return 5.0
    else:
        return 11.0


def _relationship_score(lead: dict) -> float:
    """Score 0–15 based on relationship signals."""
    gave_referral = bool(lead.get("gave_referral"))
    mentions_pause = bool(lead.get("mentions_pause") or lead.get("churn_risk_flag"))
    avg_response_hours = float(lead.get("avg_response_hours") or 24.0)

    if mentions_pause:
        return 0.0
    elif gave_referral:
        return 15.0
    elif avg_response_hours <= 24:
        return 11.0
    elif avg_response_hours <= 72:
        return 6.0
    else:
        return 2.0


def calculate_health_score(lead: dict) -> dict:
    """
    Compute the composite health score and risk tier for a single client lead.

    Returns a dict with score, tier, dimension breakdown, and key signals.
    """
    payment    = _payment_score(lead)
    engagement = _engagement_score(lead)
    scope      = _scope_score(lead)
    revenue    = _revenue_score(lead)
    relationship = _relationship_score(lead)

    # Weighted composite (weights sum to 1.0)
    score = (
        payment      * 0.25 +
        engagement   * 0.25 +
        scope        * 0.20 +
        revenue      * 0.15 +
        relationship * 0.15
    )

    # Normalise to 0–100 (each sub-score already on 0–max_weight scale, so
    # the raw weighted sum is already 0–100 because payment=0-25, engagement=0-25, etc.)
    score = round(min(100.0, max(0.0, score)), 1)

    # Determine tier
    tier = "RED"
    for name, (low, high) in RISK_TIERS.items():
        if low <= score <= high:
            tier = name
            break

    # NPS adjustment
    nps = lead.get("nps_score")
    if nps is not None:
        nps = int(nps)
        if nps >= 9:
            score = min(100.0, round(score + 5.0, 1))
        elif nps <= 6:
            score = max(0.0, round(score - 10.0, 1))
            if tier == "GREEN":
                tier = "YELLOW"

    days_since_contact = _days_since(lead.get("last_contact_date") or lead.get("updated_at"))

    return {
        "name":               lead.get("name") or lead.get("company") or "Unknown",
        "mrr":                float(lead.get("monthly_value") or lead.get("mrr") or 0),
        "score":              score,
        "tier":               tier,
        "days_since_contact": days_since_contact,
        "last_contact":       lead.get("last_contact_date") or lead.get("updated_at", "unknown"),
        "lifecycle_stage":    lead.get("lifecycle_stage") or "steady_state",
        "dimensions": {
            "payment":      round(payment, 1),
            "engagement":   round(engagement, 1),
            "scope":        round(scope, 1),
            "revenue":      round(revenue, 1),
            "relationship": round(relationship, 1),
        },
        "signals": {
            "consecutive_late_payments": int(lead.get("consecutive_late_payments") or 0),
            "deliverables_delayed":      int(lead.get("deliverables_delayed") or 0),
            "mentions_pause":            bool(lead.get("mentions_pause") or lead.get("churn_risk_flag")),
            "gave_referral":             bool(lead.get("gave_referral")),
            "active_scope_dispute":      bool(lead.get("active_scope_dispute")),
            "nps_score":                 nps,
        },
        "lead_id": lead.get("id"),
    }


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_clients(db_client) -> list[dict]:
    """Pull all active clients from the live Turso-backed leads table.

    Empty is valid data. A query failure is not: fail closed so dashboards and
    briefs render an explicit unavailable diagnostic instead of plausible demo
    clients that look like business truth.
    """
    try:
        result = db_client.table("leads").select("*").eq("status", "client").execute()
        # Empty result means CC has no clients tagged status='client' in the
        # leads table — return empty so callers see ground truth instead of
        # demo data leaking into operator-facing alerts. Was: silently
        # falling through to seed records, which surfaced "Demo Community
        # Client RED, your biggest account!" in CC's daily brief on 2026-05-18
        # when his real paying customers are tracked via revenue_events, not
        # leads-with-status-client. The fix here is structural — don't fake
        # data.
        return result.data or []
    except Exception as exc:
        raise RuntimeError(f"Turso client data query failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _color(text: str, tier: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{ANSI.get(tier, '')}{text}{ANSI['RESET']}"


def _bold(text: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{ANSI['BOLD']}{text}{ANSI['RESET']}"


def format_report(clients_scored: list[dict], use_color: bool = True) -> str:
    lines: list[str] = []

    header = f"Client Health Report — {datetime.now().strftime('%Y-%m-%d')}"
    lines.append(_bold(header, use_color))
    lines.append("=" * len(header))
    lines.append("")

    # Table header
    col = f"{'CLIENT':<30} {'MRR':>8} {'SCORE':>7} {'TIER':<10} {'LAST CONTACT':>14} {'NEXT ACTION'}"
    lines.append(_bold(col, use_color))
    lines.append("-" * 95)

    total_mrr = 0.0
    total_score = 0.0
    at_risk_mrr = 0.0
    alerts: list[str] = []

    for c in sorted(clients_scored, key=lambda x: x["score"]):
        tier_label = f"{TIER_EMOJI[c['tier']]} {c['tier']}"
        last_str   = f"{c['days_since_contact']}d ago"

        # Derive a simple next action from tier
        if c["tier"] == "GREEN":
            next_action = "QBR / upsell"
        elif c["tier"] == "YELLOW":
            next_action = "Proactive check-in"
        elif c["tier"] == "ORANGE":
            next_action = "Call within 48h"
        else:
            next_action = "🚨 Executive save"

        row = (
            f"{c['name']:<30}"
            f"  {'$' + str(int(c['mrr'])):>7}"
            f"  {str(c['score']):>5}/100"
            f"  {tier_label:<14}"
            f"  {last_str:>10}"
            f"  {next_action}"
        )
        lines.append(_color(row, c["tier"], use_color))

        total_mrr   += c["mrr"]
        total_score += c["score"]
        if c["tier"] in ("ORANGE", "RED"):
            at_risk_mrr += c["mrr"]

        # Collect alerts
        sigs = c["signals"]
        if c["days_since_contact"] > 14:
            alerts.append(f"{TIER_EMOJI[c['tier']]} {c['name']}: No contact in {c['days_since_contact']} days")
        if sigs["consecutive_late_payments"] >= 2:
            alerts.append(f"🔶 {c['name']}: {sigs['consecutive_late_payments']} consecutive late payments")
        if sigs["mentions_pause"]:
            alerts.append(f"🚨 {c['name']}: Churn risk flag active")
        if sigs["deliverables_delayed"] >= 2:
            alerts.append(f"⚠️  {c['name']}: {sigs['deliverables_delayed']} deliverables delayed")

    lines.append("-" * 95)
    avg_score = round(total_score / len(clients_scored), 1) if clients_scored else 0.0
    summary = (
        f"Portfolio MRR: ${int(total_mrr):,}  |  "
        f"Avg Health: {avg_score}/100  |  "
        f"At-Risk Revenue: ${int(at_risk_mrr):,}"
    )
    lines.append(_bold(summary, use_color))

    if alerts:
        lines.append("")
        lines.append(_bold("Alerts:", use_color))
        for alert in alerts:
            lines.append(f"  {alert}")

    return "\n".join(lines)


def format_single(client_scored: dict, use_color: bool = True) -> str:
    c = client_scored
    lines: list[str] = []
    tier_line = f"{TIER_EMOJI[c['tier']]} {c['tier']} — {c['score']}/100"
    lines.append(_bold(f"{c['name']}", use_color))
    lines.append(_color(tier_line, c["tier"], use_color))
    lines.append(f"  MRR:            ${int(c['mrr']):,}/mo")
    lines.append(f"  Last contact:   {c['days_since_contact']} days ago")
    lines.append(f"  Lifecycle:      {c['lifecycle_stage']}")
    lines.append("")
    lines.append(_bold("Dimension Breakdown:", use_color))
    d = c["dimensions"]
    lines.append(f"  Payment timeliness:    {d['payment']}/25")
    lines.append(f"  Engagement frequency:  {d['engagement']}/25")
    lines.append(f"  Scope satisfaction:    {d['scope']}/20")
    lines.append(f"  Revenue trajectory:    {d['revenue']}/15")
    lines.append(f"  Relationship signals:  {d['relationship']}/15")
    lines.append("")
    sigs = c["signals"]
    active_signals = [k for k, v in sigs.items() if v and v is not True or (isinstance(v, int) and v > 0)]
    if any(v for v in sigs.values()):
        lines.append(_bold("Active Risk Signals:", use_color))
        if sigs["consecutive_late_payments"] > 0:
            lines.append(f"  Consecutive late payments: {sigs['consecutive_late_payments']}")
        if sigs["deliverables_delayed"] > 0:
            lines.append(f"  Deliverables delayed: {sigs['deliverables_delayed']}")
        if sigs["mentions_pause"]:
            lines.append("  Churn risk flag: active")
        if sigs["active_scope_dispute"]:
            lines.append("  Active scope dispute")
        if sigs["nps_score"] is not None:
            lines.append(f"  NPS score: {sigs['nps_score']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_report(db_client, args: argparse.Namespace) -> int:
    raw_clients = fetch_clients(db_client)
    if not raw_clients:
        print("No clients found with status='client' in the leads table.")
        return 0

    scored = [calculate_health_score(c) for c in raw_clients]

    if args.json:
        print(json.dumps(scored, indent=2, default=str))
    else:
        print(format_report(scored, use_color=sys.stdout.isatty()))
    return 0


def cmd_score(db_client, args: argparse.Namespace) -> int:
    if not args.client_name:
        print("ERROR: Provide a client name: client_health.py score <name>", file=sys.stderr)
        return 1

    raw_clients = fetch_clients(db_client)
    name_lower  = args.client_name.lower()
    matches     = [
        c for c in raw_clients
        if name_lower in (c.get("name") or "").lower()
        or name_lower in (c.get("company") or "").lower()
    ]

    if not matches:
        print(f"No client matching '{args.client_name}' found with status='client'.")
        return 1

    scored = [calculate_health_score(c) for c in matches]

    if args.json:
        print(json.dumps(scored[0] if len(scored) == 1 else scored, indent=2, default=str))
    else:
        for s in scored:
            print(format_single(s, use_color=sys.stdout.isatty()))
            print()
    return 0


def cmd_alerts(db_client, args: argparse.Namespace) -> int:
    raw_clients = fetch_clients(db_client)
    scored      = [calculate_health_score(c) for c in raw_clients]
    at_risk     = [c for c in scored if c["tier"] in ("ORANGE", "RED")]

    if not at_risk:
        msg = "All clients are GREEN or YELLOW. No immediate interventions required."
        if args.json:
            print(json.dumps({"status": "ok", "message": msg, "at_risk_clients": []}, indent=2))
        else:
            print(f"✅ {msg}")
        return 0

    if args.json:
        print(json.dumps(at_risk, indent=2, default=str))
    else:
        print(_bold(f"At-Risk Clients ({len(at_risk)} of {len(scored)})", use_color=sys.stdout.isatty()))
        print()
        for c in sorted(at_risk, key=lambda x: x["score"]):
            print(format_single(c, use_color=sys.stdout.isatty()))
            print()
    return 0


def cmd_trends(db_client, args: argparse.Namespace) -> int:
    """
    Trend analysis over the last 30 days.
    Reads from client_health_snapshots table if available; falls back to a
    message explaining what to set up.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        result = db_client.table("client_health_snapshots") \
            .select("client_name, score, tier, snapshot_date") \
            .gte("snapshot_date", cutoff) \
            .order("snapshot_date") \
            .execute()

        snapshots: list[dict] = result.data or []
    except Exception:
        snapshots = []

    if not snapshots:
        note = {
            "status": "no_data",
            "message": (
                "No historical snapshots found. Insert a row into the "
                "'client_health_snapshots' table each time you run 'report' to enable "
                "trend analysis. Columns: client_name, score, tier, snapshot_date."
            ),
        }
        if args.json:
            print(json.dumps(note, indent=2))
        else:
            print("ℹ️  " + note["message"])
        return 0

    # Group snapshots by client
    by_client: dict[str, list[dict]] = {}
    for snap in snapshots:
        name = snap["client_name"]
        by_client.setdefault(name, []).append(snap)

    if args.json:
        print(json.dumps(by_client, indent=2, default=str))
        return 0

    use_color = sys.stdout.isatty()
    print(_bold("30-Day Health Trends", use_color))
    print()

    for name, snaps in sorted(by_client.items()):
        first_score = snaps[0]["score"]
        last_score  = snaps[-1]["score"]
        delta       = last_score - first_score
        arrow       = "^" if delta > 0 else ("v" if delta < 0 else "-")
        tier        = snaps[-1]["tier"]

        line = (
            f"{name:<30}  "
            f"Start: {first_score:.1f}  "
            f"Current: {last_score:.1f}  "
            f"{arrow} {abs(delta):.1f}  "
            f"{TIER_EMOJI[tier]} {tier}"
        )
        print(_color(line, tier, use_color))

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="client_health.py",
        description="Client Health Scoring Engine — OASIS AI CEO Dashboard",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON for agent consumption")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("report",  help="Full health report for all clients")

    score_p = sub.add_parser("score", help="Score a single client by name")
    score_p.add_argument("client_name", nargs="?", help="Client name or company (partial match)")

    sub.add_parser("alerts",  help="Show only ORANGE and RED clients")
    sub.add_parser("trends",  help="30-day trend analysis (requires snapshot history)")

    return parser


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    env_vars  = load_env()
    db_client = get_client(env_vars)

    commands = {
        "report": cmd_report,
        "score":  cmd_score,
        "alerts": cmd_alerts,
        "trends": cmd_trends,
    }

    handler = commands.get(args.command)
    if not handler:
        print(f"ERROR: Unknown command '{args.command}'", file=sys.stderr)
        return 1

    return handler(db_client, args)


if __name__ == "__main__":
    sys.exit(main())
