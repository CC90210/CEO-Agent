#!/usr/bin/env python3
"""Financial Modeling Engine — CEO Dashboard Component

Calculates unit economics, projects revenue, models scenarios, assesses
client concentration risk, and forecasts cash runway.
Current CC baseline is baked in as defaults; override with flags.

Usage:
    python scripts/financial_model.py unit-economics
    python scripts/financial_model.py unit-economics --mrr 3500 --clients 4 --churn 0.02
    python scripts/financial_model.py forecast
    python scripts/financial_model.py forecast --months 12 --growth 0.15
    python scripts/financial_model.py scenario --type base
    python scripts/financial_model.py scenario --type bull
    python scripts/financial_model.py scenario --type bear
    python scripts/financial_model.py concentration
    python scripts/financial_model.py concentration --clients '{"Top Client": 2500, "Other": 191}'
    python scripts/financial_model.py runway
    python scripts/financial_model.py runway --cash 15000 --expenses 184
    python scripts/financial_model.py --json <any subcommand>
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# CC-specific baseline constants (post-primary-retainer end: 2026-05-18)
# ---------------------------------------------------------------------------

DEFAULT_MRR = 371.0
DEFAULT_OVERHEAD = 184.0
DEFAULT_CLIENTS = 1          # Stripe baseline only; SunBiz salary pending
DEFAULT_CHURN_RATE = 0.01    # ~1%/mo (conservative floor)
DEFAULT_GROSS_MARGIN = 0.94  # 94%
DEFAULT_CAC = 250.0          # opportunity cost estimate (no paid ads)
DEFAULT_CASH_ON_HAND = 5000.0  # conservative estimate — CC to update
MRR_TARGET = 5000.0
TARGET_DATE = "2026-06-18"

DEFAULT_CLIENT_REVENUE = {
    "Stripe": 180.0,
    "Base (other)": 191.0,
}


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------

def calc_arpu(mrr: float, clients: int) -> float:
    if clients <= 0:
        return 0.0
    return mrr / clients


def calc_ltv(arpu: float, gross_margin: float, churn_rate: float) -> float:
    """LTV = ARPU × Gross Margin × (1 / Churn Rate)"""
    if churn_rate <= 0:
        return float("inf")
    lifespan = 1.0 / churn_rate
    return arpu * gross_margin * lifespan


def calc_ltv_cac_ratio(ltv: float, cac: float) -> float:
    if cac <= 0:
        return float("inf")
    return ltv / cac


def calc_payback_months(cac: float, arpu: float, gross_margin: float) -> float:
    monthly_contribution = arpu * gross_margin
    if monthly_contribution <= 0:
        return float("inf")
    return cac / monthly_contribution


def calc_burn_rate(expenses: float, revenue: float) -> float:
    """Positive = profitable. Negative = burning cash."""
    return revenue - expenses


def calc_runway(cash: float, monthly_burn: float) -> float:
    """Months of runway. If burn >= 0 (profitable), returns inf."""
    if monthly_burn >= 0:
        return float("inf")
    return cash / abs(monthly_burn)


def calc_herfindahl(client_revenue: dict[str, float]) -> float:
    """HHI = sum of squared market shares. 0=perfect diversity, 1=monopoly."""
    total = sum(client_revenue.values())
    if total <= 0:
        return 0.0
    return sum((rev / total) ** 2 for rev in client_revenue.values())


def interpret_hhi(hhi: float) -> str:
    if hhi >= 0.75:
        return "CRITICAL - extreme concentration, single churn = catastrophic"
    if hhi >= 0.5:
        return "HIGH - dangerous, prioritize diversification immediately"
    if hhi >= 0.25:
        return "MODERATE - manageable but monitor closely"
    return "DIVERSIFIED — healthy spread of revenue"


def mrr_gap_to_target(current_mrr: float) -> dict:
    gap = MRR_TARGET - current_mrr
    today = datetime.now(timezone.utc)
    try:
        target = datetime.strptime(TARGET_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_remaining = (target - today).days
    except ValueError:
        days_remaining = 0
    pct = (current_mrr / MRR_TARGET) * 100
    return {
        "current_mrr": current_mrr,
        "target_mrr": MRR_TARGET,
        "gap": gap,
        "pct_complete": round(pct, 1),
        "days_remaining": max(days_remaining, 0),
        "target_date": TARGET_DATE,
    }


# ---------------------------------------------------------------------------
# Scenario modeling
# ---------------------------------------------------------------------------

SCENARIOS = {
    "bear": {
        "label": "Bear (pessimistic)",
        "new_clients_per_month": 0,
        "avg_deal_size": 500.0,
        "monthly_churn_rate": 0.05,
        "expansion_pct": 0.0,
        "probability": 0.15,
        "description": "No new clients, primary retainer holds but no growth, 5% monthly churn kicks in.",
    },
    "base": {
        "label": "Base (realistic)",
        "new_clients_per_month": 1,
        "avg_deal_size": 1000.0,
        "monthly_churn_rate": 0.02,
        "expansion_pct": 0.02,
        "probability": 0.60,
        "description": "1 new client/month at $1K, low churn, modest expansion from primary retainer.",
    },
    "bull": {
        "label": "Bull (optimistic)",
        "new_clients_per_month": 2,
        "avg_deal_size": 1500.0,
        "monthly_churn_rate": 0.005,
        "expansion_pct": 0.05,
        "probability": 0.25,
        "description": "2 new clients/month at $1.5K, near-zero churn, PropFlow launch contributes.",
    },
}


def project_mrr_scenario(
    starting_mrr: float,
    months: int,
    new_clients_per_month: float,
    avg_deal_size: float,
    monthly_churn_rate: float,
    expansion_pct: float,
) -> list[float]:
    """Project MRR month-by-month for a given scenario."""
    mrr = starting_mrr
    projection = [round(mrr, 2)]
    for _ in range(months):
        new_mrr = new_clients_per_month * avg_deal_size
        expansion_mrr = mrr * expansion_pct
        churned_mrr = mrr * monthly_churn_rate
        mrr = mrr + new_mrr + expansion_mrr - churned_mrr
        projection.append(round(mrr, 2))
    return projection


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_unit_economics(args: argparse.Namespace) -> dict:
    mrr = args.mrr
    clients = args.clients
    churn = args.churn
    gross_margin = args.gross_margin
    cac = args.cac
    expenses = args.expenses

    arpu = calc_arpu(mrr, clients)
    ltv = calc_ltv(arpu, gross_margin, churn)
    ltv_str = f"${ltv:,.0f}" if not math.isinf(ltv) else "inf (no churn)"
    ratio = calc_ltv_cac_ratio(ltv, cac)
    ratio_str = f"{ratio:.1f}:1" if not math.isinf(ratio) else "inf:1 (no churn)"
    payback = calc_payback_months(cac, arpu, gross_margin)
    payback_str = f"{payback:.1f} months" if not math.isinf(payback) else "N/A (zero contribution)"
    burn = calc_burn_rate(expenses, mrr)
    runway = calc_runway(args.cash, -burn if burn < 0 else 0)
    runway_str = f"{runway:.0f} months" if not math.isinf(runway) else "inf (profitable)"
    gap = mrr_gap_to_target(mrr)

    result = {
        "mrr": mrr,
        "clients": clients,
        "arpu": round(arpu, 2),
        "gross_margin_pct": round(gross_margin * 100, 1),
        "monthly_churn_rate_pct": round(churn * 100, 2),
        "cac": cac,
        "ltv": round(ltv, 2) if not math.isinf(ltv) else "inf",
        "ltv_cac_ratio": round(ratio, 1) if not math.isinf(ratio) else "inf",
        "payback_months": round(payback, 1) if not math.isinf(payback) else "inf",
        "monthly_expenses": expenses,
        "monthly_burn": round(burn, 2),
        "runway_months": round(runway, 1) if not math.isinf(runway) else "inf",
        "mrr_gap": gap,
        "ltv_str": ltv_str,
        "ratio_str": ratio_str,
        "payback_str": payback_str,
        "runway_str": runway_str,
    }

    if not args.json:
        _print_unit_economics(result, mrr_str=ltv_str, ratio_str=ratio_str, payback_str=payback_str, runway_str=runway_str, gap=gap)

    return result


def _print_unit_economics(r: dict, mrr_str: str, ratio_str: str, payback_str: str, runway_str: str, gap: dict) -> None:
    print("=" * 50)
    print("UNIT ECONOMICS")
    print("=" * 50)
    print(f"  MRR:                ${r['mrr']:,.0f}")
    print(f"  Clients:            {r['clients']}")
    print(f"  ARPU:               ${r['arpu']:,.0f}/mo")
    print(f"  Gross Margin:       {r['gross_margin_pct']}%")
    print(f"  Monthly Churn:      {r['monthly_churn_rate_pct']}%")
    print()
    print(f"  LTV:                {mrr_str}")
    print(f"  CAC:                ${r['cac']:,.0f}")
    print(f"  LTV:CAC:            {ratio_str}")
    print(f"  Payback Period:     {payback_str}")
    print()
    print(f"  Monthly Expenses:   ${r['monthly_expenses']:,.0f}")
    print(f"  Monthly Net:        ${r['monthly_burn']:,.0f} ({'PROFITABLE' if r['monthly_burn'] >= 0 else 'BURNING'})")
    print(f"  Runway:             {runway_str}")
    print()
    print("MRR PROGRESS")
    print("-" * 40)
    bar_filled = int((gap["pct_complete"] / 100) * 20)
    bar = "#" * bar_filled + "." * (20 - bar_filled)
    print(f"  ${gap['current_mrr']:,.0f} / ${gap['target_mrr']:,.0f} [{bar}] {gap['pct_complete']}%")
    print(f"  Gap: ${gap['gap']:,.0f} | {gap['days_remaining']} days to {gap['target_date']}")


def cmd_forecast(args: argparse.Namespace) -> dict:
    months = args.months
    mrr = args.mrr
    growth = args.growth  # monthly MRR growth rate
    churn = args.churn

    projection = []
    current = mrr
    for m in range(months + 1):
        target_hit = current >= MRR_TARGET
        projection.append({
            "month": m,
            "mrr": round(current, 2),
            "target_hit": target_hit,
        })
        if m < months:
            current = current * (1 + growth) * (1 - churn)

    target_month = next((p["month"] for p in projection if p["target_hit"]), None)

    result = {
        "projection": projection,
        "months": months,
        "starting_mrr": mrr,
        "monthly_growth_rate_pct": round(growth * 100, 1),
        "monthly_churn_rate_pct": round(churn * 100, 2),
        "final_mrr": projection[-1]["mrr"],
        "target": MRR_TARGET,
        "target_hit_month": target_month,
    }

    if not args.json:
        print("=" * 50)
        print(f"REVENUE FORECAST - {months} months")
        print("=" * 50)
        print(f"  Starting MRR: ${mrr:,.0f} | Growth: {growth*100:.1f}%/mo | Churn: {churn*100:.2f}%/mo")
        print()
        for p in projection:
            marker = " ** TARGET HIT **" if p["mrr"] >= MRR_TARGET and (p["month"] == 0 or projection[p["month"]-1]["mrr"] < MRR_TARGET) else ""
            print(f"  Month {p['month']:2d}: ${p['mrr']:8,.0f}{marker}")
        print()
        if target_month is not None:
            print(f"  Target ${MRR_TARGET:,.0f} hit at month {target_month}")
        else:
            print(f"  Target ${MRR_TARGET:,.0f} NOT reached in {months} months at this growth rate")

    return result


def cmd_scenario(args: argparse.Namespace) -> dict:
    scenario_key = args.type
    if scenario_key not in SCENARIOS:
        return {"error": f"Invalid scenario type. Choose: {', '.join(SCENARIOS.keys())}"}

    s = SCENARIOS[scenario_key]
    months = args.months
    mrr = args.mrr

    projection = project_mrr_scenario(
        starting_mrr=mrr,
        months=months,
        new_clients_per_month=s["new_clients_per_month"],
        avg_deal_size=s["avg_deal_size"],
        monthly_churn_rate=s["monthly_churn_rate"],
        expansion_pct=s["expansion_pct"],
    )

    target_month = next((i for i, v in enumerate(projection) if v >= MRR_TARGET), None)
    expenses = args.expenses
    final_net = projection[-1] - expenses

    result = {
        "scenario": scenario_key,
        "label": s["label"],
        "description": s["description"],
        "probability": s["probability"],
        "assumptions": {
            "new_clients_per_month": s["new_clients_per_month"],
            "avg_deal_size": s["avg_deal_size"],
            "monthly_churn_rate_pct": s["monthly_churn_rate"] * 100,
            "expansion_pct": s["expansion_pct"] * 100,
        },
        "projection": [{"month": i, "mrr": v} for i, v in enumerate(projection)],
        "final_mrr": projection[-1],
        "target_hit_month": target_month,
        "final_monthly_net": round(final_net, 2),
    }

    if not args.json:
        print("=" * 50)
        print(f"SCENARIO: {s['label'].upper()}")
        print("=" * 50)
        print(f"  {s['description']}")
        print(f"  Probability: {int(s['probability']*100)}%")
        print()
        print("  Assumptions:")
        print(f"    New clients/mo:  {s['new_clients_per_month']}")
        print(f"    Avg deal size:   ${s['avg_deal_size']:,.0f}")
        print(f"    Monthly churn:   {s['monthly_churn_rate']*100:.1f}%")
        print(f"    Expansion:       {s['expansion_pct']*100:.0f}%/mo")
        print()
        print("  MRR Projection:")
        for i, v in enumerate(projection):
            marker = " ** TARGET **" if v >= MRR_TARGET and (i == 0 or projection[i-1] < MRR_TARGET) else ""
            print(f"    Month {i:2d}: ${v:8,.0f}{marker}")
        print()
        if target_month is not None:
            print(f"  Target ${MRR_TARGET:,.0f} reached at month {target_month}")
        else:
            print(f"  Target ${MRR_TARGET:,.0f} NOT reached in {months} months")
        print(f"  Final monthly net (after ${expenses}/mo expenses): ${final_net:,.0f}")

    return result


def cmd_concentration(args: argparse.Namespace) -> dict:
    client_revenue: dict[str, float]
    if args.clients:
        try:
            client_revenue = json.loads(args.clients)
            client_revenue = {k: float(v) for k, v in client_revenue.items()}
        except (json.JSONDecodeError, ValueError):
            return {"error": "Invalid JSON for --clients. Use: '{\"Top Client\": 2500, \"Other\": 191}'"}
    else:
        client_revenue = DEFAULT_CLIENT_REVENUE

    total = sum(client_revenue.values())
    hhi = calc_herfindahl(client_revenue)
    interpretation = interpret_hhi(hhi)

    shares = {k: round((v / total) * 100, 1) for k, v in client_revenue.items()}
    largest = max(client_revenue, key=lambda k: client_revenue[k])
    largest_share = shares[largest]

    # How many clients needed to get HHI below 0.5?
    # If we add N equal-revenue clients alongside existing, what's new HHI?
    safe_hhi_clients = _clients_needed_for_hhi(client_revenue, target_hhi=0.5)

    result = {
        "client_revenue": client_revenue,
        "total_mrr": round(total, 2),
        "revenue_shares_pct": shares,
        "hhi": round(hhi, 4),
        "interpretation": interpretation,
        "largest_client": largest,
        "largest_share_pct": largest_share,
        "clients_needed_for_safe_hhi": safe_hhi_clients,
    }

    if not args.json:
        print("=" * 50)
        print("CLIENT CONCENTRATION RISK (Herfindahl Index)")
        print("=" * 50)
        print()
        for client, rev in client_revenue.items():
            share = shares[client]
            bar = "#" * int(share / 5)
            print(f"  {client:20s} ${rev:7,.0f}  {share:5.1f}%  {bar}")
        print()
        print(f"  Total MRR:  ${total:,.0f}")
        print(f"  HHI:        {hhi:.4f}  =>  {interpretation.upper()}")
        print()
        print(f"  Largest client ({largest}) = {largest_share}% of revenue")
        if hhi > 0.5:
            print(f"  Need ~{safe_hhi_clients} new client(s) at avg deal size to reach safe HHI (<0.5)")
        else:
            print("  Concentration is within acceptable range.")

    return result


def _clients_needed_for_hhi(current: dict[str, float], target_hhi: float = 0.5) -> int:
    """Estimate how many $1,000/mo clients to add to reach target HHI."""
    clients = dict(current)
    avg_new_deal = 1000.0
    n = 0
    while calc_herfindahl(clients) > target_hhi and n < 20:
        n += 1
        clients[f"New Client {n}"] = avg_new_deal
    return n


def cmd_runway(args: argparse.Namespace) -> dict:
    cash = args.cash
    expenses = args.expenses
    mrr = args.mrr
    net = mrr - expenses
    burn = -net if net < 0 else 0
    runway = calc_runway(cash, burn)
    runway_str = f"{runway:.0f} months" if not math.isinf(runway) else "inf (profitable)"

    # Worst-case: what if the top client churns? (largest revenue stream in the default split)
    top_client_revenue = max(DEFAULT_CLIENT_REVENUE.values(), default=0.0) if DEFAULT_CLIENT_REVENUE else 0.0
    post_churn_mrr = max(mrr - top_client_revenue, 0)
    post_churn_net = post_churn_mrr - expenses
    post_churn_burn = -post_churn_net if post_churn_net < 0 else 0
    post_churn_runway = calc_runway(cash, post_churn_burn)
    post_churn_str = f"{post_churn_runway:.0f} months" if not math.isinf(post_churn_runway) else "inf"

    result = {
        "cash_on_hand": cash,
        "monthly_expenses": expenses,
        "current_mrr": mrr,
        "monthly_net": round(net, 2),
        "monthly_burn": round(burn, 2),
        "runway_months": round(runway, 1) if not math.isinf(runway) else "inf",
        "runway_str": runway_str,
        "worst_case": {
            "scenario": "top client churns",
            "remaining_mrr": round(post_churn_mrr, 2),
            "monthly_net": round(post_churn_net, 2),
            "runway_months": round(post_churn_runway, 1) if not math.isinf(post_churn_runway) else "inf",
            "runway_str": post_churn_str,
        },
    }

    if not args.json:
        print("=" * 50)
        print("CASH RUNWAY")
        print("=" * 50)
        print(f"  Cash on hand:      ${cash:,.0f}")
        print(f"  Monthly expenses:  ${expenses:,.0f}")
        print(f"  Monthly MRR:       ${mrr:,.0f}")
        print(f"  Monthly net:       ${net:,.0f} ({'PROFITABLE' if net >= 0 else 'BURNING'})")
        print(f"  Runway:            {runway_str}")
        print()
        print("  WORST CASE: top client churns today")
        print(f"    Remaining MRR:   ${post_churn_mrr:,.0f}")
        print(f"    Monthly net:     ${post_churn_net:,.0f}")
        print(f"    Runway:          {post_churn_str}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Financial Modeling Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    sub = parser.add_subparsers(dest="command")

    # unit-economics
    p_ue = sub.add_parser("unit-economics", help="Calculate CAC, LTV, payback period, burn")
    p_ue.add_argument("--mrr", type=float, default=DEFAULT_MRR, help=f"Current MRR (default: {DEFAULT_MRR})")
    p_ue.add_argument("--clients", type=int, default=DEFAULT_CLIENTS, help=f"Number of clients (default: {DEFAULT_CLIENTS})")
    p_ue.add_argument("--churn", type=float, default=DEFAULT_CHURN_RATE, help=f"Monthly churn rate 0-1 (default: {DEFAULT_CHURN_RATE})")
    p_ue.add_argument("--gross-margin", dest="gross_margin", type=float, default=DEFAULT_GROSS_MARGIN, help=f"Gross margin 0-1 (default: {DEFAULT_GROSS_MARGIN})")
    p_ue.add_argument("--cac", type=float, default=DEFAULT_CAC, help=f"Customer acquisition cost $ (default: {DEFAULT_CAC})")
    p_ue.add_argument("--expenses", type=float, default=DEFAULT_OVERHEAD, help=f"Monthly expenses $ (default: {DEFAULT_OVERHEAD})")
    p_ue.add_argument("--cash", type=float, default=DEFAULT_CASH_ON_HAND, help=f"Cash on hand $ (default: {DEFAULT_CASH_ON_HAND})")

    # forecast
    p_fc = sub.add_parser("forecast", help="Project MRR over time with growth rate")
    p_fc.add_argument("--months", type=int, default=6, help="Months to project (default: 6)")
    p_fc.add_argument("--mrr", type=float, default=DEFAULT_MRR, help=f"Starting MRR (default: {DEFAULT_MRR})")
    p_fc.add_argument("--growth", type=float, default=0.10, help="Monthly MRR growth rate 0-1 (default: 0.10)")
    p_fc.add_argument("--churn", type=float, default=DEFAULT_CHURN_RATE, help=f"Monthly churn rate (default: {DEFAULT_CHURN_RATE})")

    # scenario
    p_sc = sub.add_parser("scenario", help="Bull/base/bear scenario modeling")
    p_sc.add_argument("--type", choices=["bull", "base", "bear"], default="base", help="Scenario type (default: base)")
    p_sc.add_argument("--months", type=int, default=6, help="Months to project (default: 6)")
    p_sc.add_argument("--mrr", type=float, default=DEFAULT_MRR, help=f"Starting MRR (default: {DEFAULT_MRR})")
    p_sc.add_argument("--expenses", type=float, default=DEFAULT_OVERHEAD, help=f"Monthly expenses (default: {DEFAULT_OVERHEAD})")

    # concentration
    p_con = sub.add_parser("concentration", help="Client concentration risk (Herfindahl Index)")
    p_con.add_argument("--clients", help='JSON: \'{"ClientName": revenue, ...}\' (default: CC current split)')

    # runway
    p_rw = sub.add_parser("runway", help="Cash runway and worst-case analysis")
    p_rw.add_argument("--cash", type=float, default=DEFAULT_CASH_ON_HAND, help=f"Cash on hand $ (default: {DEFAULT_CASH_ON_HAND})")
    p_rw.add_argument("--expenses", type=float, default=DEFAULT_OVERHEAD, help=f"Monthly expenses $ (default: {DEFAULT_OVERHEAD})")
    p_rw.add_argument("--mrr", type=float, default=DEFAULT_MRR, help=f"Current MRR (default: {DEFAULT_MRR})")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Propagate --json flag to subcommand handler
    if not hasattr(args, "json"):
        args.json = False

    command_map = {
        "unit-economics": cmd_unit_economics,
        "forecast": cmd_forecast,
        "scenario": cmd_scenario,
        "concentration": cmd_concentration,
        "runway": cmd_runway,
    }

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handler = command_map.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

    result = handler(args)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    if isinstance(result, dict) and "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
