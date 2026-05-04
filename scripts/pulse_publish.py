"""
pulse_publish.py — Atomic, schema-validated writer for Bravo's ceo_pulse.json.

This is the only blessed path to update data/pulse/ceo_pulse.json. Direct
file edits are forbidden (per brain/AGENT_ORCHESTRATION.md § Pulse Protocol).

Why a script and not just an edit:
  1. Atomic write (write-to-temp + rename) — readers never see partial JSON
  2. Schema validation — catches missing fields before publish
  3. Stamps `updated_at` automatically — never stale on republish
  4. Optional inbox notification — pings Atlas + Maven when material fields change

Usage:
  # Refresh from CLI (recommended for CC tonight):
  python scripts/pulse_publish.py refresh \\
    --net-mrr 3322 \\
    --priority "Diversify off Bennett — close 2 new clients before May 15" \\
    --bennett-pct 84

  # Validate current pulse without writing:
  python scripts/pulse_publish.py validate

  # Show current pulse with freshness:
  python scripts/pulse_publish.py status [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PULSE_PATH = REPO_ROOT / "data" / "pulse" / "ceo_pulse.json"
SCHEMA_VERSION = "0.3.0"

REQUIRED_TOP_LEVEL = {"agent", "version", "updated_at", "status", "revenue", "strategy"}
REQUIRED_REVENUE = {"net_mrr_usd", "target_mrr_usd", "gap_usd", "active_clients"}
REQUIRED_STRATEGY = {"current_focus", "top_priority_this_week"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_pulse() -> dict[str, Any] | None:
    if not PULSE_PATH.exists():
        return None
    try:
        return json.loads(PULSE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def validate(payload: dict[str, Any]) -> list[str]:
    """Return list of validation errors. Empty list = valid."""
    errors: list[str] = []
    missing_top = REQUIRED_TOP_LEVEL - set(payload.keys())
    if missing_top:
        errors.append(f"missing top-level fields: {sorted(missing_top)}")
    revenue = payload.get("revenue", {})
    if isinstance(revenue, dict):
        missing_rev = REQUIRED_REVENUE - set(revenue.keys())
        if missing_rev:
            errors.append(f"missing revenue fields: {sorted(missing_rev)}")
        if revenue.get("net_mrr_usd") is not None and not isinstance(revenue["net_mrr_usd"], (int, float)):
            errors.append("revenue.net_mrr_usd must be a number")
    else:
        errors.append("revenue must be an object")
    strategy = payload.get("strategy", {})
    if isinstance(strategy, dict):
        missing_strat = REQUIRED_STRATEGY - set(strategy.keys())
        if missing_strat:
            errors.append(f"missing strategy fields: {sorted(missing_strat)}")
    else:
        errors.append("strategy must be an object")
    if "updated_at" in payload:
        try:
            ts = payload["updated_at"]
            if isinstance(ts, str):
                normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
                datetime.fromisoformat(normalized)
        except (ValueError, TypeError):
            errors.append("updated_at must be ISO 8601")
    return errors


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def cmd_refresh(args: argparse.Namespace) -> int:
    existing = _read_pulse() or {}
    payload = dict(existing)
    payload["agent"] = "Bravo (CEO)"
    payload["version"] = SCHEMA_VERSION
    payload["updated_at"] = _now_iso()
    payload["status"] = args.status or existing.get("status", "ACTIVE")
    if args.session_note:
        payload["session_note"] = args.session_note

    revenue = dict(existing.get("revenue", {}))
    if args.net_mrr is not None:
        revenue["net_mrr_usd"] = args.net_mrr
        revenue["target_mrr_usd"] = revenue.get("target_mrr_usd", 5000)
        revenue["gap_usd"] = max(0, revenue["target_mrr_usd"] - args.net_mrr)
    if args.bennett_pct is not None:
        revenue["bennett_concentration_pct"] = args.bennett_pct
    if args.active_clients is not None:
        revenue["active_clients"] = args.active_clients
    revenue.setdefault("net_mrr_usd", existing.get("revenue", {}).get("net_mrr_usd", 0))
    revenue.setdefault("target_mrr_usd", 5000)
    revenue.setdefault("gap_usd", 5000 - revenue.get("net_mrr_usd", 0))
    revenue.setdefault("active_clients", existing.get("revenue", {}).get("active_clients", 0))
    payload["revenue"] = revenue

    strategy = dict(existing.get("strategy", {}))
    if args.priority:
        strategy["top_priority_this_week"] = args.priority
        strategy.setdefault("current_focus", args.priority)
    if args.focus:
        strategy["current_focus"] = args.focus
    strategy.setdefault("current_focus", existing.get("strategy", {}).get("current_focus", ""))
    strategy.setdefault("top_priority_this_week", existing.get("strategy", {}).get("top_priority_this_week", ""))
    payload["strategy"] = strategy

    errors = validate(payload)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        print("\n(dry-run — pulse not written)", file=sys.stderr)
        return 0

    _atomic_write(PULSE_PATH, payload)
    print(f"OK — ceo_pulse refreshed at {payload['updated_at']}")
    print(f"  net_mrr_usd:    ${revenue['net_mrr_usd']:,}")
    print(f"  gap_usd:        ${revenue['gap_usd']:,}")
    print(f"  priority:       {strategy['top_priority_this_week']}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = _read_pulse()
    if payload is None:
        print(f"ERROR — pulse not readable at {PULSE_PATH}", file=sys.stderr)
        return 2
    errors = validate(payload)
    if args.json:
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    else:
        if errors:
            print("INVALID:")
            for e in errors:
                print(f"  - {e}")
        else:
            print("VALID")
    return 0 if not errors else 1


def cmd_status(args: argparse.Namespace) -> int:
    payload = _read_pulse()
    if payload is None:
        print(f"ERROR — pulse not readable at {PULSE_PATH}", file=sys.stderr)
        return 2
    updated = payload.get("updated_at", "?")
    age_hours: float | None = None
    try:
        ts = updated[:-1] + "+00:00" if isinstance(updated, str) and updated.endswith("Z") else updated
        dt = datetime.fromisoformat(ts) if isinstance(ts, str) else None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        pass
    summary = {
        "updated_at": updated,
        "age_hours": round(age_hours, 1) if age_hours is not None else None,
        "freshness": (
            "FRESH" if age_hours is not None and age_hours < 24
            else "AGING" if age_hours is not None and age_hours < 168
            else "STALE" if age_hours is not None
            else "UNKNOWN"
        ),
        "net_mrr_usd": payload.get("revenue", {}).get("net_mrr_usd"),
        "gap_usd": payload.get("revenue", {}).get("gap_usd"),
        "priority": payload.get("strategy", {}).get("top_priority_this_week"),
    }
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"updated_at:  {summary['updated_at']}")
        print(f"age_hours:   {summary['age_hours']}")
        print(f"freshness:   {summary['freshness']}")
        print(f"net_mrr_usd: ${summary['net_mrr_usd']}")
        print(f"gap_usd:     ${summary['gap_usd']}")
        print(f"priority:    {summary['priority']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Bravo ceo_pulse atomic publisher.")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("refresh", help="Update ceo_pulse with new values")
    pr.add_argument("--net-mrr", type=float, default=None, help="Current net MRR (USD)")
    pr.add_argument("--bennett-pct", type=float, default=None, help="Bennett concentration % of MRR")
    pr.add_argument("--active-clients", type=int, default=None)
    pr.add_argument("--priority", type=str, default=None, help="This week's #1 priority")
    pr.add_argument("--focus", type=str, default=None, help="Current strategic focus")
    pr.add_argument("--status", type=str, default=None, help="ACTIVE | PAUSED | ESCALATED")
    pr.add_argument("--session-note", type=str, default=None)
    pr.add_argument("--dry-run", action="store_true")

    pv = sub.add_parser("validate", help="Validate current pulse against schema")
    pv.add_argument("--json", action="store_true")

    ps = sub.add_parser("status", help="Show current pulse summary + freshness")
    ps.add_argument("--json", action="store_true")

    args = p.parse_args()
    handlers = {"refresh": cmd_refresh, "validate": cmd_validate, "status": cmd_status}
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
