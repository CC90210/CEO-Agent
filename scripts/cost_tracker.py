"""
Cost Tracker — Per-Operation Label:Units Tracking for Business-Empire-Agent
Follows the Claude Code internal cost tracking pattern: label:units per operation.
Covers all CLI tools (supabase, stripe, n8n, late, playwright) and MCP calls.
No external dependencies — stdlib only (sqlite3, argparse, uuid, datetime).

Usage:
  python scripts/cost_tracker.py log --label "supabase_query" --units 1 --detail "select from memories"
  python scripts/cost_tracker.py log --label "late_post" --units 2 --detail "cross-post to 8 accounts"
  python scripts/cost_tracker.py log --label "n8n_execute" --units 1 --detail "workflow 42"
  python scripts/cost_tracker.py log --label "playwright_session" --units 5 --detail "skool lesson edit"

  python scripts/cost_tracker.py summary [--period today|week|month|all] [--json]
  python scripts/cost_tracker.py session [--json]

  python scripts/cost_tracker.py budget --set supabase_query 100 --period daily
  python scripts/cost_tracker.py budget --check [--json]
  python scripts/cost_tracker.py budget --list [--json]

Flags:
  --json    Output raw JSON for agent consumption (supported on all commands)
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Project root resolution — works from any cwd
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Walk up from this file until we find a .git directory."""
    candidate = Path(__file__).resolve().parent
    for _ in range(6):
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Fallback: two levels up from scripts/
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
DB_PATH = PROJECT_ROOT / "tmp" / "cost_tracker.db"


# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they do not already exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            session_id  TEXT    NOT NULL,
            label       TEXT    NOT NULL,
            units       REAL    NOT NULL,
            detail      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_events_label     ON events(label);
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);

        CREATE TABLE IF NOT EXISTS budgets (
            label       TEXT PRIMARY KEY,
            max_units   REAL NOT NULL,
            period      TEXT NOT NULL DEFAULT 'daily'
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Session ID resolution
# ---------------------------------------------------------------------------

def _session_id() -> str:
    """Return BRAVO_SESSION_ID env var or generate a UUID for this process."""
    sid = os.environ.get("BRAVO_SESSION_ID", "").strip()
    if sid:
        return sid
    # Stable within this process invocation
    if not hasattr(_session_id, "_cached"):
        _session_id._cached = str(uuid.uuid4())  # type: ignore[attr-defined]
    return _session_id._cached  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def _period_start(period: str) -> str:
    """Return ISO timestamp string for the start of the requested period (UTC)."""
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        # Monday of current week
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "all":
        return "1970-01-01T00:00:00+00:00"
    else:
        print(f"ERROR: Unknown period '{period}'. Options: today, week, month, all", file=sys.stderr)
        sys.exit(1)
    return start.isoformat()


def _budget_period_start(period: str) -> str:
    """Return period start for budget enforcement ('daily' or 'weekly' or 'monthly')."""
    mapping = {"daily": "today", "weekly": "week", "monthly": "month"}
    return _period_start(mapping.get(period, "today"))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2))


def _print_table(headers: list[str], rows: list[list[str]], title: str = "") -> None:
    """Print an ASCII table to stdout."""
    if title:
        print(f"\n{title}")
        print("-" * len(title))
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in col_widths))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print()


# ---------------------------------------------------------------------------
# Subcommand: log
# ---------------------------------------------------------------------------

def cmd_log(args: argparse.Namespace) -> None:
    """Record a single cost event."""
    if args.units < 0:
        print("ERROR: --units must be non-negative", file=sys.stderr)
        sys.exit(1)

    conn = _get_connection()
    ts = datetime.now(timezone.utc).isoformat()
    sid = _session_id()

    conn.execute(
        "INSERT INTO events (timestamp, session_id, label, units, detail) VALUES (?, ?, ?, ?, ?)",
        (ts, sid, args.label.strip(), args.units, args.detail or None),
    )
    conn.commit()
    conn.close()

    result = {
        "status": "logged",
        "label": args.label.strip(),
        "units": args.units,
        "detail": args.detail,
        "session_id": sid,
        "timestamp": ts,
    }

    if args.json:
        _print_json(result)
    else:
        detail_str = f" — {args.detail}" if args.detail else ""
        print(f"Logged: {args.label}:{args.units}{detail_str}")


