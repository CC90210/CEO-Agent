"""
shop_out_track — read state for one or more shop-out rounds.

Two-agent workflow: the SENDER agent fires shop_out.py; the TRACKING
agent uses THIS tool to poll round state, see per-lender response
status, and update statuses as lenders reply.

Reads from shopping_threads (migration 088). Reply detection is a
separate concern owned by the response classifier daemon (SunBiz-Agent
lender_response_classifier.py); this tool only READS that state and
optionally PATCHES it when the tracking agent has manual updates.

CLI
---

    # Round-level read by id
    python scripts/outbound/shop_out_track.py show --round-id <uuid>

    # Round-level read by (tenant, lead, round_number)
    python scripts/outbound/shop_out_track.py show \\
        --tenant-id <uuid> --lead-id <id> --round-number N

    # Lead-level list (all rounds for a lead)
    python scripts/outbound/shop_out_track.py list \\
        --tenant-id <uuid> --lead-id <id>

    # Tenant-level list (recent rounds across the workspace)
    python scripts/outbound/shop_out_track.py list \\
        --tenant-id <uuid> --limit 20

    # Update one lender's status (tracking-agent manual override or
    # classifier daemon writeback)
    python scripts/outbound/shop_out_track.py update-lender \\
        --round-id <uuid> --lender-id <id> \\
        --status replied --summary "soft approval pending docs"

All commands accept --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "integrations") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "integrations"))

from integrations.send_gateway import get_supabase  # noqa: E402


VALID_LENDER_STATUSES = (
    "pending",
    "sent",
    "error",
    "replied",
    "no_response",
    "approved",
    "declined",
    "info_requested",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[shop_out_track] {msg}", file=sys.stderr)


def _load_env() -> dict[str, str]:
    try:
        from lib.secret_loader import load_env  # type: ignore
        return load_env()
    except Exception as exc:  # noqa: BLE001
        _log(f"secret_loader unavailable ({exc}) — using os.environ")
        return dict(os.environ)


def _fetch_round_by_id(db: Any, round_id: str) -> Optional[dict[str, Any]]:
    r = (
        db.table("shopping_threads")
        .select("*")
        .eq("id", round_id)
        .maybeSingle()
        .execute()
    )
    return getattr(r, "data", None)


def _fetch_round_by_lookup(
    db: Any, tenant_id: str, lead_id: str, round_number: int
) -> Optional[dict[str, Any]]:
    r = (
        db.table("shopping_threads")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("lead_id", lead_id)
        .eq("round_number", round_number)
        .maybeSingle()
        .execute()
    )
    return getattr(r, "data", None)


def cmd_show(args: argparse.Namespace) -> dict[str, Any]:
    env = _load_env()
    db = get_supabase(env)
    if args.round_id:
        row = _fetch_round_by_id(db, args.round_id)
    else:
        if not (args.tenant_id and args.lead_id and args.round_number):
            raise RuntimeError(
                "show requires either --round-id OR "
                "--tenant-id + --lead-id + --round-number"
            )
        row = _fetch_round_by_lookup(
            db, args.tenant_id, args.lead_id, int(args.round_number)
        )
    if not row:
        return {"ok": False, "error": "round_not_found"}
    return {"ok": True, "round": row}


def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    env = _load_env()
    db = get_supabase(env)
    q = (
        db.table("shopping_threads")
        .select(
            "id, tenant_id, lead_id, round_number, status, root_message_id, "
            "agent_user_id, subject, created_at, updated_at, lenders"
        )
        .eq("tenant_id", args.tenant_id)
    )
    if args.lead_id:
        q = q.eq("lead_id", args.lead_id)
    if args.status:
        q = q.eq("status", args.status)
    q = q.order("created_at", desc=True).limit(int(args.limit or 20))
    try:
        r = q.execute()
    except Exception as exc:
        raise RuntimeError(f"shopping_threads list failed: {exc}") from exc
    rows = getattr(r, "data", None) or []
    # Compact summary for human-readable mode — keep lenders array
    # untouched so JSON consumers get the full state.
    summary = [
        {
            "round_id": row.get("id"),
            "lead_id": row.get("lead_id"),
            "round_number": row.get("round_number"),
            "status": row.get("status"),
            "subject": row.get("subject"),
            "lender_count": len(row.get("lenders") or []),
            "sent_count": sum(
                1 for l in (row.get("lenders") or []) if l.get("status") == "sent"
            ),
            "replied_count": sum(
                1
                for l in (row.get("lenders") or [])
                if l.get("status") in ("replied", "approved", "declined", "info_requested")
            ),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]
    return {"ok": True, "rounds": rows, "summary": summary, "count": len(rows)}


def cmd_update_lender(args: argparse.Namespace) -> dict[str, Any]:
    env = _load_env()
    db = get_supabase(env)
    new_status = args.status
    if new_status not in VALID_LENDER_STATUSES:
        raise RuntimeError(
            f"--status must be one of {VALID_LENDER_STATUSES}, got {new_status!r}"
        )

    # Build the patch jsonb the RPC will MERGE into the matching
    # lenders[] element. jsonb_set with || does a shallow merge so
    # only the fields we set get touched; everything else (message_id,
    # interaction_id, sent_at) survives.
    patch: dict[str, Any] = {"status": new_status}
    if args.summary:
        patch["last_response_summary"] = args.summary
    if new_status in (
        "replied",
        "approved",
        "declined",
        "info_requested",
        "no_response",
    ):
        patch["last_response_at"] = _now()

    # Atomic per-lender update via the shop_out_patch_lender RPC
    # (migration 089; null-on-miss return contract in 090). The prior
    # implementation did read-modify-write on the full lenders[] jsonb
    # which raced between concurrent operators + the response-classifier
    # daemon, silently losing changes. The RPC does jsonb_set inside
    # one statement so writes to different lenders in the same round
    # don't collide. Null .data means the (round, lender) pair was
    # not found; real DB errors still raise.
    try:
        rpc_res = db.rpc(
            "shop_out_patch_lender",
            {
                "p_round_id": args.round_id,
                "p_lender_id": str(args.lender_id),
                "p_patch": patch,
            },
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"shop_out_patch_lender RPC failed: {exc}") from exc

    # PostgREST wraps a NULL composite return as a dict whose fields
    # are all None, NOT as Python None. Detect the miss by checking
    # whether the returned row carries an id. Defensive against the
    # list-of-one shape some PostgREST versions use for composite
    # returns.
    data = getattr(rpc_res, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    row_id = (data or {}).get("id") if isinstance(data, dict) else None
    if not row_id:
        return {"ok": False, "error": "round_or_lender_not_found"}

    return {
        "ok": True,
        "round_id": args.round_id,
        "lender_id": args.lender_id,
        "new_status": new_status,
    }


def _print_human(result: dict[str, Any], cmd: str) -> None:
    if not result.get("ok"):
        print(f"shop_out_track {cmd}: {result.get('error') or 'failed'}",
              file=sys.stderr)
        return
    if cmd == "show":
        rnd = result["round"]
        print(f"Round {rnd.get('round_number')} for lead {rnd.get('lead_id')}")
        print(f"  status:           {rnd.get('status')}")
        print(f"  root_message_id:  {rnd.get('root_message_id')}")
        print(f"  agent_user_id:    {rnd.get('agent_user_id')}")
        print(f"  subject:          {rnd.get('subject')}")
        print(f"  created_at:       {rnd.get('created_at')}")
        print("  lenders:")
        for plan in rnd.get("lenders") or []:
            print(
                f"    - {plan.get('lender_name') or plan.get('lender_id')}  "
                f"({plan.get('recipient_email')}) "
                f"status={plan.get('status')}"
                + (f"  err={plan.get('error')}" if plan.get('error') else "")
            )
    elif cmd == "list":
        for s in result.get("summary") or []:
            print(
                f"  round {s['round_number']:>2} | lead {s['lead_id']} "
                f"| sent {s['sent_count']}/{s['lender_count']} "
                f"replied {s['replied_count']} | {s['status']} "
                f"| {s['created_at']}"
            )
        print(f"  ({result.get('count')} rounds)")
    elif cmd == "update-lender":
        print(
            f"OK round={result['round_id']} lender={result['lender_id']} "
            f"→ {result['new_status']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Shop-out round tracking")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="Print one round's full state")
    p_show.add_argument("--round-id", default=None)
    p_show.add_argument("--tenant-id", default=None)
    p_show.add_argument("--lead-id", default=None)
    p_show.add_argument("--round-number", default=None)
    p_show.add_argument("--json", action="store_true")

    p_list = sub.add_parser("list", help="List recent rounds for a tenant / lead")
    p_list.add_argument("--tenant-id", required=True)
    p_list.add_argument("--lead-id", default=None)
    p_list.add_argument("--status", default=None,
                        help="Filter rounds by status (pending/sending/sent/error)")
    p_list.add_argument("--limit", default="20")
    p_list.add_argument("--json", action="store_true")

    p_upd = sub.add_parser("update-lender", help="Patch one lender's status in a round")
    p_upd.add_argument("--round-id", required=True)
    p_upd.add_argument("--lender-id", required=True)
    p_upd.add_argument("--status", required=True,
                       help=f"One of {VALID_LENDER_STATUSES}")
    p_upd.add_argument("--summary", default=None,
                       help="Optional free-text summary of the response")
    p_upd.add_argument("--json", action="store_true")

    args = parser.parse_args()

    handlers = {
        "show": cmd_show,
        "list": cmd_list,
        "update-lender": cmd_update_lender,
    }
    try:
        result = handlers[args.cmd](args)
    except Exception as exc:
        err = {"ok": False, "error": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(err))
        else:
            print(f"shop_out_track {args.cmd} failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, default=str))
    else:
        _print_human(result, args.cmd)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
