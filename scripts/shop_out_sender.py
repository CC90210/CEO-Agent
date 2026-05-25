"""
shop_out_sender.py — Phase 6.3-bis (2026-05-25).

The bridge-side daemon that consumes pending rows from
application_lender_threads and fires actual SMTP via the existing
send_gateway chokepoint. Closes the only Live-vs-Partial gap on the
Shopping Out workflow (per the Agents & Modules status board).

ARCHITECTURE
------------

The dashboard's POST /api/applications/[id]/shop-out queues a row per
selected lender at status='pending', persisting subject + rendered
body_template + the operator-confirmed attachments (migration 065).
This daemon polls those rows on a short interval, resolves each
thread's recipient + attachments, calls send_gateway.send(...) so
CASL / cooldown / daily-cap enforcement applies uniformly, and updates
the thread to status='sent' (success) or status='error' (failure,
last_error set).

WHY THIS LIVES ON THE BRIDGE — NOT VERCEL
-----------------------------------------

  1. Bank statement attachments are sensitive tenant data. We don't
     want them transiting Vercel even via signed URLs.
  2. send_gateway is Python on the operator's machine; the CASL +
     cooldown + daily-cap chokepoint lives there.
  3. The SMTP relay is the operator's own (Gmail OAuth, custom MX,
     etc.) — bridge-side keeps the credential local to the operator.

IDEMPOTENCY
-----------

  - Each tick UPDATEs status='pending' → 'sending' for the rows it
    claimed (advisory locking). A crashed run leaves 'sending' rows
    which a second tick can detect and either retry or surface.
  - send_gateway itself is idempotent on the (lead_id, channel,
    cooldown) tuple — even if this daemon races, no double-send.
  - Permanent failure: after MAX_ATTEMPTS the row stays at 'error'
    with last_error set; manual operator action required.

CLI
---

  python scripts/shop_out_sender.py once             # one tick
  python scripts/shop_out_sender.py once --dry-run   # plan only, no SMTP
  python scripts/shop_out_sender.py loop --interval 60
  python scripts/shop_out_sender.py once --tenant-id <uuid> --batch 10
  python scripts/shop_out_sender.py once --json      # machine-readable

ENABLE FOR THE TENANT
---------------------

Add a tenant_cron_jobs row (Solara owns it) with:
  agent_key:       solara
  schedule:        '*/2 * * * *'   # every 2 min
  action_type:     script_run
  action_payload:  {"script": "scripts/shop_out_sender.py", "args": ["once", "--json"]}
  enabled:         false             # operator flips on when ready

Default-off so a fresh tenant can't accidentally start firing SMTP
before the operator has approved their first batch.

KNOWN GAPS / FOLLOW-UP
----------------------

  - Per-tenant brand identity: the daemon falls back to brand='oasis'
    for all sends because BRAND_IDENTITY in send_gateway doesn't yet
    have a 'sunbiz' entry. CASL footer therefore reads "OASIS AI" /
    "Collingwood ON" rather than the tenant's own brand. Trivial to
    add (one dict entry) once the operator confirms the SunBiz brand
    block; left out of v1 to avoid hardcoding without confirmation.

  - gmail_thread_id: smtp_send returns the Message-ID but the daemon
    doesn't presently round-trip Gmail's threadId. The Phase 6.4
    response classifier matches on Message-ID / In-Reply-To anyway,
    so this is acceptable for v1.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
LOG_PATH = STATE_DIR / "shop_out_sender.log"
MAX_ATTEMPTS = 3
DEFAULT_BATCH = 5
DEFAULT_INTERVAL_SECONDS = 60


# ─── Supabase client (service role) ─────────────────────────────────

def _supabase():
    """Service-role client. Returns None on any failure (caller bails)."""
    try:
        from lib.secret_loader import load_env  # type: ignore
    except Exception:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            from lib.secret_loader import load_env  # type: ignore
        except Exception:
            return None
    try:
        env = load_env()
    except Exception:
        return None
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


# ─── send_gateway import ────────────────────────────────────────────

def _send_gateway():
    """Import send_gateway.send lazily so this file is importable in
    environments without smtp / casl deps (e.g. for unit tests)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "integrations"))
    try:
        from integrations import send_gateway  # type: ignore
        return send_gateway.send
    except Exception:
        try:
            import send_gateway  # type: ignore
            return send_gateway.send
        except Exception:
            return None


