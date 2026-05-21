"""Dashboard outbound-email consumer daemon.

Polls Supabase `lead_interactions` for rows the operator queued from
the OASIS Command Center drawer's Email composer:

    type='email_queued'
    channel='email'
    direction='outbound'
    agent_source='dashboard_drawer'
    metadata.status='queued'

For each row:
    1. Resolve sender credentials (GMAIL_USER + GMAIL_APP_PASSWORD).
       Per-tenant credentials in tenant_integration_credentials are
       deferred until the multi-tenant Gmail-account split lands;
       env-var fallback covers the SunBiz pilot.
    2. Send via smtplib.SMTP_SSL('smtp.gmail.com', 465) using the same
       transport scripts/integrations/send_gateway.py uses.
    3. Update the row's metadata.status to 'sent' (+ sent_at timestamp)
       or 'failed' (+ metadata.send_error) so the drawer's timeline
       reflects the outcome.

Failure modes (all non-fatal — daemon keeps running):
    - SMTP auth → mark row 'failed', back off 60s before next poll
    - Recipient refused → mark row 'failed' permanently
    - Transient network → leave 'queued', retry next tick

PM2 entry:
    pm2 start scripts/dashboard_email_consumer.py \\
        --name dashboard-email-consumer \\
        --interpreter python -- loop --interval 10

CLI:
    python scripts/dashboard_email_consumer.py once   # single tick, exit
    python scripts/dashboard_email_consumer.py loop   # poll forever
    python scripts/dashboard_email_consumer.py drain  # process backlog, exit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# V5.6 chokepoint: all SMTP sends go through lib.smtp_send (single source of truth)
from lib.smtp_send import smtp_send  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _load_env() -> dict[str, str]:
    """Load .env.agents via the canonical scripts/lib/secret_loader.
    Matches the pattern every other daemon in this repo uses
    (event_router, sequence_runner, override_consumer) — audited
    access via state/secret_access.log, single source of truth, and
    refuses interactive shells.
    """
    try:
        from lib.secret_loader import load_env  # type: ignore
        return load_env()
    except Exception as e:
        # Last-resort fallback so the daemon stays up if the loader
        # ever errors on startup. PM2 backoff handles the rest.
        print(f"[dashboard_email_consumer] secret_loader failed, falling back to os.environ: {e}",
              file=sys.stderr)
        return dict(os.environ)


def _client(env: dict[str, str]):
    """Service-role Supabase client. Returns None on missing config."""
    url = (env.get("BRAVO_SUPABASE_URL") or env.get("SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("[dashboard_email_consumer] BRAVO_SUPABASE_URL / SERVICE_ROLE_KEY missing — sleeping",
              file=sys.stderr)
        return None
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        print("[dashboard_email_consumer] supabase-py not installed. Run: pip install supabase",
              file=sys.stderr)
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        print(f"[dashboard_email_consumer] supabase client error: {e}", file=sys.stderr)
        return None


def _publish_event(sb, *, event_type: str, tenant_id: str, payload: dict) -> None:
    """Insert an agent_events row for observability. Mirrors the
    lib/manifest/events.publishAgentEvent shape on the dashboard
    side: agent_events has no tenant_id column — scope rides on
    correlation_id. Best-effort, never raises.
    """
    try:
        sb.table("agent_events").insert({
            "event_type": event_type,
            "publisher_agent": "dashboard_email_consumer",
            "severity": "info" if event_type.endswith("_SENT") else "warn",
            "correlation_id": tenant_id,
            "payload": {**payload, "tenant_id": tenant_id},
        }).execute()
    except Exception as e:
        print(f"[dashboard_email_consumer] event publish failed ({event_type}): {e}",
              file=sys.stderr)


def _fetch_queued(sb, *, limit: int = 25) -> list[dict]:
    """Pull queued rows. Filter is `metadata.status = 'queued'` and the
    other channel/direction/source guards so we don't accidentally
    re-send drip-engine or legacy rows."""
    try:
        r = (
            sb.table("lead_interactions")
            .select(
                "id, tenant_id, lead_id, subject, content, content_preview, "
                "to_email, agent_source, channel, direction, type, metadata, created_at"
            )
            .eq("channel", "email")
            .eq("direction", "outbound")
            .eq("agent_source", "dashboard_drawer")
            .eq("type", "email_queued")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        rows = r.data or []
    except Exception as e:
        print(f"[dashboard_email_consumer] fetch failed: {e}", file=sys.stderr)
        return []
    # PostgREST can't filter on nested jsonb keys via the python SDK
    # cleanly, so we post-filter on metadata.status here.
    out: list[dict] = []
    for row in rows:
        md = row.get("metadata") or {}
        if isinstance(md, dict) and md.get("status") == "queued":
            out.append(row)
    return out


def _build_message(row: dict, gmail_from: str) -> MIMEMultipart:
    subject = (row.get("subject") or "").strip() or "(no subject)"
    body = (row.get("content") or row.get("content_preview") or "").strip()
    to_email = (row.get("to_email") or "").strip()
    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def _mark_status(sb, row_id: str, *, status: str, error: str | None = None) -> None:
    """Update metadata.status (+ sent_at on success) for one row."""
    md_patch: dict[str, object] = {"status": status}
    if error:
        md_patch["send_error"] = error[:500]
    if status == "sent":
        md_patch["sent_at"] = datetime.now(timezone.utc).isoformat()
    # supabase-py rpc-less jsonb merge: pull the existing metadata, merge,
    # write back.
    try:
        cur = (
            sb.table("lead_interactions")
            .select("metadata")
            .eq("id", row_id)
            .single()
            .execute()
        )
        existing = (cur.data or {}).get("metadata") or {}
        merged = {**(existing if isinstance(existing, dict) else {}), **md_patch}
        update_payload: dict[str, object] = {"metadata": merged}
        if status == "sent":
            update_payload["sent_at"] = datetime.now(timezone.utc).isoformat()
        sb.table("lead_interactions").update(update_payload).eq("id", row_id).execute()
    except Exception as e:
        print(f"[dashboard_email_consumer] mark_status failed for {row_id}: {e}", file=sys.stderr)


def _send_one(env: dict[str, str], sb, row: dict) -> bool:
    """Send one queued email. Returns True on success, False otherwise."""
    row_id = row.get("id")
    to_email = (row.get("to_email") or "").strip()
    if not to_email:
        _mark_status(sb, row_id, status="failed", error="missing to_email")
        return False
    gmail_user = (env.get("GMAIL_USER") or env.get("GMAIL_ADDRESS") or "").strip()
    gmail_pass = (env.get("GMAIL_APP_PASSWORD") or "").strip()
    gmail_from = (env.get("GMAIL_FROM_ADDRESS") or gmail_user or "").strip()
    if not gmail_user or not gmail_pass:
        _mark_status(
            sb,
            row_id,
            status="failed",
            error="GMAIL_USER or GMAIL_APP_PASSWORD missing in .env.agents",
        )
        return False
    msg = _build_message(row, gmail_from or gmail_user)
    tenant_id = row.get("tenant_id") or ""
    lead_id = row.get("lead_id") or ""
    # V5.6 chokepoint: uses shared lib.smtp_send (single source of truth).
    # send_gateway.py and this daemon share the same transport layer.
    try:
        ok, err = smtp_send(gmail_user, gmail_pass, msg, to_email)
        if not ok:
            _mark_status(sb, row_id, status="failed", error=err)
            _publish_event(sb, event_type="BRAVO_DASHBOARD_EMAIL_FAILED",
                           tenant_id=tenant_id,
                           payload={"interaction_id": row_id, "lead_id": lead_id,
                                    "to_email": to_email, "reason": err or "unknown"})
            return False
    except Exception as e:  # noqa: BLE001
        # Network blip — leave queued for retry.
        print(f"[dashboard_email_consumer] send error for {row_id}: {e}", file=sys.stderr)
        return False
    _mark_status(sb, row_id, status="sent")
    _publish_event(sb, event_type="BRAVO_DASHBOARD_EMAIL_SENT",
                   tenant_id=tenant_id,
                   payload={"interaction_id": row_id, "lead_id": lead_id,
                            "to_email": to_email})
    print(f"[dashboard_email_consumer] sent {row_id} → {to_email}", file=sys.stderr)
    return True


def tick(env: dict[str, str], sb) -> dict[str, int]:
    """One pass: fetch + send each queued row. Returns counts."""
    rows = _fetch_queued(sb)
    sent = 0
    failed = 0
    for row in rows:
        ok = _send_one(env, sb, row)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"queued_seen": len(rows), "sent": sent, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard outbound-email consumer")
    parser.add_argument("mode", choices=["once", "loop", "drain"], nargs="?", default="once")
    parser.add_argument("--interval", type=int, default=10,
                        help="seconds between polls in loop mode (default 10)")
    args = parser.parse_args()
    env = _load_env()
    # Ensure secret_loader's loaded values are visible to smtplib + any
    # downstream module that reads os.environ directly.
    for k, v in env.items():
        if k and isinstance(v, str) and k not in os.environ:
            os.environ[k] = v
    sb = _client(env)
    if sb is None:
        # Don't crash — pm2 will hold the process; sleep + retry.
        print("[dashboard_email_consumer] no supabase client; sleeping 60s",
              file=sys.stderr)
        time.sleep(60)
        return 0
    if args.mode == "once":
        result = tick(env, sb)
        print(json.dumps(result))
        return 0
    if args.mode == "drain":
        total = {"queued_seen": 0, "sent": 0, "failed": 0}
        while True:
            result = tick(env, sb)
            for k, v in result.items():
                total[k] += v
            if result["queued_seen"] == 0:
                break
        print(json.dumps(total))
        return 0
    # loop mode
    print(f"[dashboard_email_consumer] starting loop (every {args.interval}s)",
          file=sys.stderr)
    while True:
        try:
            tick(env, sb)
        except Exception as e:  # noqa: BLE001
            print(f"[dashboard_email_consumer] tick error: {e}", file=sys.stderr)
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    sys.exit(main())
