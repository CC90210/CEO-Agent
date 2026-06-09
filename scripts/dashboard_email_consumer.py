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

# CASL compliance at send time. The dashboard drawer queues operator-composed
# lead emails straight to lib.smtp_send, bypassing send_gateway — so the
# suppression check + CASL footer + List-Unsubscribe headers that the gateway
# enforces must be applied HERE too, or this daemon can legally email someone
# who unsubscribed. (Phase 2 of the 2026-06-09 audit remediation.)
from casl_compliance import (  # noqa: E402
    should_suppress,
    build_casl_footer,
    build_casl_footer_html,
    add_list_unsubscribe_headers,
)

# Mirrors send_gateway.VALID_INTENTS — same three values, same semantics.
# Defined locally so the daemon doesn't import the ~160KB gateway module.
# Rule parity with send_gateway: suppression gates intent == "commercial";
# CASL footer + List-Unsubscribe headers apply when intent != "internal".
_VALID_INTENTS = frozenset({"commercial", "transactional", "internal"})

# Per-user Gmail OAuth resolver (Phase 4 SunBiz multi-employee
# personalization). When the dashboard drawer queued the email with a
# metadata.acted_by_user_id stamp, we try to send authenticated as that
# user's connected Gmail. Falls back to the tenant-shared SMTP path
# whenever the user hasn't connected Gmail or the OAuth refresh fails.
try:
    from integrations.user_gmail_oauth import (  # type: ignore  # noqa: E402
        resolve_send_identity as _resolve_send_identity,
        send_via_gmail_api as _send_via_gmail_api,
    )