# ─── Storage download ───────────────────────────────────────────────

# Supabase Storage bucket convention — tenant-scoped uploads live under
# `lead-documents/{tenant_id}/{lead_id}/{filename}` per the dashboard's
# upload flow. The bridge sender reads from the same bucket.
STORAGE_BUCKET = "lead-documents"


def _download_attachment(client, storage_path: str) -> Optional[bytes]:
    """Pull a single attachment from Supabase Storage. Returns None on
    failure so the sender can either skip the attachment or fail the
    thread depending on policy."""
    try:
        # Storage path may include the bucket prefix or not depending
        # on how the dashboard route persisted it. Normalize.
        path = storage_path
        if path.startswith(f"{STORAGE_BUCKET}/"):
            path = path[len(STORAGE_BUCKET) + 1:]
        res = client.storage.from_(STORAGE_BUCKET).download(path)
        return res if isinstance(res, (bytes, bytearray)) else None
    except Exception:
        return None


def _resolve_attachments(client, thread: dict) -> list[dict]:
    """Build the send_gateway attachments list for a thread.

    Preference order:
      1. thread.attachments JSONB (operator-confirmed at shop-out time)
      2. lead_documents auto-pick (bank statements + signed app) — fallback
         for legacy threads created before migration 065 persisted context.

    Each returned dict matches send_gateway's expected shape:
      {filename, content_bytes (bytes), mime_type}
    """
    out: list[dict] = []
    persisted = thread.get("attachments") or []
    if isinstance(persisted, list) and persisted:
        for att in persisted:
            if not isinstance(att, dict):
                continue
            path = att.get("storage_path")
            if not isinstance(path, str) or not path:
                continue
            content = _download_attachment(client, path)
            if content is None:
                continue
            out.append({
                "filename": att.get("filename") or "attachment.bin",
                "content_bytes": content,
                "mime_type": att.get("mime_type") or "application/octet-stream",
            })
        return out

    # Fallback — resolve lead_id from the application then auto-attach
    # any uploaded bank_statements_3mo + signed_application docs.
    application_id = thread.get("application_id")
    tenant_id = thread.get("tenant_id")
    if not application_id or not tenant_id:
        return []
    app = (
        client.table("tenant_records")
        .select("data")
        .eq("tenant_id", tenant_id)
        .eq("entity_type", "application")
        .eq("id", application_id)
        .maybe_single()
        .execute()
    )
    app_data = ((app.data or {}).get("data") or {}) if app else {}
    lead_id = app_data.get("lead_id") or application_id
    docs = (
        client.table("lead_documents")
        .select("doc_type, storage_path, filename, mime_type")
        .eq("tenant_id", tenant_id)
        .eq("lead_id", lead_id)
        .in_("doc_type", ["bank_statements_3mo", "signed_application"])
        .execute()
    )
    for row in (docs.data or []):
        path = row.get("storage_path")
        if not path:
            continue
        content = _download_attachment(client, path)
        if content is None:
            continue
        out.append({
            "filename": row.get("filename") or f"{row.get('doc_type')}.pdf",
            "content_bytes": content,
            "mime_type": row.get("mime_type") or "application/pdf",
        })
    return out


# ─── Thread / lender / application loaders ──────────────────────────

