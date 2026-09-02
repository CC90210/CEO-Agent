#!/usr/bin/env python3
"""email_draft_action.py — act on a held email draft from a Telegram tap.

WHY THIS EXISTS
email_brain drafts a reply, persists it to `lead_interactions` as
`type='email_draft_pending'` with `metadata.awaiting_approval=true`, and pushes
the proposed text to CC on Telegram. Until now that was the end of the road:
the message said "Draft ready to send" and CC had to go somewhere else and
retype it. The alert proposed an action and offered no way to take it, so the
operator became the transport.

This module is the action. The Telegram button carries only the row id; every
decision — what to send, to whom, whether it is still sendable — is made here
against the stored row, so a stale button cannot send the wrong thing.

WHY THE STATE LIVES IN THE DATABASE
telegram_agent.js already has an approval mechanism, but it is
`PENDING_CONFIRMATIONS[chatId]` — one in-memory slot per chat, lost on restart.
Email drafts arrive in bursts and the bot restarts on deploy, so that shape
would drop approvals silently and could only ever track one draft at a time.
The row is already durable; key the button to it.

IDEMPOTENCY IS THE WHOLE SAFETY PROPERTY
There is no unsend. A double-tap, a Telegram retry, or two operators tapping
the same button must send exactly once, so approve() claims the row with a
compare-and-set on `awaiting_approval` BEFORE it calls the gateway, and refuses
outright if the row is already resolved. A claim that cannot be made is not an
error to retry — it means someone already decided.

Usage:
  python scripts/email_draft_action.py show    --id <interaction_id> [--json]
  python scripts/email_draft_action.py approve --id <interaction_id> [--json]
  python scripts/email_draft_action.py reject  --id <interaction_id> [--reason "..."] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts" / "integrations"))

CAPABILITY_META = {
    "category": "communication.email",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": ["approve email draft", "reject email draft", "send held draft"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": True, "subcommands": {"approve": {"confirm": True}}},
}

DRAFT_TYPE = "email_draft_pending"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    from inbound_classifier import get_supabase  # noqa: PLC0415

    return get_supabase()


def _load(draft_id: str, db=None) -> Optional[dict[str, Any]]:
    """Read the draft row. Returns None when the id does not exist."""
    _dbc = db or _db()
    res = (
        _dbc.table("lead_interactions")
        .select("*")
        .eq("id", draft_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    """`metadata` is TEXT in Turso and dict under the Supabase shim. Normalize.

    A JSON string that fails to parse is NOT coerced to {} — an unreadable
    decision record must not read as "no decision recorded", which is exactly
    how a resolved draft would look sendable again.
    """
    meta = row.get("metadata")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str) and meta.strip():
        return json.loads(meta)
    return {}


def _resolution(meta: dict[str, Any]) -> Optional[str]:
    """The decision already recorded on this row, if any."""
    if meta.get("approved_at"):
        return "approved"
    if meta.get("rejected_at"):
        return "rejected"
    if meta.get("awaiting_approval") is False:
        return "resolved"
    return None


def _claim(draft_id: str, meta: dict[str, Any], patch: dict[str, Any], db=None) -> bool:
    """Compare-and-set the row out of the awaiting state.

    The `.eq("metadata->>awaiting_approval", "true")` predicate is what makes a
    double-tap safe: the second writer matches zero rows and gets False back,
    so only one caller ever proceeds to the gateway.
    """
    _dbc = db or _db()
    merged = {**meta, **patch, "awaiting_approval": False}
    res = (
        _dbc.table("lead_interactions")
        .update({"metadata": merged})
        .eq("id", draft_id)
        .eq("metadata->>awaiting_approval", "true")
        .execute()
    )
    return bool(res.data)


def cmd_show(draft_id: str, db=None) -> dict[str, Any]:
    row = _load(draft_id, db=db)
    if not row:
        return {"ok": False, "error": "draft_not_found", "id": draft_id}
    meta = _metadata(row)
    return {
        "ok": True,
        "id": draft_id,
        "to": meta.get("from_identity"),
        "subject": row.get("subject"),
        "body": row.get("content"),
        "category": meta.get("category"),
        "resolution": _resolution(meta) or "awaiting_approval",
    }


def cmd_approve(draft_id: str, db=None) -> dict[str, Any]:
    """Send the stored draft. Claims the row first; never sends twice."""
    row = _load(draft_id, db=db)
    if not row:
        return {"ok": False, "error": "draft_not_found", "id": draft_id}
    if row.get("type") != DRAFT_TYPE:
        return {"ok": False, "error": "not_a_draft_row", "id": draft_id}

    meta = _metadata(row)
    already = _resolution(meta)
    if already:
        return {"ok": False, "error": f"already_{already}", "id": draft_id}

    to_email = (meta.get("from_identity") or "").strip()
    if not to_email:
        return {"ok": False, "error": "draft_has_no_recipient", "id": draft_id}
    body = row.get("content") or ""
    if not body.strip():
        return {"ok": False, "error": "draft_body_empty", "id": draft_id}

    # Claim BEFORE sending. If the send then fails we have recorded an approval
    # for a mail that did not go out — recoverable, and visible in the row. The
    # reverse ordering risks sending twice, which is not recoverable.
    if not _claim(draft_id, meta, {"approved_at": _now()}, db=db):
        return {"ok": False, "error": "already_resolved_by_another_tap", "id": draft_id}

    from send_gateway import send  # noqa: PLC0415

    result = send(
        channel="email",
        # CC tapped approve, so this is operator-initiated by definition. That
        # is the accurate source AND the one that will not be refused by a
        # nurture cooldown for a reply a human explicitly authorized.
        agent_source="manual_cc",
        to_email=to_email,
        subject=row.get("subject") or "Re:",
        body_text=body,
        tenant_id=row.get("tenant_id"),
        intent="transactional",
        # Thread the reply onto the message that prompted it, so it lands in the
        # existing conversation instead of opening a new one.
        in_reply_to=meta.get("rfc_message_id"),
        references=meta.get("rfc_message_id"),
    )

    status = result.get("status")
    if status != "sent":
        # Record the failure ON the row so the next reader sees why an approved
        # draft never arrived, instead of finding an approval with no mail.
        try:
            _dbc = db or _db()
            _dbc.table("lead_interactions").update(
                {"metadata": {**meta, "awaiting_approval": False,
                              "approved_at": _now(),
                              "send_status": status,
                              "send_error": result.get("reason")}}
            ).eq("id", draft_id).execute()
        except Exception as exc:  # noqa: BLE001
            print(f"[email_draft_action] failure-record warning: {exc}", file=sys.stderr)
        return {"ok": False, "error": f"send_{status}", "reason": result.get("reason"),
                "id": draft_id, "to": to_email}

    return {"ok": True, "action": "approved", "id": draft_id, "to": to_email,
            "subject": row.get("subject"), "interaction_id": result.get("interaction_id")}


def cmd_reject(draft_id: str, reason: str = "", db=None) -> dict[str, Any]:
    row = _load(draft_id, db=db)
    if not row:
        return {"ok": False, "error": "draft_not_found", "id": draft_id}
    meta = _metadata(row)
    already = _resolution(meta)
    if already:
        return {"ok": False, "error": f"already_{already}", "id": draft_id}
    if not _claim(draft_id, meta,
                  {"rejected_at": _now(), "rejected_reason": reason or None}, db=db):
        return {"ok": False, "error": "already_resolved_by_another_tap", "id": draft_id}
    return {"ok": True, "action": "rejected", "id": draft_id}


def main() -> int:
    ap = argparse.ArgumentParser(description="Approve or reject a held email draft.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("show", "approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("--id", required=True, help="lead_interactions.id of the draft")
        p.add_argument("--json", action="store_true")
        if name == "reject":
            p.add_argument("--reason", default="")
    args = ap.parse_args()

    if args.command == "show":
        out = cmd_show(args.id)
    elif args.command == "approve":
        out = cmd_approve(args.id)
    else:
        out = cmd_reject(args.id, reason=args.reason)

    if args.json:
        print(json.dumps(out))
    else:
        if out.get("ok"):
            print(f"{out.get('action', 'ok')}: {out.get('id')} -> {out.get('to', '')}".strip())
        else:
            print(f"ERROR: {out.get('error')} ({out.get('reason') or ''})".strip())
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
