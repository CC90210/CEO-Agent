"""
shop_out — fan a loan file out to N lenders as one logical email round.

Two-agent workflow: the SENDER agent fires this tool with a lead_id +
lender_ids; the TRACKER agent reads the round back via shop_out_track.

THREADING STRATEGY
------------------

Each round is anchored by a single References Message-ID:
    <round-{uuid}@oasis>

Per-lender outbound:
    Message-ID:  <round-{round_uuid}-lender-{lender_id}@oasis>
    References:  <round-{round_uuid}@oasis>
    Subject:     <same subject across all N lenders>
    To:          <one lender's contact email>
    Cc:          <the initiating agent's email>

Result:
  * Each lender receives their own email (privacy — lenders never see
    each other on To/Cc).
  * Lender replies preserve the References anchor, so the agent's CC'd
    inbox groups all N outbound + all N inbound replies as ONE Gmail
    conversation.
  * Re-shopping to NEW lenders later creates a NEW round (new anchor)
    so the second outreach lands on a separate visible thread.

The send is fan-out per-lender (one send_gateway.send() per recipient)
so the CASL footer, cooldown ledger, per-user OAuth identity, and
attachment plumbing all run through the canonical chokepoint without
modification.

CLI
---

    python scripts/outbound/shop_out.py send \\
        --tenant-id <uuid> \\
        --lead-id <id> \\
        --agent-user-id <uuid> \\
        --lenders <lender_id_1>,<lender_id_2>,... \\
        --subject "..." \\
        --body-file path/to/body.txt \\
        [--body-html-file path/to/body.html] \\
        [--attachments file1.pdf,file2.pdf] \\
        [--round-number N]      # optional override; defaults to auto-increment
        [--dry-run]              # plan only, no SMTP
        [--json]                 # machine-readable status output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "integrations") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "integrations"))

from integrations.send_gateway import (  # noqa: E402
    get_supabase,
    send as gateway_send,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[shop_out] {msg}", file=sys.stderr)


def _load_env() -> dict[str, str]:
    try:
        from lib.secret_loader import load_env  # type: ignore
        return load_env()
    except Exception as exc:  # noqa: BLE001
        _log(f"secret_loader unavailable ({exc}) — using os.environ")
        return dict(os.environ)


def _resolve_lender_contact(db: Any, tenant_id: str, lender_id: str) -> dict[str, Any]:
    """Read a lender record from tenant_records and pull its primary
    contact email + display name. Returns {"name", "email"}.

    Raises if no contact email exists on the lender — the round can't
    proceed without somewhere to send.
    """
    r = (
        db.table("tenant_records")
        .select("data")
        .eq("tenant_id", tenant_id)
        .eq("entity_type", "lender")
        .eq("id", lender_id)
        .limit(1)
        .execute()
    )
    rows = getattr(r, "data", None) or []
    if not rows:
        raise RuntimeError(f"lender {lender_id} not found in tenant {tenant_id}")
    data = rows[0].get("data") or {}
    email = (
        data.get("submission_email")
        or data.get("primary_email")
        or data.get("email")
        or ""
    ).strip()
    name = (data.get("name") or data.get("lender_name") or "").strip() or lender_id
    if not email:
        raise RuntimeError(f"lender {lender_id} has no submission/primary email")
    return {"name": name, "email": email}


def _resolve_agent_email(db: Any, agent_user_id: str) -> Optional[str]:
    """Read the initiating agent's email from user_profiles for the CC.

    Returns None on miss — caller treats that as "no CC, just send" and
    logs a warning. Don't fail the round over a missing CC.
    """
    try:
        r = (
            db.table("user_profiles")
            .select("email")
            .eq("auth_user_id", agent_user_id)
            .maybeSingle()
            .execute()
        )
        data = getattr(r, "data", None) or {}
        return (data.get("email") or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        _log(f"agent email lookup failed for {agent_user_id}: {exc}")
        return None


def _next_round_number(db: Any, tenant_id: str, lead_id: str) -> int:
    """Compute the next round_number for this (tenant, lead) by reading
    the current max. Race-safe enough for the operator-paced workflow
    (a human kicks off rounds; concurrent rounds for the same lead would
    be a UX bug, not a load problem). The UNIQUE constraint on
    (tenant_id, lead_id, round_number) is the hard backstop if two
    rounds DO race — the second insert errors out.
    """
    try:
        r = (
            db.table("shopping_threads")
            .select("round_number")
            .eq("tenant_id", tenant_id)
            .eq("lead_id", lead_id)
            .order("round_number", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"round_number lookup failed: {exc} — defaulting to 1")
        return 1
    rows = getattr(r, "data", None) or []
    if not rows:
        return 1
    return int(rows[0].get("round_number") or 0) + 1


def _read_body_file(path_str: Optional[str]) -> Optional[str]:
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_file():
        raise RuntimeError(f"body file not found: {path_str}")
    return p.read_text(encoding="utf-8")


def _read_attachment(path_str: str) -> dict[str, Any]:
    p = Path(path_str.strip())
    if not p.is_file():
        raise RuntimeError(f"attachment not found: {path_str}")
    ext = p.suffix.lower()
    ctype = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".csv": "text/csv",
        ".txt": "text/plain",
    }.get(ext, "application/octet-stream")
    return {
        "filename": p.name,
        "content": p.read_bytes(),
        "content_type": ctype,
    }


def _synthesize_message_ids(round_uuid: str, lender_id: str) -> tuple[str, str]:
    """Return (per_lender_message_id, references_anchor)."""
    anchor = f"<round-{round_uuid}@oasis>"
    # lender_id may contain non-rfc822 chars in dev; squash to safe slug
    safe_lender = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in str(lender_id)
    )
    per_lender = f"<round-{round_uuid}-lender-{safe_lender}@oasis>"
    return per_lender, anchor


def cmd_send(args: argparse.Namespace) -> dict[str, Any]:
    env = _load_env()
    # Ensure secret_loader env reaches send_gateway's downstream lookups.
    for k, v in env.items():
        if k not in os.environ:
            os.environ[k] = v

    db = get_supabase(env)

    lender_ids = [s.strip() for s in (args.lenders or "").split(",") if s.strip()]
    if not lender_ids:
        raise RuntimeError("--lenders is empty")

    body_text = _read_body_file(args.body_file)
    if not body_text:
        raise RuntimeError("--body-file required (text body for the round)")
    body_html = _read_body_file(args.body_html_file)

    attachment_specs: list[dict[str, Any]] = []
    if args.attachments:
        for p in args.attachments.split(","):
            attachment_specs.append(_read_attachment(p))

    round_uuid = uuid.uuid4().hex
    _root_msg_id = f"<round-{round_uuid}@oasis>"

    round_number = (
        int(args.round_number)
        if args.round_number
        else _next_round_number(db, args.tenant_id, args.lead_id)
    )

    agent_cc = _resolve_agent_email(db, args.agent_user_id)
    if not agent_cc:
        _log(
            f"warning: agent {args.agent_user_id} has no user_profiles.email "
            f"— round will send without CC"
        )

    # Pre-resolve every lender contact BEFORE inserting the round row.
    # If a lender record is broken we want to fail fast, not leave a
    # half-sent round in the DB.
    plans: list[dict[str, Any]] = []
    for lid in lender_ids:
        contact = _resolve_lender_contact(db, args.tenant_id, lid)
        per_msg_id, references = _synthesize_message_ids(round_uuid, lid)
        plans.append({
            "lender_id": lid,
            "lender_name": contact["name"],
            "recipient_email": contact["email"],
            "message_id": per_msg_id,
            "references": references,
            "interaction_id": None,
            "status": "pending",
            "error": None,
            "sent_at": None,
            "last_response_at": None,
        })

    if args.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "round_id": None,
            "round_number": round_number,
            "root_message_id": _root_msg_id,
            "lenders": plans,
        }

    # Insert the round row at status='pending' so observers see it
    # before any send fires. UNIQUE(tenant, lead, round_number) is the
    # race backstop if two operators kick off concurrent rounds.
    try:
        insert_res = (
            db.table("shopping_threads")
            .insert({
                "tenant_id": args.tenant_id,
                "lead_id": args.lead_id,
                "round_number": round_number,
                "root_message_id": _root_msg_id,
                "agent_user_id": args.agent_user_id,
                "lenders": [
                    {k: v for k, v in p.items() if k != "references"}
                    for p in plans
                ],
                "status": "pending",
                "subject": args.subject,
            })
            .select("id")
            .single()
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"shopping_threads insert failed: {exc}") from exc
    round_id = (getattr(insert_res, "data", None) or {}).get("id")
    if not round_id:
        raise RuntimeError("shopping_threads insert returned no id")

    # Flip to 'sending' so the tracker reflects in-flight state.
    db.table("shopping_threads").update({"status": "sending"}).eq("id", round_id).execute()

    # Fan out per-lender through send_gateway. Each send carries the
    # shared References anchor so Gmail groups them as one conversation
    # in the agent's CC'd inbox.
    success_count = 0
    for plan in plans:
        result = gateway_send(
            channel="email",
            agent_source="shop_out",
            to_email=plan["recipient_email"],
            cc_email=agent_cc,
            lead_id=args.lead_id,
            subject=args.subject,
            body_text=body_text,
            body_html=body_html,
            brand="sunbiz",
            intent="transactional",
            metadata={
                "shop_out_round_id": round_id,
                "shop_out_round_number": round_number,
                "lender_id": plan["lender_id"],
                "lender_name": plan["lender_name"],
            },
            attachments=attachment_specs or None,
            db=db,
            acted_by_user_id=args.agent_user_id,
            tenant_id=args.tenant_id,
            message_id=plan["message_id"],
            references=plan["references"],
        )
        plan["interaction_id"] = result.get("interaction_id")
        if result.get("status") == "sent":
            plan["status"] = "sent"
            plan["sent_at"] = _now()
            success_count += 1
        else:
            plan["status"] = "error"
            plan["error"] = result.get("reason") or "unknown"

    round_status = (
        "sent" if success_count == len(plans)
        else ("error" if success_count == 0 else "sent")
    )

    # Persist the per-lender outcomes back onto the round row. Strip
    # the transient References field — it's the same for every lender
    # and lives on the round row as root_message_id already.
    final_lenders = [
        {k: v for k, v in p.items() if k != "references"}
        for p in plans
    ]
    db.table("shopping_threads").update({
        "lenders": final_lenders,
        "status": round_status,
    }).eq("id", round_id).execute()

    return {
        "ok": success_count > 0,
        "round_id": round_id,
        "round_number": round_number,
        "root_message_id": _root_msg_id,
        "status": round_status,
        "sent_count": success_count,
        "lender_count": len(plans),
        "lenders": final_lenders,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-lender shop-out (threaded send)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_send = sub.add_parser("send", help="Send a shop-out round")
    p_send.add_argument("--tenant-id", required=True)
    p_send.add_argument("--lead-id", required=True)
    p_send.add_argument("--agent-user-id", required=True,
                        help="auth.users.id of the agent firing the round (used for CC + audit)")
    p_send.add_argument("--lenders", required=True,
                        help="Comma-separated lender tenant_records ids")
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body-file", required=True,
                        help="Path to text body for every lender (same body across the round)")
    p_send.add_argument("--body-html-file", default=None,
                        help="Optional HTML body file")
    p_send.add_argument("--attachments", default=None,
                        help="Comma-separated file paths to attach (PDF / image / CSV)")
    p_send.add_argument("--round-number", default=None,
                        help="Override the auto-incremented round number")
    p_send.add_argument("--dry-run", action="store_true",
                        help="Plan only, no SMTP send + no DB insert")
    p_send.add_argument("--json", action="store_true",
                        help="Print machine-readable JSON result on stdout")

    args = parser.parse_args()

    try:
        result = cmd_send(args)
    except Exception as exc:
        err = {"ok": False, "error": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(err))
        else:
            print(f"shop_out send failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, default=str))
    else:
        print(
            f"shop_out round {result.get('round_number')} → "
            f"{result.get('sent_count', 0)}/{result.get('lender_count', 0)} sent. "
            f"round_id={result.get('round_id')} "
            f"status={result.get('status')}"
        )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
