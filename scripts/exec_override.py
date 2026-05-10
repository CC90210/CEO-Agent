"""V6 BUILD 4 — operator-approval CLI for the override flow.

The agent never holds a token. When `exec_guard.py` blocks a command, it
auto-creates an `override_request` row and prints the request_id. The
operator has TWO paths to authorize:

    1. CLI (this script, TTY-gated):
         python scripts/exec_override.py approve req-<id>

    2. Dashboard (V6 Apex Phase 2, 2026-05-10):
         Open the /overrides page on the Vercel command center, click
         Approve. `scripts/exec_override_consumer.py loop` (run on CC's
         machine under PM2) polls the Supabase mirror every ~5s and
         applies the dashboard's decision to local SQLite the same way
         this CLI does. The HMAC signing of the SQLite row stays local
         either way — Vercel only records intent.

Either path produces the same result: the agent's next attempt at the SAME
command goes through. Single-use, HMAC-signed at-rest, command-hash-bound,
TTL-capped.

CLI:
  list                                 # last 24h of requests
  list --pending                       # only pending approval
  list --status approved               # filter by status
  approve <id> [--reason "..."]        # operator action; HMAC-signs the row
  deny    <id> [--reason "..."]        # operator action; closes the request
  status  <id>                         # show one request as JSON
  cleanup [--days 7]                   # purge requests older than N days

Refusal layer: `approve` and `deny` are blocked when the parent process is
NOT a TTY and `EMPIRE_OVERRIDE_FORCE_TTY=1` is not set. This stops an LLM
from approving its own override request via a Bash tool call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import state_manager                                  # noqa: E402
from lib.override_crypto import is_tty_caller         # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ── CLI handlers ─────────────────────────────────────────────────────────

def _cmd_list(args) -> int:
    rows = state_manager.list_override_requests(
        status=args.status, limit=args.limit, since_hours=args.since_hours,
    )
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print(f"No override requests in the last {args.since_hours}h"
              f"{f' with status={args.status}' if args.status else ''}.")
        return 0
    for r in rows:
        cmd_short = (r["command"] or "")[:80].replace("\n", " ")
        print(f"  {r['id']}  [{r['status']:9s}]  {r['ts']}  {r['layer']:20s}  {cmd_short}")
    return 0


def _refuse_if_not_tty() -> int | None:
    if not is_tty_caller():
        sys.stderr.write(
            "REFUSED: exec_override approve/deny requires an interactive TTY.\n"
            "  This stops an LLM in a Bash tool call from approving its own request.\n"
            "  If you're CC running this from your terminal and the check is\n"
            "  wrong, set EMPIRE_OVERRIDE_FORCE_TTY=1 to bypass — but do this\n"
            "  ONLY when you're certain the parent process is you, not an agent.\n"
        )
        return 2
    return None


def _cmd_approve(args) -> int:
    refusal = _refuse_if_not_tty()
    if refusal is not None:
        return refusal
    try:
        row = state_manager.approve_override_request(
            args.id,
            approved_by="cc",
            approved_reason=args.reason,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"APPROVED  {row['id']}")
    print(f"  command:  {(row.get('command') or '')[:200]}")
    print(f"  expires:  {row['expires_at']}")
    print(f"  hmac:     {row['hmac_sig'][:16]}…")
    print(f"  reason:   {row.get('approved_reason') or '(none)'}")
    print()
    print("  The agent's next attempt at the EXACT same command will be allowed,")
    print("  marked consumed, and the row sealed (single-use).")
    return 0


def _cmd_deny(args) -> int:
    refusal = _refuse_if_not_tty()
    if refusal is not None:
        return refusal
    ok = state_manager.deny_override_request(args.id, reason=args.reason)
    if not ok:
        print(f"ERROR: request {args.id} not pending (already consumed/denied/expired/missing).",
              file=sys.stderr)
        return 1
    print(f"DENIED  {args.id}")
    if args.reason:
        print(f"  reason:  {args.reason}")
    return 0


def _cmd_status(args) -> int:
    rows = state_manager.list_override_requests(limit=200, since_hours=24*30)
    match = next((r for r in rows if r["id"] == args.id), None)
    if not match:
        print(f"ERROR: request {args.id} not found in the last 30 days.",
              file=sys.stderr)
        return 1
    print(json.dumps(match, indent=2, default=str))
    return 0


def _cmd_cleanup(args) -> int:
    n = state_manager.cleanup_override_requests(older_than_days=args.days)
    print(f"Purged {n} override_request rows older than {args.days} days.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6 BUILD 4 operator-approval CLI")
    sub = p.add_subparsers(dest="command", required=True)

    lst = sub.add_parser("list", help="List recent override requests")
    lst.add_argument("--status", default=None,
                     choices=["pending", "approved", "denied", "expired", "consumed"])
    lst.add_argument("--pending", action="store_true",
                     help="alias for --status pending")
    lst.add_argument("--since-hours", type=int, default=24)
    lst.add_argument("--limit", type=int, default=50)
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(func=_cmd_list)

    apr = sub.add_parser("approve", help="Authorize a pending override request")
    apr.add_argument("id")
    apr.add_argument("--reason", default=None,
                     help="One-line note recorded with the approval")
    apr.set_defaults(func=_cmd_approve)

    dny = sub.add_parser("deny", help="Reject a pending override request")
    dny.add_argument("id")
    dny.add_argument("--reason", default=None)
    dny.set_defaults(func=_cmd_deny)

    st = sub.add_parser("status", help="Show one request as JSON")
    st.add_argument("id")
    st.set_defaults(func=_cmd_status)

    cl = sub.add_parser("cleanup", help="Purge old request rows")
    cl.add_argument("--days", type=int, default=7)
    cl.set_defaults(func=_cmd_cleanup)

    args = p.parse_args(argv)
    if args.command == "list" and getattr(args, "pending", False):
        args.status = "pending"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
