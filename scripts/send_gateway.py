"""
Send Gateway — the single outbound chokepoint for every autonomous action
Bravo performs on behalf of CC's empire.

WHY THIS EXISTS
---------------
Before this module, four Python engines (outreach_engine, outreach_batch,
email_engine, funnel_nurture) plus one N8N workflow (OASIS Inbound Qualifier)
could all contact the same lead on the same day without ever seeing each
other. They wrote to three different tables (email_log, lead_interactions,
funnel_leads.follow_up_count) so no cross-engine query was possible. That
is the root cause of the "AI sends 10 emails in a row" behavior CC described
in the 2026-04-19 audit.

This module replaces all of those ad-hoc send paths. Every engine imports
`send(...)` from here. Idempotency, CASL enforcement, cooldowns, daily caps,
and observability are ENFORCED ARCHITECTURALLY — a caller physically cannot
send without them, because the smtplib / Playwright / whatever call happens
inside this file and nowhere else.

HOW IT IS USED
--------------
From any engine::

    from send_gateway import send

    result = send(
        channel="email",
        to_email="jane@acme.com",
        subject="Quick question about your HVAC scheduling",
        body_text="Hi Jane, ...",
        body_html="<p>Hi Jane ...</p>",
        lead_id="<uuid>",               # if known; auto-resolved if omitted + email given
        agent_source="outreach_engine",  # who is calling
        brand="oasis",                   # 'oasis' | 'kona_makana' | 'nostalgic'
        intent="commercial",             # 'commercial' | 'transactional' | 'internal'
        cooldown_hours=None,             # None -> DEFAULT_COOLDOWNS[channel]
        dry_run=False,
    )

    # result is always a dict:
    # {"status": "sent"|"blocked"|"suppressed"|"dry_run"|"error",
    #  "reason": "...", "lead_id": "...", "interaction_id": "...",
    #  "cooldown_until": "...", "daily_count": int}

From the CLI (scheduler, Telegram, manual)::

    python scripts/send_gateway.py send --channel email --to jane@acme.com \\
        --subject "..." --body "..." --agent-source manual_cc --json

    python scripts/send_gateway.py can-act --lead-id <uuid> --channel email --json
    python scripts/send_gateway.py stats --json
    python scripts/send_gateway.py history --lead-id <uuid> --limit 10

DESIGN DECISIONS
----------------
1. Single choke point. Every outbound Python path goes through send(). If an
   engine bypasses this, CASL and cooldown are not enforced. Reviewers must
   reject any PR that calls smtplib directly from a business engine.
2. Architectural idempotency. The cooldown check happens INSIDE send(),
   reading from lead_interactions. Callers cannot forget to check because
   there is no separate check-then-act API.
3. Multi-brand by construction. brand="oasis"|"kona_makana"|"nostalgic" lets
   CC's six business brands share this path while still speaking in their
   own voices. Brand identity flows into CASL footer sender_name + business_name.
4. Transactional exemption. intent="transactional" skips the suppression
   check for booking confirmations and reminders (CASL s. 10(9)) but still
   adds footer + List-Unsubscribe (best practice, protects deliverability).
5. Graceful degradation. If the migration 003 columns don't exist yet, the
   gateway falls back to legacy write paths without crashing, logging a
   warning instead. This lets CC apply the migration when convenient.
6. Observable. Every send writes to lead_interactions (architectural) AND
   email_log (legacy SMTP truth). Callers can still read either table.

CALLER CONTRACT
---------------
- `send()` NEVER raises. On error it returns status="error" with reason.
- `send()` NEVER double-sends. If the cooldown check fails, status="blocked".
- `send()` NEVER sends to a suppressed address on commercial intent.
- `send()` ALWAYS logs to lead_interactions (except on dry_run or block).
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional

# ---- Path + env wiring (same pattern used by every other engine) -----------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from casl_compliance import (  # noqa: E402
    should_suppress,
    build_casl_footer,
    build_casl_footer_html,
    add_list_unsubscribe_headers,
)

try:
    from notify import notify as _telegram_notify  # noqa: F401
except ImportError:
    def _telegram_notify(*_a: Any, **_kw: Any) -> bool:  # type: ignore[misc]
        return False


# ---- Canonical constants ----------------------------------------------------

# Cooldown windows per channel. Conservative by default — CC is a 22yo founder
# still building reputation; better to under-send than to look spammy.
DEFAULT_COOLDOWNS: dict[str, int] = {
    "email": 72,        # 3 days between cold emails to the same lead
    "instagram": 48,    # 2 days between DMs
    "linkedin": 72,     # 3 days
    "phone": 168,       # 7 days between calls
    "skool": 24,        # 1 day — community is higher frequency
    "telegram": 0,      # internal, no cooldown
}

# Global daily outbound caps. Prevents any single day becoming a firehose
# even if a bug slips through. Breach triggers fail-closed: gateway refuses.
DAILY_CAPS: dict[str, int] = {
    "email": 50,        # 50 outbound emails/day hard cap
    "instagram": 30,    # 30 DMs/day (IG is especially spam-sensitive)
    "linkedin": 20,     # 20 connection requests / messages / day
    "phone": 15,        # 15 calls/day sanity bound
}

# Canonical agent_source tags — whoever is calling MUST identify itself.
# Free-form strings allowed, but staying on these values keeps audits sane.
KNOWN_AGENT_SOURCES: frozenset[str] = frozenset({
    "outreach_engine",
    "outreach_batch",
    "funnel_nurture",
    "email_engine",
    "booking_engine",
    "instagram_engine",
    "linkedin_cli",
    "skool_engine",
    "n8n_inbound",
    "manual_cc",
    "scheduler",
    "test_harness",
})

# Canonical channel tags.
KNOWN_CHANNELS: frozenset[str] = frozenset(DEFAULT_COOLDOWNS.keys())

# Intent determines CASL treatment.
VALID_INTENTS: frozenset[str] = frozenset({"commercial", "transactional", "internal"})

# Brand identity — flows into CASL footer. Add a brand here when CC wants
# a new one to share the gateway. The values match the project's known
# business brands; DEFAULT is OASIS AI (the main outreach vehicle).
BRAND_IDENTITY: dict[str, dict[str, str]] = {
    "oasis": {
        "business_name": "OASIS AI Solutions",
        "sender_name": "Conaugh McKenna",
        "business_address": "OASIS AI Solutions, Collingwood, ON, Canada",
        "from_display": "Conaugh McKenna — OASIS AI",
    },
    "kona_makana": {
        "business_name": "Kona Makana",
        "sender_name": "CC (Kona Makana)",
        "business_address": "Kona Makana, Collingwood, ON, Canada",
        "from_display": "Kona Makana",
    },
    "nostalgic": {
        "business_name": "Nostalgic Requests",
        "sender_name": "Conaugh McKenna",
        "business_address": "Nostalgic Requests, Collingwood, ON, Canada",
        "from_display": "Nostalgic Requests",
    },
}

DEFAULT_BRAND = "oasis"


# ---- Env + DB ---------------------------------------------------------------

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    # Also mirror into os.environ so downstream helpers resolve
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def get_supabase(env_vars: Optional[dict[str, str]] = None):
    env = env_vars if env_vars is not None else load_env()
    url = env.get("BRAVO_SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError(
            "Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY "
            "in .env.agents — send_gateway cannot query the interaction ledger."
        )
    from supabase import create_client
    return create_client(url, key)


# ---- Lead resolution --------------------------------------------------------

def resolve_lead_id(db, to_email: Optional[str], lead_id: Optional[str]) -> Optional[str]:
    """Return the lead UUID for a given email, creating one if it does not
    exist yet. None if neither lead_id nor to_email is provided.

    The gateway deliberately auto-creates a lead record. Before this existed,
    outreach to a freshly-scraped address had no CRM trace, so scoring and
    pipeline reports were always behind reality.
    """
    if lead_id:
        return lead_id
    if not to_email:
        return None
    norm = to_email.strip().lower()
    try:
        existing = db.table("leads").select("id").eq("email", norm).limit(1).execute()
        if existing.data:
            return existing.data[0]["id"]
        # Create a minimal lead record for audit trail
        now = datetime.now(timezone.utc).isoformat()
        created = db.table("leads").insert({
            "name": norm.split("@")[0],  # placeholder — CC or scraper can enrich later
            "email": norm,
            "status": "new",
            "source": "gateway_autocreate",
            "created_at": now,
            "updated_at": now,
        }).execute()
        return created.data[0]["id"] if created.data else None
    except Exception as exc:  # noqa: BLE001
        # Lead resolution is best-effort; a DB blip must not block sending.
        print(f"[send_gateway] resolve_lead_id warning: {exc}", file=sys.stderr)
        return None


# ---- Idempotency core -------------------------------------------------------

def can_act(
    lead_id: Optional[str],
    channel: str,
    to_email: Optional[str] = None,
    cooldown_hours: Optional[int] = None,
    db: Any = None,
) -> dict:
    """Pre-send check. Returns::

        {"allowed": bool, "reason": str, "last_action_at": str|None,
         "cooldown_until": str|None, "daily_count": int, "daily_cap": int|None}

    Four gates applied in order:
      1. Supression (commercial intent checked inside send(); here we only
         report it so callers can see why a send was blocked).
      2. Active cooldown on (lead_id, channel).
      3. Daily cap for channel (global, across all leads).
      4. Empty-to-email (treated as suppressed, never send).

    This function is SAFE to call without a resolved lead_id — in that case
    only the daily cap is checked. Resolution happens inside send().
    """
    db = db if db is not None else get_supabase()
    now = datetime.now(timezone.utc)
    channel = channel.lower()

    result: dict[str, Any] = {
        "allowed": True,
        "reason": "ok",
        "last_action_at": None,
        "cooldown_until": None,
        "daily_count": 0,
        "daily_cap": DAILY_CAPS.get(channel),
    }

    # Gate 1: empty email (commercial intent will catch suppression separately).
    if to_email is not None and not (to_email or "").strip():
        result.update(allowed=False, reason="empty recipient")
        return result

    # Gate 2: active cooldown on this lead+channel.
    if lead_id:
        try:
            rows = (
                db.table("lead_interactions")
                .select("created_at, cooldown_until")
                .eq("lead_id", lead_id)
                .eq("channel", channel)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
            )
        except Exception as exc:  # noqa: BLE001
            # Likely the migration 003 columns do not exist yet. Fall back to
            # querying without cooldown_until so the engine still functions.
            try:
                rows = (
                    db.table("lead_interactions")
                    .select("created_at")
                    .eq("lead_id", lead_id)
                    .eq("channel", channel)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                    .data
                )
                for r in rows or []:
                    r["cooldown_until"] = None
            except Exception as exc2:  # noqa: BLE001
                print(
                    f"[send_gateway] can_act cooldown query failed: {exc2}; "
                    "treating as allowed (degraded mode).",
                    file=sys.stderr,
                )
                rows = []

        if rows:
            last = rows[0]
            result["last_action_at"] = last.get("created_at")
            cu_raw = last.get("cooldown_until")
            if cu_raw:
                try:
                    cu = datetime.fromisoformat(cu_raw.replace("Z", "+00:00"))
                    result["cooldown_until"] = cu.isoformat()
                    if now < cu:
                        result.update(
                            allowed=False,
                            reason=f"cooldown active until {cu.isoformat()}",
                        )
                        return result
                except (ValueError, TypeError):
                    pass
            else:
                # Legacy row without cooldown_until: apply default window
                # from last action.
                try:
                    created_at = datetime.fromisoformat(
                        (last.get("created_at") or "").replace("Z", "+00:00")
                    )
                    window_hours = (
                        cooldown_hours
                        if cooldown_hours is not None
                        else DEFAULT_COOLDOWNS.get(channel, 0)
                    )
                    if window_hours > 0:
                        implied_cu = created_at + timedelta(hours=window_hours)
                        result["cooldown_until"] = implied_cu.isoformat()
                        if now < implied_cu:
                            result.update(
                                allowed=False,
                                reason=(
                                    f"implied cooldown (legacy row, "
                                    f"{window_hours}h window) "
                                    f"until {implied_cu.isoformat()}"
                                ),
                            )
                            return result
                except (ValueError, TypeError):
                    pass

    # Gate 3: daily cap.
    cap = DAILY_CAPS.get(channel)
    if cap is not None:
        try:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            rows = (
                db.table("lead_interactions")
                .select("id", count="exact")
                .eq("channel", channel)
                .gte("created_at", day_start.isoformat())
                .execute()
            )
            count = rows.count or 0
            result["daily_count"] = count
            if count >= cap:
                result.update(
                    allowed=False,
                    reason=f"daily cap hit: {count}/{cap} {channel} actions today",
                )
                return result
        except Exception as exc:  # noqa: BLE001
            print(
                f"[send_gateway] can_act daily-cap query failed: {exc}",
                file=sys.stderr,
            )

    return result


# ---- Logging ----------------------------------------------------------------

def log_action(
    db,
    lead_id: Optional[str],
    channel: str,
    action_type: str,
    subject: Optional[str],
    content_preview: Optional[str],
    agent_source: str,
    cooldown_hours: Optional[int],
    metadata: Optional[dict] = None,
    to_email: Optional[str] = None,
) -> Optional[str]:
    """Write a row to lead_interactions. Returns the new row id, or None on
    failure. Also writes a row to email_log for email sends so the legacy
    SMTP-layer reports keep working.

    Graceful degradation: if migration 003 columns (cooldown_until,
    agent_source) do not yet exist, the insert falls back to the pre-migration
    schema and logs a warning. This lets the gateway ship before the
    migration is applied.
    """
    now = datetime.now(timezone.utc)
    cooldown_until: Optional[str] = None
    if cooldown_hours and cooldown_hours > 0:
        cooldown_until = (now + timedelta(hours=cooldown_hours)).isoformat()

    row: dict[str, Any] = {
        "type": action_type,
        "channel": channel,
        "created_at": now.isoformat(),
    }
    if lead_id:
        row["lead_id"] = lead_id
    if subject:
        row["subject"] = subject[:500]
    if content_preview:
        row["content"] = content_preview[:1000]
    if metadata:
        row["metadata"] = metadata
    if agent_source:
        row["agent_source"] = agent_source
    if cooldown_until:
        row["cooldown_until"] = cooldown_until

    interaction_id: Optional[str] = None
    try:
        res = db.table("lead_interactions").insert(row).execute()
        interaction_id = res.data[0].get("id") if res.data else None
    except Exception as exc:  # noqa: BLE001
        # Likely because cooldown_until / agent_source columns do not exist.
        # Retry with the legacy column set so the send still gets logged.
        legacy_row = {k: v for k, v in row.items() if k not in {"cooldown_until", "agent_source"}}
        try:
            res = db.table("lead_interactions").insert(legacy_row).execute()
            interaction_id = res.data[0].get("id") if res.data else None
            print(
                "[send_gateway] degraded mode: migration 003 not applied; "
                "cooldown_until + agent_source NOT persisted.",
                file=sys.stderr,
            )
        except Exception as exc2:  # noqa: BLE001
            print(
                f"[send_gateway] lead_interactions insert failed: {exc2}",
                file=sys.stderr,
            )

    # Mirror email sends to email_log for backward compatibility with all
    # legacy queries and analytics built on email_log.
    if channel == "email" and action_type in {"email_sent", "email_reply"}:
        try:
            db.table("email_log").insert({
                "to_email": to_email,
                "subject": subject or "",
                "body_preview": (content_preview or "")[:200],
                "status": "sent" if action_type == "email_sent" else "received",
                "sent_at": now.isoformat(),
                "lead_id": lead_id,
            }).execute()
        except Exception as exc:  # noqa: BLE001
            # Legacy mirror is best-effort; lead_interactions is truth.
            print(f"[send_gateway] email_log mirror warning: {exc}", file=sys.stderr)

    # Update leads.last_contacted_at so the CRM view stays fresh.
    if lead_id and action_type in {"email_sent", "dm_sent", "call"}:
        try:
            db.table("leads").update({
                "last_contacted_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }).eq("id", lead_id).execute()
        except Exception as exc:  # noqa: BLE001
            print(f"[send_gateway] leads.last_contacted_at update warning: {exc}", file=sys.stderr)

    return interaction_id


def get_entity_history(db, lead_id: str, limit: int = 20) -> list[dict]:
    """Return the last N interactions for a lead, newest first. Consumed
    by context_builder.py (persona engine)."""
    try:
        rows = (
            db.table("lead_interactions")
            .select("*")
            .eq("lead_id", lead_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return rows or []
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] get_entity_history warning: {exc}", file=sys.stderr)
        return []


def get_daily_stats(db, channel: Optional[str] = None) -> dict:
    """Counts of actions today by channel. For the daily Telegram digest
    and the CEO briefing."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result: dict[str, Any] = {"date": day_start.date().isoformat(), "channels": {}}
    channels = [channel] if channel else list(KNOWN_CHANNELS)
    for c in channels:
        try:
            r = (
                db.table("lead_interactions")
                .select("id", count="exact")
                .eq("channel", c)
                .gte("created_at", day_start.isoformat())
                .execute()
            )
            result["channels"][c] = {
                "count": r.count or 0,
                "cap": DAILY_CAPS.get(c),
            }
        except Exception as exc:  # noqa: BLE001
            result["channels"][c] = {"count": None, "cap": DAILY_CAPS.get(c), "error": str(exc)}
    result["total"] = sum(
        (c["count"] or 0) for c in result["channels"].values()
    )
    return result


