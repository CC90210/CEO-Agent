"""debt_detector.py — turn parsed statement JSON into a debt-load summary.

Phase 7.2 of the SunBiz CRM build. The vision parser already does most
of the work (identified_loan_payments + recurring_debits). This module
aggregates those across multiple months' statements into a single
underwriter-friendly summary the operator + sales angle generator both
consume.

CLI:
  python scripts/underwriting/debt_detector.py summarize --statements <file1.json> <file2.json> ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────
# Heuristics
# ─────────────────────────────────────────────────────────────────────

# Frequency -> approximate monthly multiplier. Daily ACH from a lender
# is 22 business days, weekly ~4.3 weeks, monthly = 1.
FREQUENCY_MONTHLY_MULTIPLIER = {
    "daily": 22.0,
    "weekly": 4.3,
    "bi-weekly": 2.0,
    "biweekly": 2.0,
    "monthly": 1.0,
}


def _normalize_freq(freq: str | None) -> float:
    if not freq:
        return 1.0  # conservative default: assume monthly
    return FREQUENCY_MONTHLY_MULTIPLIER.get(freq.lower().strip(), 1.0)


# ─────────────────────────────────────────────────────────────────────
# Cross-statement aggregation
# ─────────────────────────────────────────────────────────────────────


def summarize_debt(statements: list[dict]) -> dict:
    """Given a list of parsed statements (output of statement_parser),
    return a single debt-load summary."""
    if not statements:
        return {
            "summary": "no statements provided",
            "monthly_debt_service": 0,
            "lender_count": 0,
            "lenders": [],
            "total_nsf_events": 0,
            "total_overdraft_days": 0,
            "average_monthly_revenue": 0,
            "debt_to_revenue_ratio": None,
        }

    # Aggregate identified_loan_payments across statements. Group by
    # (lender_hint lowercased) so the same lender showing across 3 months
    # of statements is one row, not three.
    by_lender: dict[str, dict] = {}
    for stmt in statements:
        for entry in stmt.get("identified_loan_payments") or []:
            hint = (entry.get("lender_hint") or "unknown").strip().lower()
            amt = float(entry.get("amount") or 0)
            freq = entry.get("frequency") or "monthly"
            monthly_eq = amt * _normalize_freq(freq)
            row = by_lender.setdefault(hint, {
                "lender_hint": entry.get("lender_hint") or "unknown",
                "monthly_estimate": 0.0,
                "occurrences": 0,
                "frequencies": set(),
            })
            row["monthly_estimate"] += monthly_eq
            row["occurrences"] += 1
            row["frequencies"].add(freq)

    # Normalize the running sums to averages (operator looks at one
    # representative month, not the cumulative across statements).
    statement_count = max(1, len(statements))
    lenders_out = []
    monthly_debt_service = 0.0
    for hint, row in by_lender.items():
        avg_monthly = row["monthly_estimate"] / statement_count
        monthly_debt_service += avg_monthly
        lenders_out.append({
            "lender_hint": row["lender_hint"],
            "estimated_monthly_payment": round(avg_monthly, 2),
            "observed_in_statements": row["occurrences"],
            "frequencies_observed": sorted(row["frequencies"]),
        })
    lenders_out.sort(key=lambda r: r["estimated_monthly_payment"], reverse=True)

    total_nsf = sum(int(s.get("nsf_events") or 0) for s in statements)
    total_overdraft = sum(int(s.get("overdraft_days") or 0) for s in statements)
    deposits_sum = sum(float(s.get("total_deposits") or 0) for s in statements)
    avg_revenue = deposits_sum / statement_count if statement_count else 0.0

    debt_to_revenue = None
    if avg_revenue > 0:
        debt_to_revenue = round(monthly_debt_service / avg_revenue, 3)

    # Plain-English summary string the operator can paste into a CRM
    # note without re-shaping the JSON.
    pieces = []
    pieces.append(
        f"{len(lenders_out)} active lender(s) observed across {statement_count} statement(s); "
        f"est. monthly debt service ${monthly_debt_service:,.0f}."
    )
    if avg_revenue > 0:
        pieces.append(f"Avg monthly deposits ${avg_revenue:,.0f}.")
    if debt_to_revenue is not None:
        if debt_to_revenue > 0.5:
            pieces.append(f"D/R ratio {debt_to_revenue:.0%} — heavy stack; likely consolidation play.")
        elif debt_to_revenue > 0.2:
            pieces.append(f"D/R ratio {debt_to_revenue:.0%} — moderate stack; clean second position possible.")
        else:
            pieces.append(f"D/R ratio {debt_to_revenue:.0%} — light stack; strong first-position candidate.")
    if total_nsf > 0:
        pieces.append(f"{total_nsf} NSF event(s) across the window — flag for lender QA.")
    if total_overdraft > 5:
        pieces.append(f"{total_overdraft} overdraft days — cash-management concern.")

    return {
        "summary": " ".join(pieces),
        "monthly_debt_service": round(monthly_debt_service, 2),
        "lender_count": len(lenders_out),
        "lenders": lenders_out,
        "total_nsf_events": total_nsf,
        "total_overdraft_days": total_overdraft,
        "average_monthly_revenue": round(avg_revenue, 2),
        "debt_to_revenue_ratio": debt_to_revenue,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="debt_detector")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("summarize", help="Cross-statement debt summary")
    s.add_argument("--statements", nargs="+", required=True,
                   help="Paths to parsed-statement JSON files")
    s.set_defaults(func=lambda a: _summarize_from_files(a.statements))

    args = p.parse_args(argv)
    try:
        result = args.func(args)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"ok": True, "result": result}, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))
    return 0


def _summarize_from_files(paths: list[str]) -> dict:
    statements: list[dict] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            raise FileNotFoundError(f"{p} does not exist")
        statements.append(json.loads(p.read_text(encoding="utf-8")))
    return summarize_debt(statements)


if __name__ == "__main__":
    sys.exit(main())