except Exception:  # noqa: BLE001
    _resolve_send_identity = None  # type: ignore[assignment]
    _send_via_gmail_api = None  # type: ignore[assignment]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _load_env() -> dict[str, str]:
    """Load .env.agents via the canonical scripts/lib/secret_loader.
    Matches the pattern every other daemon in this repo uses
    (event_router, sequence_runner) — audited access via
    state/secret_access.log, single source of truth, and refuses
    interactive shells.
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


def _footer_already_present(content: str, footer_text: str) -> bool:
    """True if the operator already pasted the CASL signature into the body.
    Keyed on the stable "<sender> — <business>" signature line so we never
    double-stamp a footer on a re-queued or hand-signed message."""
    sig_line = next((ln for ln in footer_text.splitlines() if " — " in ln), "")
    return bool(sig_line and sig_line in content)


def _build_message(row: dict, gmail_from: str, intent: str = "commercial") -> MIMEMultipart:
    """Build a multipart/alternative email with BOTH plain-text + OASIS-branded HTML.

    2026-06-06: previously this attached only the plain-text part, so every
    drawer-queued check-in arrived unbranded — CC's complaint after
    shipping the new LeadActionToolbar. send_gateway has had the OASIS
    branding for months via scripts/email_template.render_branded_html;
    we delegate to the same function so every send surface ships the
    same visual brand.

    The plain-text part stays attached as the alternative — clients that
    strip HTML still see the body, and the multipart/alternative ordering
    (text first, html second) means Gmail prefers HTML when available.

    2026-06-09 (audit Phase 2): CASL footer + List-Unsubscribe parity with
    send_gateway. For every non-internal send we append the compliance
    footer (text + HTML) and the RFC 2369/8058 one-click unsubscribe
    headers — the same rule send_gateway applies (`intent != "internal"`).
    Idempotent: skip the footer if the operator already signed the body.
    """
    subject = (row.get("subject") or "").strip() or "(no subject)"
    content = (row.get("content") or row.get("content_preview") or "").strip()
    to_email = (row.get("to_email") or "").strip()

    # CASL footer (text). Mirrors send_gateway: append when intent != internal.
    want_footer = intent != "internal"
    footer_text = build_casl_footer(to_email) if want_footer else ""
    if footer_text and _footer_already_present(content, footer_text):
        want_footer = False  # operator already signed — don't double-stamp
        footer_text = ""
    plain_body = content + footer_text

    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_from
    msg["To"] = to_email
    msg["Subject"] = subject

    # Plain-text part (always attached — fallback for HTML-blocking clients)
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))

    # OASIS-branded HTML part. Import is lazy + best-effort so a missing
    # email_template module degrades to plain-text-only rather than
    # failing the send. Render from the ORIGINAL content (not plain_body)
    # so the footer isn't double-rendered, then append the HTML footer.
    try:
        from email_template import render_branded_html  # type: ignore
        html_body = render_branded_html(content, subject=subject, show_booking=False)
        if want_footer:
            html_body = html_body + build_casl_footer_html(to_email)
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    except Exception as exc:  # noqa: BLE001
        # Log but don't fail — recipient will see the plain-text body.
        print(
            f"[dashboard_email_consumer] OASIS branding failed (sending plain only): {exc}",
            file=sys.stderr,
        )

    # RFC 2369 / 8058 one-click unsubscribe — same rule as send_gateway
    # (every non-internal send). Gives recipients the native Gmail/Outlook
    # Unsubscribe button and satisfies CASL/CAN-SPAM.
    if intent != "internal":
        add_list_unsubscribe_headers(msg, to_email)

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


def _send_one(env: dict[str, str], sb, row: dict) -> str:
    """Send one queued email. Returns 'sent' | 'failed' | 'suppressed'.

    'failed' covers both permanent failures (row marked failed) and transient
    ones (row left 'queued' for retry) — the per-tick counter treats them the
    same; the row's metadata.status carries the durable truth.
    """
    row_id = row.get("id")
    to_email = (row.get("to_email") or "").strip()
    if not to_email:
        _mark_status(sb, row_id, status="failed", error="missing to_email")
        return "failed"
    tenant_id = row.get("tenant_id") or ""
    lead_id = row.get("lead_id") or ""
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}

    # ---- CASL intent classification (parity with send_gateway) ----
    # Default 'commercial' (operator-composed lead emails). The drawer may
    # stamp metadata.intent='transactional' (e.g. a booking confirmation) or
    # 'internal' to opt out of the commercial gates. Unknown values fall back
    # to the safest setting: commercial (gets both suppression + footer).
    intent = str((md or {}).get("intent") or "commercial").strip().lower()
    if intent not in _VALID_INTENTS:
        intent = "commercial"
    brand = (md or {}).get("brand") or None

    # ---- CASL suppression gate (commercial only — matches send_gateway) ----
    # Transactional + internal are exempt (a booking confirmation must still
    # reach someone who unsubscribed from marketing). A suppressed commercial
    # recipient is marked 'suppressed' (not 'failed') so it leaves the queue
    # permanently and the drawer timeline shows why.
    if intent == "commercial" and should_suppress(to_email, tenant_id=tenant_id, brand=brand):
        _mark_status(sb, row_id, status="suppressed")
        _publish_event(
            sb,
            event_type="BRAVO_DASHBOARD_EMAIL_SUPPRESSED",
            tenant_id=tenant_id,
            payload={
                "interaction_id": row_id,
                "lead_id": lead_id,
                "to_email": to_email,
                "reason": "on_suppression_list",
            },
        )
        print(
            f"[dashboard_email_consumer] SUPPRESSED {row_id} → {to_email} "
            f"(on suppression list; not sent)",
            file=sys.stderr,
        )
        return "suppressed"

    # Phase 4 SunBiz multi-employee personalization: the drawer stamps
    # metadata.acted_by_user_id when the operator queued the send. If
    # that user has connected their personal Gmail, send authenticated
    # as them; otherwise fall through to the shared SMTP path.
    acted_by_user_id = (md or {}).get("acted_by_user_id") or ""

    identity = (
        _resolve_send_identity(sb, tenant_id, acted_by_user_id)
        if _resolve_send_identity is not None
        else {"mode": "tenant_smtp"}
    )
    if identity["mode"] == "block":
        _mark_status(sb, row_id, status="failed", error=identity["reason"])
        _publish_event(
            sb,
            event_type="BRAVO_DASHBOARD_EMAIL_FAILED",
            tenant_id=tenant_id,
            payload={
                "interaction_id": row_id,
                "lead_id": lead_id,
                "to_email": to_email,
                "reason": "user_gmail_oauth_resolution_failed",
                "acted_by_user_id": acted_by_user_id,
            },
        )
        return "failed"
    user_bundle = identity["bundle"] if identity["mode"] == "user_oauth" else None

    sent_via = "smtp"
    sent_as = ""
    err: str | None = None
    ok = False

    if user_bundle and _send_via_gmail_api is not None:
        gmail_from = user_bundle["gmail_address"]
        msg = _build_message(row, gmail_from, intent)
        try:
            raw = msg.as_bytes()
        except Exception:
            raw = msg.as_string().encode("utf-8")
        try:
            ok, err = _send_via_gmail_api(user_bundle["access_token"], raw)
        except Exception as e:  # noqa: BLE001
            print(
                f"[dashboard_email_consumer] gmail_api raised for {row_id}: {e}",
                file=sys.stderr,
            )
            return "failed"
        sent_via = "gmail_api"
        sent_as = gmail_from
    else:
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
            return "failed"
        msg = _build_message(row, gmail_from or gmail_user, intent)
        try:
            ok, err = smtp_send(
                gmail_user, gmail_pass, msg, to_email,
                require_from_domain=env.get("EMAIL_REQUIRE_FROM_DOMAIN"),
            )
        except Exception as e:  # noqa: BLE001
            # Network blip — leave queued for retry.
            print(
                f"[dashboard_email_consumer] send error for {row_id}: {e}",
                file=sys.stderr,
            )
            return "failed"
        sent_as = gmail_from or gmail_user

    if not ok:
        _mark_status(sb, row_id, status="failed", error=err)
        _publish_event(
            sb,
            event_type="BRAVO_DASHBOARD_EMAIL_FAILED",
            tenant_id=tenant_id,
            payload={
                "interaction_id": row_id,
                "lead_id": lead_id,
                "to_email": to_email,
                "reason": err or "unknown",
                "sent_via": sent_via,
            },
        )
        return "failed"

    _mark_status(sb, row_id, status="sent")
    _publish_event(
        sb,
        event_type="BRAVO_DASHBOARD_EMAIL_SENT",
        tenant_id=tenant_id,
        payload={
            "interaction_id": row_id,
            "lead_id": lead_id,
            "to_email": to_email,
            "sent_via": sent_via,
            "sent_as": sent_as,
        },
    )
    print(
        f"[dashboard_email_consumer] sent {row_id} → {to_email} "
        f"via={sent_via} as={sent_as}",
        file=sys.stderr,
    )
    return "sent"


def tick(env: dict[str, str], sb) -> dict[str, int]:
    """One pass: fetch + send each queued row. Returns counts."""
    rows = _fetch_queued(sb)
    counts = {"queued_seen": len(rows), "sent": 0, "failed": 0, "suppressed": 0}
    for row in rows:
        status = _send_one(env, sb, row)
        if status == "sent":
            counts["sent"] += 1
        elif status == "suppressed":
            counts["suppressed"] += 1
        else:
            counts["failed"] += 1
    return counts


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
        total = {"queued_seen": 0, "sent": 0, "failed": 0, "suppressed": 0}
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