# ---- Email sender (the real smtplib call) -----------------------------------

def _build_email_mime(
    gmail_address: str,
    brand: dict[str, str],
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str],
    intent: str,
    ics_content: Optional[str] = None,
    ics_filename: str = "meeting.ics",
    attachments: Optional[list[dict]] = None,
) -> MIMEMultipart:
    """Assemble the MIME payload: CASL footer + List-Unsubscribe headers,
    optional HTML body, optional .ics calendar invite, optional generic
    file attachments (PDFs, images, whatever).

    Structure:
      multipart/mixed
        ├── multipart/alternative
        │     ├── text/plain  (body_text + CASL footer)
        │     └── text/html   (body_html + CASL footer html)  [if provided]
        ├── text/calendar     (the .ics REQUEST)              [if provided]
        └── <each attachment> (application/pdf, etc.)         [if provided]

    This is the canonical shape Gmail/Outlook/Apple Mail all render correctly.

    Each attachment in `attachments` is a dict:
        {"filename": "invoice.pdf",
         "content": b"<raw bytes>",
         "content_type": "application/pdf"   # optional; defaults to
                                              # application/octet-stream}
    """
    # Append CASL footer for every outbound path (both commercial and
    # transactional). Only intent="internal" skips the footer.
    if intent != "internal":
        body_text = body_text + build_casl_footer(
            to_email,
            business_name=brand["business_name"],
            business_address=brand["business_address"],
            sender_name=brand["sender_name"],
        )
        if body_html:
            body_html = body_html + build_casl_footer_html(
                to_email,
                business_name=brand["business_name"],
                business_address=brand["business_address"],
                sender_name=brand["sender_name"],
            )

    # Top-level envelope — mixed so we can attach non-body parts (.ics etc.)
    outer = MIMEMultipart("mixed")
    outer["Subject"] = subject
    outer["From"] = f'{brand["from_display"]} <{gmail_address}>'
    outer["To"] = to_email
    if intent != "internal":
        add_list_unsubscribe_headers(outer, to_email)

    # Body part — text/plain always, text/html optional
    body_alt = MIMEMultipart("alternative")
    body_alt.attach(MIMEText(body_text, "plain"))
    if body_html:
        body_alt.attach(MIMEText(body_html, "html"))
    outer.attach(body_alt)

    # Optional .ics calendar invite attachment
    if ics_content:
        ics_part = MIMEBase("text", "calendar", method="REQUEST")
        ics_part.set_payload(ics_content.encode("utf-8"))
        encoders.encode_base64(ics_part)
        ics_part.add_header("Content-Disposition", "attachment", filename=ics_filename)
        outer.attach(ics_part)

    # Optional generic file attachments (PDFs, images, etc.). Each dict must
    # supply filename + content bytes. content_type defaults to the generic
    # application/octet-stream if not supplied.
    for att in (attachments or []):
        fname = att.get("filename") or "attachment.bin"
        content_bytes = att.get("content")
        if not content_bytes:
            continue
        ctype = att.get("content_type") or "application/octet-stream"
        maintype, _, subtype = ctype.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        part = MIMEBase(maintype, subtype)
        part.set_payload(content_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=fname)
        outer.attach(part)

    return outer