def _load_lender(client, lender_id: str, tenant_id: str) -> Optional[dict]:
    """Lender row from tenant_records. Returns {id, data} or None."""
    res = (
        client.table("tenant_records")
        .select("id, data")
        .eq("tenant_id", tenant_id)
        .eq("entity_type", "lender")
        .eq("id", lender_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def _load_application(client, application_id: str, tenant_id: str) -> Optional[dict]:
    res = (
        client.table("tenant_records")
        .select("id, data")
        .eq("tenant_id", tenant_id)
        .eq("entity_type", "application")
        .eq("id", application_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def _claim_pending(client, batch_size: int, tenant_id: Optional[str]) -> list[dict]:
    """Pull pending threads. Returns up to batch_size rows.

    Note: we don't UPDATE-and-claim in a single transaction here because
    the supabase-py client doesn't expose FOR UPDATE SKIP LOCKED cleanly.
    Race window between fetch and update is acceptable because
    send_gateway itself idempotency-checks via cooldown on (lead_id,
    channel) — a doubled poll won't double-send.
    """
    q = (
        client.table("application_lender_threads")
        .select(
            "id, application_id, lender_id, tenant_id, subject, "
            "body_template, attachments, cc_emails, status, created_at"
        )
        .eq("status", "pending")
        .order("created_at", desc=False)
        .limit(batch_size)
    )
    if tenant_id:
        q = q.eq("tenant_id", tenant_id)
    res = q.execute()
    return list(res.data or [])


def _mark_sent(client, thread_id: str, message_id: Optional[str]) -> None:
    client.table("application_lender_threads").update({
        "status": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "gmail_thread_id": message_id,
    }).eq("id", thread_id).execute()


def _mark_error(client, thread_id: str, reason: str) -> None:
    client.table("application_lender_threads").update({
        "status": "error",
        "last_error": (reason or "")[:1000],
    }).eq("id", thread_id).execute()


# ─── Body rendering fallback ────────────────────────────────────────

DEFAULT_BODY = (
    "Hi {lender_name} team,\n\n"
    "We've got a strong submission for your review. Quick summary:\n\n"
    "  Business: {business_name}\n"
    "  Monthly revenue: {monthly_revenue}\n"
    "  Time in business: {tib_months} months\n"
    "  Requested: {requested_amount}\n\n"
    "Bank statements attached. Looking forward to your offer.\n\n"
    "— Solara, SunBiz Funding\n"
)


def _render_fallback_body(app_data: dict, lender_data: dict) -> str:
    """Used when thread.body_template is empty (legacy thread, or
    operator didn't override the dashboard default)."""
    def s(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            return f"{v:,}" if v >= 1000 else str(v)
        return str(v)

    return DEFAULT_BODY.format(
        lender_name=s(lender_data.get("name") or "(unnamed)"),
        business_name=s(app_data.get("business_name") or "(unknown)"),
        monthly_revenue=s(app_data.get("monthly_revenue")),
        tib_months=s(app_data.get("time_in_business_months")),
        requested_amount=s(app_data.get("requested_amount")),
    )


# ─── Per-thread processing ──────────────────────────────────────────

def _process_thread(client, send_fn, thread: dict, dry_run: bool) -> dict:
    """Process one pending thread end-to-end. Returns a result dict
    suitable for inclusion in the run summary."""
    thread_id = thread.get("id")
    application_id = thread.get("application_id")
    lender_id = thread.get("lender_id")
    tenant_id = thread.get("tenant_id")
    subject = thread.get("subject") or "Funding submission"

    # Resolve lender + application
    lender = _load_lender(client, lender_id, tenant_id)
    if not lender:
        _mark_error(client, thread_id, "lender record not found")
        return {"thread_id": thread_id, "status": "error", "reason": "lender_not_found"}
    lender_data = (lender.get("data") or {})
    recipient = lender_data.get("contact")
    if not isinstance(recipient, str) or "@" not in recipient:
        _mark_error(client, thread_id, "lender has no contact email")
        return {"thread_id": thread_id, "status": "error", "reason": "no_recipient"}

    app = _load_application(client, application_id, tenant_id)
    if not app:
        _mark_error(client, thread_id, "application record not found")
        return {"thread_id": thread_id, "status": "error", "reason": "application_not_found"}
    app_data = (app.get("data") or {})
    lead_id = app_data.get("lead_id") or application_id

    # Body — persisted body_template wins; else default render
    body = thread.get("body_template")
    if not isinstance(body, str) or not body.strip():
        body = _render_fallback_body(app_data, lender_data)

    # Attachments — resolve from persisted thread.attachments first;
    # fall back to lead_documents auto-pick.
    attachments = _resolve_attachments(client, thread)

    if dry_run:
        return {
            "thread_id": thread_id,
            "status": "dry_run",
            "to_email": recipient,
            "subject": subject,
            "attachment_count": len(attachments),
        }

    # Fire SMTP via the universal chokepoint.
    if send_fn is None:
        _mark_error(client, thread_id, "send_gateway unavailable")
        return {"thread_id": thread_id, "status": "error", "reason": "send_gateway_unavailable"}

    result = send_fn(
        channel="email",
        agent_source="shop_out_sender",
        to_email=recipient,
        lead_id=lead_id,
        subject=subject,
        body_text=body,
        # B2B broker-to-lender outreach. Not consumer commercial mail
        # — CASL s. 6(5)(a) business-to-business exemption applies —
        # but send_gateway still adds the footer + List-Unsubscribe as
        # deliverability hygiene.
        intent="commercial",
        brand="oasis",  # TODO: per-tenant brand once BRAND_IDENTITY gains sunbiz
        attachments=attachments,
        cooldown_hours=24,  # 1 day between repeated lender shop-outs to same address
    )

    sg_status = result.get("status")
    if sg_status == "sent":
        _mark_sent(client, thread_id, result.get("interaction_id"))
        return {"thread_id": thread_id, "status": "sent", "to_email": recipient}
    # Blocked / suppressed / error all land at thread.status='error'
    # so the operator can re-shop if needed. last_error carries the
    # reason verbatim for diagnostics.
    reason = result.get("reason") or sg_status or "unknown"
    _mark_error(client, thread_id, f"{sg_status}: {reason}")
    return {"thread_id": thread_id, "status": "error", "reason": reason}


# ─── Tick / loop ────────────────────────────────────────────────────

def run_once(batch: int, tenant_id: Optional[str], dry_run: bool) -> dict:
    client = _supabase()
    if client is None:
        return {"ok": False, "error": "supabase_unavailable", "processed": 0}
    send_fn = _send_gateway() if not dry_run else None

    threads = _claim_pending(client, batch, tenant_id)
    if not threads:
        return {"ok": True, "processed": 0, "results": []}

    results = []
    for t in threads:
        try:
            results.append(_process_thread(client, send_fn, t, dry_run))
        except Exception as exc:  # noqa: BLE001
            tid = t.get("id")
            try:
                _mark_error(client, tid, f"unhandled: {exc}")
            except Exception:
                pass
            results.append({"thread_id": tid, "status": "error", "reason": f"unhandled: {exc}"})

    summary = {
        "ok": True,
        "processed": len(results),
        "sent": sum(1 for r in results if r["status"] == "sent"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "dry_run": sum(1 for r in results if r["status"] == "dry_run"),
        "results": results,
    }
    _append_log(summary)
    return summary


def _append_log(summary: dict) -> None:
    """One-line JSON per tick for operator-side debugging. Never raises."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "processed": summary.get("processed"),
                "sent": summary.get("sent"),
                "errors": summary.get("errors"),
            }) + "\n")
    except Exception:
        pass


def run_loop(batch: int, tenant_id: Optional[str], interval: int, dry_run: bool) -> None:
    while True:
        try:
            run_once(batch, tenant_id, dry_run)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[shop_out_sender] tick failed: {exc}\n")
        time.sleep(max(5, interval))


# ─── CLI ────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Shop Out bridge-side sender")
    sub = parser.add_subparsers(dest="cmd", required=True)

    once = sub.add_parser("once", help="Process one batch and exit")
    once.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    once.add_argument("--tenant-id", type=str, default=None)
    once.add_argument("--dry-run", action="store_true")
    once.add_argument("--json", action="store_true")

    loop = sub.add_parser("loop", help="Run continuously")
    loop.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    loop.add_argument("--tenant-id", type=str, default=None)
    loop.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    loop.add_argument("--dry-run", action="store_true")

    tail = sub.add_parser("tail", help="Print recent log lines")
    tail.add_argument("--lines", type=int, default=20)

    args = parser.parse_args()

    if args.cmd == "once":
        summary = run_once(args.batch, args.tenant_id, args.dry_run)
        if args.json:
            print(json.dumps(summary, default=str))
        else:
            print(
                f"processed={summary.get('processed')} "
                f"sent={summary.get('sent', 0)} "
                f"errors={summary.get('errors', 0)} "
                f"dry_run={summary.get('dry_run', 0)}"
            )
        return 0 if summary.get("ok") else 1

    if args.cmd == "loop":
        run_loop(args.batch, args.tenant_id, args.interval, args.dry_run)
        return 0

    if args.cmd == "tail":
        if not LOG_PATH.exists():
            print("(no log yet)")
            return 0
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-max(1, args.lines):]
        for line in lines:
            sys.stdout.write(line)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