# ---------------------------------------------------------------------------
# Subcommand: summary
# ---------------------------------------------------------------------------

def cmd_summary(args: argparse.Namespace) -> None:
    """Show aggregated cost breakdown by label for a time window."""
    period = getattr(args, "period", "today")
    start_ts = _period_start(period)

    conn = _get_connection()
    rows = conn.execute(
        """
        SELECT
            label,
            COUNT(*)        AS count,
            SUM(units)      AS total_units,
            AVG(units)      AS avg_units,
            MAX(timestamp)  AS last_used
        FROM events
        WHERE timestamp >= ?
        GROUP BY label
        ORDER BY total_units DESC
        """,
        (start_ts,),
    ).fetchall()

    grand_total = conn.execute(
        "SELECT SUM(units) FROM events WHERE timestamp >= ?", (start_ts,)
    ).fetchone()[0] or 0.0

    conn.close()

    if args.json:
        _print_json({
            "period": period,
            "period_start": start_ts,
            "grand_total_units": round(grand_total, 4),
            "breakdown": [
                {
                    "label": r["label"],
                    "count": r["count"],
                    "total_units": round(r["total_units"], 4),
                    "avg_units": round(r["avg_units"], 4),
                    "last_used": r["last_used"],
                }
                for r in rows
            ],
        })
        return

    if not rows:
        print(f"No events recorded for period: {period}")
        return

    table_rows = [
        [
            r["label"],
            r["count"],
            f"{r['total_units']:.2f}",
            f"{r['avg_units']:.2f}",
            r["last_used"][:19].replace("T", " "),
        ]
        for r in rows
    ]
    _print_table(
        ["Label", "Count", "Total Units", "Avg Units", "Last Used"],
        table_rows,
        title=f"Cost Summary — {period}  (grand total: {grand_total:.2f} units)",
    )


# ---------------------------------------------------------------------------
# Subcommand: session
# ---------------------------------------------------------------------------