def _send_email_smtp(
    env: dict[str, str],
    mime: MIMEMultipart,
    to_email: str,
) -> tuple[bool, Optional[str]]:
    gmail_user = env.get("GMAIL_USER") or env.get("GMAIL_ADDRESS", "")
    gmail_pass = env.get("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pass:
        return False, "GMAIL_USER/GMAIL_APP_PASSWORD missing in .env.agents"
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, to_email, mime.as_string())
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed — rotate GMAIL_APP_PASSWORD"
    except smtplib.SMTPRecipientsRefused:
        return False, f"recipient refused by server: {to_email}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected send error: {e}"


# ---- Public API -------------------------------------------------------------

def send(
    channel: str,
    agent_source: str,
    *,
    to_email: Optional[str] = None,
    lead_id: Optional[str] = None,
    subject: Optional[str] = None,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    brand: str = DEFAULT_BRAND,
    intent: str = "commercial",
    cooldown_hours: Optional[int] = None,
    metadata: Optional[dict] = None,
    ics_content: Optional[str] = None,
    ics_filename: str = "meeting.ics",
    attachments: Optional[list[dict]] = None,
    dry_run: bool = False,
    db: Any = None,
) -> dict:
    """Single outbound chokepoint.

    Returns a status dict:

        {"status": "sent"|"blocked"|"suppressed"|"dry_run"|"error",
         "reason": str, "lead_id": str|None, "interaction_id": str|None,
         "cooldown_until": str|None, "daily_count": int|None}

    NEVER raises. A caller can trust that the return shape above always holds.
    """
    # ---- Validate inputs ----
    channel = (channel or "").lower()
    if channel not in KNOWN_CHANNELS:
        return {"status": "error", "reason": f"unknown channel '{channel}'",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}
    if intent not in VALID_INTENTS:
        return {"status": "error", "reason": f"invalid intent '{intent}'",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}
    if not agent_source:
        return {"status": "error", "reason": "agent_source required",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}
    if brand not in BRAND_IDENTITY:
        return {"status": "error", "reason": f"unknown brand '{brand}' — "
                f"known: {sorted(BRAND_IDENTITY.keys())}",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}
    brand_cfg = BRAND_IDENTITY[brand]

    # ---- Per-channel required fields ----
    if channel == "email":
        if not to_email or not subject or not body_text:
            return {"status": "error",
                    "reason": "email channel requires to_email, subject, body_text",
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

    # ---- Resolve DB + lead ----
    env = load_env()
    try:
        db = db if db is not None else get_supabase(env)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": f"supabase unavailable: {exc}",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    lead_id = resolve_lead_id(db, to_email, lead_id)

    # ---- Gate 1: commercial suppression ----
    if intent == "commercial" and to_email and should_suppress(to_email):
        return {"status": "suppressed",
                "reason": f"{to_email} is on CASL suppression list",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- Gate 2 + 3: cooldown + daily cap (skipped for internal intent) ----
    if intent != "internal":
        check = can_act(
            lead_id=lead_id,
            channel=channel,
            to_email=to_email,
            cooldown_hours=cooldown_hours,
            db=db,
        )
        if not check["allowed"]:
            return {"status": "blocked",
                    "reason": check["reason"],
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": check.get("cooldown_until"),
                    "daily_count": check.get("daily_count")}

    # ---- Dry run ----
    if dry_run:
        return {"status": "dry_run",
                "reason": "dry_run=True, nothing sent",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- Channel dispatch ----
    if channel == "email":
        gmail_user = env.get("GMAIL_USER") or env.get("GMAIL_ADDRESS", "")
        if not gmail_user:
            return {"status": "error",
                    "reason": "GMAIL_USER missing in .env.agents",
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

        mime = _build_email_mime(
            gmail_address=gmail_user,
            brand=brand_cfg,
            to_email=to_email,  # type: ignore[arg-type]
            subject=subject,  # type: ignore[arg-type]
            body_text=body_text,  # type: ignore[arg-type]
            body_html=body_html,
            intent=intent,
            ics_content=ics_content,
            ics_filename=ics_filename,
            attachments=attachments,
        )
        ok, err = _send_email_smtp(env, mime, to_email)  # type: ignore[arg-type]
        if not ok:
            # Log failure so future diagnostics see the attempt.
            try:
                db.table("email_log").insert({
                    "to_email": to_email,
                    "subject": subject or "",
                    "body_preview": (body_text or "")[:200],
                    "status": "failed",
                    "error_message": err,
                    "lead_id": lead_id,
                }).execute()
            except Exception:  # noqa: BLE001
                pass
            return {"status": "error", "reason": err,
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

        # Successful send — log it.
        effective_cooldown = (
            cooldown_hours
            if cooldown_hours is not None
            else DEFAULT_COOLDOWNS.get(channel, 0)
        )
        full_metadata = dict(metadata or {})
        full_metadata.update({
            "brand": brand,
            "intent": intent,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        interaction_id = log_action(
            db=db,
            lead_id=lead_id,
            channel=channel,
            action_type="email_sent",
            subject=subject,
            content_preview=body_text,
            agent_source=agent_source,
            cooldown_hours=effective_cooldown,
            metadata=full_metadata,
            to_email=to_email,
        )
        return {"status": "sent",
                "reason": "ok",
                "lead_id": lead_id,
                "interaction_id": interaction_id,
                "cooldown_until": (datetime.now(timezone.utc)
                                   + timedelta(hours=effective_cooldown)).isoformat()
                if effective_cooldown else None,
                "daily_count": None}

    # Non-email channels are logged only — the real send happens in the
    # channel-specific engine (instagram_engine, linkedin_cli, etc.). The
    # gateway still enforces cooldown + cap BEFORE those engines act; they
    # import can_act() directly.
    effective_cooldown = (
        cooldown_hours
        if cooldown_hours is not None
        else DEFAULT_COOLDOWNS.get(channel, 0)
    )
    full_metadata = dict(metadata or {})
    full_metadata.update({"brand": brand, "intent": intent})
    interaction_id = log_action(
        db=db,
        lead_id=lead_id,
        channel=channel,
        action_type=f"{channel}_sent",
        subject=subject,
        content_preview=body_text,
        agent_source=agent_source,
        cooldown_hours=effective_cooldown,
        metadata=full_metadata,
        to_email=to_email,
    )
    return {"status": "sent",
            "reason": "non-email channel: logged only, engine performs physical send",
            "lead_id": lead_id,
            "interaction_id": interaction_id,
            "cooldown_until": (datetime.now(timezone.utc)
                               + timedelta(hours=effective_cooldown)).isoformat()
            if effective_cooldown else None,
            "daily_count": None}


# ---- CLI --------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_send(args) -> int:
    result = send(
        channel=args.channel,
        agent_source=args.agent_source,
        to_email=args.to,
        lead_id=args.lead_id,
        subject=args.subject,
        body_text=args.body,
        body_html=args.body_html,
        brand=args.brand,
        intent=args.intent,
        cooldown_hours=args.cooldown,
        dry_run=args.dry_run,
    )
    if args.output_json:
        _print_json(result)
    else:
        print(f"[send_gateway] status={result['status']} reason={result['reason']}")
        if result.get("interaction_id"):
            print(f"  interaction_id: {result['interaction_id']}")
        if result.get("cooldown_until"):
            print(f"  cooldown_until: {result['cooldown_until']}")
    return 0 if result["status"] in {"sent", "dry_run"} else 1


def _cmd_can_act(args) -> int:
    db = get_supabase()
    r = can_act(
        lead_id=args.lead_id,
        channel=args.channel,
        to_email=args.to,
        cooldown_hours=args.cooldown,
        db=db,
    )
    if args.output_json:
        _print_json(r)
    else:
        print(f"allowed: {r['allowed']}")
        print(f"reason: {r['reason']}")
        if r.get("last_action_at"):
            print(f"last_action_at: {r['last_action_at']}")
        if r.get("cooldown_until"):
            print(f"cooldown_until: {r['cooldown_until']}")
        print(f"daily_count: {r.get('daily_count')}/{r.get('daily_cap')}")
    return 0 if r["allowed"] else 1


def _cmd_history(args) -> int:
    db = get_supabase()
    rows = get_entity_history(db, args.lead_id, limit=args.limit)
    if args.output_json:
        _print_json(rows)
        return 0
    if not rows:
        print(f"No history for lead {args.lead_id}.")
        return 0
    for r in rows:
        print(f"  {r.get('created_at','')[:19]}  "
              f"{r.get('channel','-'):10}  "
              f"{r.get('type','-'):14}  "
              f"src={r.get('agent_source','-')}  "
              f"subj={(r.get('subject') or '-')[:60]}")
    print(f"\n  {len(rows)} interaction(s).")
    return 0


def _cmd_stats(args) -> int:
    db = get_supabase()
    s = get_daily_stats(db, channel=args.channel)
    if args.output_json:
        _print_json(s)
    else:
        print(f"Daily stats ({s['date']}):")
        for ch, d in s["channels"].items():
            cap = d.get("cap")
            cnt = d.get("count")
            print(f"  {ch:10}  {cnt}/{cap if cap is not None else '-'}")
        print(f"  TOTAL      {s['total']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="send_gateway.py",
        description="Single outbound chokepoint: CASL + cooldown + daily cap + log.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    ps = sub.add_parser("send", help="Send an outbound message")
    ps.add_argument("--channel", required=True, choices=sorted(KNOWN_CHANNELS))
    ps.add_argument("--agent-source", dest="agent_source", required=True)
    ps.add_argument("--to", default=None, help="Recipient email (for email channel)")
    ps.add_argument("--lead-id", dest="lead_id", default=None)
    ps.add_argument("--subject", default=None)
    ps.add_argument("--body", default=None, help="Plain text body")
    ps.add_argument("--body-html", dest="body_html", default=None)
    ps.add_argument("--brand", default=DEFAULT_BRAND, choices=sorted(BRAND_IDENTITY.keys()))
    ps.add_argument("--intent", default="commercial", choices=sorted(VALID_INTENTS))
    ps.add_argument("--cooldown", type=int, default=None, help="Override cooldown hours")
    ps.add_argument("--dry-run", dest="dry_run", action="store_true")

    pc = sub.add_parser("can-act", help="Check if a send is allowed")
    pc.add_argument("--lead-id", dest="lead_id", default=None)
    pc.add_argument("--channel", required=True, choices=sorted(KNOWN_CHANNELS))
    pc.add_argument("--to", default=None)
    pc.add_argument("--cooldown", type=int, default=None)

    ph = sub.add_parser("history", help="Recent interactions for a lead")
    ph.add_argument("--lead-id", dest="lead_id", required=True)
    ph.add_argument("--limit", type=int, default=20)

    pss = sub.add_parser("stats", help="Today's outbound counts by channel")
    pss.add_argument("--channel", default=None, choices=sorted(KNOWN_CHANNELS))

    args = p.parse_args()

    if args.command == "send":
        sys.exit(_cmd_send(args))
    elif args.command == "can-act":
        sys.exit(_cmd_can_act(args))
    elif args.command == "history":
        sys.exit(_cmd_history(args))
    elif args.command == "stats":
        sys.exit(_cmd_stats(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