def cmd_session(args: argparse.Namespace) -> None:
    """Show all events for the current session."""
    sid = _session_id()

    conn = _get_connection()
    rows = conn.execute(
        """
        SELECT timestamp, label, units, detail
        FROM events
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (sid,),
    ).fetchall()

    total = sum(r["units"] for r in rows)
    conn.close()

    if args.json:
        _print_json({
            "session_id": sid,
            "event_count": len(rows),
            "total_units": round(total, 4),
            "events": [
                {
                    "timestamp": r["timestamp"],
                    "label": r["label"],
                    "units": r["units"],
                    "detail": r["detail"],
                }
                for r in rows
            ],
        })
        return

    if not rows:
        print(f"No events for session: {sid}")
        return

    table_rows = [
        [
            r["timestamp"][:19].replace("T", " "),
            r["label"],
            f"{r['units']:.2f}",
            r["detail"] or "",
        ]
        for r in rows
    ]
    _print_table(
        ["Timestamp", "Label", "Units", "Detail"],
        table_rows,
        title=f"Session: {sid}  ({len(rows)} events, {total:.2f} total units)",
    )


# ---------------------------------------------------------------------------
# Subcommand: budget
# ---------------------------------------------------------------------------

def cmd_budget(args: argparse.Namespace) -> None:
    """Set budgets or check current spend against budgets."""
    conn = _get_connection()

    # --set label max_units --period period
    if args.set:
        label = args.set.strip()
        if args.max_units is None:
            print("ERROR: --set requires a max_units value (positional after the label)", file=sys.stderr)
            sys.exit(1)
        period = getattr(args, "period", "daily") or "daily"
        valid_periods = ("daily", "weekly", "monthly")
        if period not in valid_periods:
            print(f"ERROR: --period must be one of {valid_periods}", file=sys.stderr)
            sys.exit(1)
        conn.execute(
            "INSERT INTO budgets (label, max_units, period) VALUES (?, ?, ?) "
            "ON CONFLICT(label) DO UPDATE SET max_units=excluded.max_units, period=excluded.period",
            (label, args.max_units, period),
        )
        conn.commit()
        conn.close()
        result = {"status": "budget_set", "label": label, "max_units": args.max_units, "period": period}
        if args.json:
            _print_json(result)
        else:
            print(f"Budget set: {label} = {args.max_units} units/{period}")
        return

    # --list: show all budgets
    if args.list:
        budgets = conn.execute("SELECT label, max_units, period FROM budgets ORDER BY label").fetchall()
        conn.close()
        if args.json:
            _print_json([{"label": b["label"], "max_units": b["max_units"], "period": b["period"]} for b in budgets])
            return
        if not budgets:
            print("No budgets configured.")
            return
        _print_table(
            ["Label", "Max Units", "Period"],
            [[b["label"], f"{b['max_units']:.2f}", b["period"]] for b in budgets],
            title="Configured Budgets",
        )
        return

    # --check: compare current spend vs budgets
    budgets = conn.execute("SELECT label, max_units, period FROM budgets ORDER BY label").fetchall()

    if not budgets:
        conn.close()
        if args.json:
            _print_json({"status": "no_budgets", "alerts": []})
        else:
            print("No budgets configured. Use --set to add one.")
        return

    alerts = []
    check_rows = []
    for b in budgets:
        start_ts = _budget_period_start(b["period"])
        spent_row = conn.execute(
            "SELECT COALESCE(SUM(units), 0) AS spent FROM events WHERE label = ? AND timestamp >= ?",
            (b["label"], start_ts),
        ).fetchone()
        spent = spent_row["spent"]
        pct = (spent / b["max_units"] * 100) if b["max_units"] > 0 else 0.0
        over = spent > b["max_units"]
        status = "OVER" if over else ("WARN" if pct >= 80 else "OK")
        check_rows.append([b["label"], f"{spent:.2f}", f"{b['max_units']:.2f}", b["period"], f"{pct:.1f}%", status])
        if over:
            alerts.append({"label": b["label"], "spent": round(spent, 4), "max_units": b["max_units"], "period": b["period"]})

    conn.close()

    if args.json:
        _print_json({
            "status": "over_budget" if alerts else "within_budget",
            "alerts": alerts,
            "details": [
                {
                    "label": r[0],
                    "spent": float(r[1]),
                    "max_units": float(r[2]),
                    "period": r[3],
                    "pct_used": r[4],
                    "status": r[5],
                }
                for r in check_rows
            ],
        })
        return

    _print_table(
        ["Label", "Spent", "Budget", "Period", "% Used", "Status"],
        check_rows,
        title="Budget Check",
    )
    if alerts:
        print(f"ALERT: {len(alerts)} label(s) over budget: {', '.join(a['label'] for a in alerts)}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cost_tracker",
        description="Per-operation label:units cost tracking for Business-Empire-Agent.",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    # --- log ---
    p_log = sub.add_parser("log", help="Record a cost event")
    p_log.add_argument("--label", required=True, help="Operation label (e.g. supabase_query)")
    p_log.add_argument("--units", required=True, type=float, help="Cost units for this operation")
    p_log.add_argument("--detail", default=None, help="Optional human-readable detail")
    p_log.add_argument("--json", action="store_true", help="Output JSON")

    # --- summary ---
    p_summary = sub.add_parser("summary", help="Show cost breakdown by label")
    p_summary.add_argument(
        "--period",
        default="today",
        choices=["today", "week", "month", "all"],
        help="Time window (default: today)",
    )
    p_summary.add_argument("--json", action="store_true", help="Output JSON")

    # --- session ---
    p_session = sub.add_parser("session", help="Show costs for the current session")
    p_session.add_argument("--json", action="store_true", help="Output JSON")

    # --- budget ---
    p_budget = sub.add_parser("budget", help="Set or check label budgets")
    budget_group = p_budget.add_mutually_exclusive_group(required=True)
    budget_group.add_argument("--set", metavar="LABEL", help="Label to set budget for")
    budget_group.add_argument("--check", action="store_true", help="Check all labels against budgets")
    budget_group.add_argument("--list", action="store_true", help="List all configured budgets")
    p_budget.add_argument(
        "max_units",
        nargs="?",
        type=float,
        default=None,
        help="Max units allowed per period (required with --set)",
    )
    p_budget.add_argument(
        "--period",
        default="daily",
        choices=["daily", "weekly", "monthly"],
        help="Budget reset period (default: daily)",
    )
    p_budget.add_argument("--json", action="store_true", help="Output JSON")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "log": cmd_log,
        "summary": cmd_summary,
        "session": cmd_session,
        "budget": cmd_budget,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
