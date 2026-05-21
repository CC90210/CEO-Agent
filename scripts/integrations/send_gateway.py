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
        brand="oasis",                   # 'oasis' | 'conaugh_mckenna' | 'nostalgic'
        intent="commercial",             # 'commercial' | 'transactional' | 'internal'
        cooldown_hours=None,             # None -> DEFAULT_COOLDOWNS[channel]
        dry_run=False,
    )

    # result is always a dict:
    # {"status": "sent"|"blocked"|"suppressed"|"dry_run"|"error",
    #  "reason": "...", "lead_id": "...", "interaction_id": "...",
    #  "cooldown_until": "...", "daily_count": int}

From the CLI (scheduler, Telegram, manual)::

    python scripts/integrations/send_gateway.py send --channel email --to jane@acme.com \\
        --subject "..." --body "..." --agent-source manual_cc --json

    python scripts/integrations/send_gateway.py can-act --lead-id <uuid> --channel email --json
    python scripts/integrations/send_gateway.py stats --json
    python scripts/integrations/send_gateway.py history --lead-id <uuid> --limit 10

DESIGN DECISIONS
----------------
1. Single choke point. Every outbound Python path goes through send(). If an
   engine bypasses this, CASL and cooldown are not enforced. Reviewers must
   reject any PR that calls smtplib directly from a business engine.
2. Architectural idempotency. The cooldown check happens INSIDE send(),
   reading from lead_interactions. Callers cannot forget to check because
   there is no separate check-then-act API.
3. Multi-brand by construction. brand="oasis"|"conaugh_mckenna"|"nostalgic" lets
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
import math
import os
import re
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from casl_compliance import (  # noqa: E402
    should_suppress,
    should_suppress_phone,
    is_reserved_domain,
    build_casl_footer,
    build_casl_footer_html,
    add_list_unsubscribe_headers,
)
from lib.smtp_send import smtp_send as _smtp_send  # noqa: E402

try:
    from notify import notify as _telegram_notify  # noqa: F401
except ImportError:
    def _telegram_notify(*_a: Any, **_kw: Any) -> bool:  # type: ignore[misc]
        return False

try:
    from draft_critic import critique_draft  # noqa: F401
except ImportError:
    def critique_draft(*_a: Any, **_kw: Any) -> dict:  # type: ignore[misc]
        return {
            "verdict": "reject",
            "reasons": ["draft_critic unavailable"],
            "notes": "draft_critic unavailable",
        }


# ---- Canonical constants ----------------------------------------------------

# Cooldown windows per channel. Manual operator overrides can still pass
# cooldown_hours=0 for a specific approved send, but the default path must
# protect against an agent repeatedly hitting the same lead.
DEFAULT_COOLDOWNS: dict[str, int] = {
    "email": 72,        # 3 days between cold emails to the same lead
    "sms": 24,          # 1 day between SMS to same lead (TT/Twilio shared)
    "instagram": 48,    # 2 days between DMs
    "phone": 168,       # 7 days between calls
    "skool": 24,        # 1 day — community is higher frequency
    "telegram": 0,      # internal, no cooldown
    # LinkedIn outreach removed 2026-04-25 — CC's directive: "no automation
    # for LinkedIn." Drafting CC LinkedIn messages by hand is fine; the
    # gateway will not auto-send them. send(channel="linkedin") now returns
    # status=error, reason="unknown channel 'linkedin'" as the hard guard.
}

# Global daily outbound caps. Prevents any single day becoming a firehose
# even if a bug slips through. Breach triggers fail-closed: gateway refuses.
DAILY_CAPS: dict[str, int] = {
    "email": 50,        # 50 outbound emails/day hard cap
    "sms": 30,          # 30 SMS/day per tenant (TT + Twilio combined)
    "instagram": 30,    # 30 DMs/day (IG is especially spam-sensitive)
    "phone": 15,        # 15 calls/day sanity bound
}

# Hourly caps protect the domain reputation from bursty sends even when the
# daily cap is still far away.
HOURLY_CAPS: dict[str, int] = {
    "email": 30,
    "sms": 10,           # 10 SMS/hour — drip-campaign step burst protection
    "instagram": 6,
    "phone": 3,
}

# Canonical agent_source tags — whoever is calling MUST identify itself.
# Free-form strings allowed, but staying on these values keeps audits sane.
KNOWN_AGENT_SOURCES: frozenset[str] = frozenset({
    "outreach_engine",
    "funnel_nurture",
    "email_engine",
    "booking_engine",
    "instagram_engine",
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
    "conaugh_mckenna": {
        "business_name": "Conaugh McKenna",
        "sender_name": "CC (Conaugh McKenna)",
        "business_address": "Conaugh McKenna, Collingwood, ON, Canada",
        "from_display": "Conaugh McKenna",
    },
    "nostalgic": {
        "business_name": "Nostalgic Requests",
        "sender_name": "Conaugh McKenna",
        "business_address": "Nostalgic Requests, Collingwood, ON, Canada",
        "from_display": "Nostalgic Requests",
    },
}

DEFAULT_BRAND = "oasis"
RESERVATION_WINDOW_MINUTES = 30
DAILY_ALERT_THRESHOLD = 0.8
_DAILY_CAP_ALERTS_SENT: set[str] = set()


# ---- Env + DB ---------------------------------------------------------------

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    env_vars: dict[str, str] = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_vars[k.strip()] = v.strip()
    # CI / VPS / systemd deployments inject credentials directly into the
    # process environment. Keep .env.agents as local-file override, but never
    # require the file to exist in hosted runtimes or tests.
    for k, v in os.environ.items():
        env_vars.setdefault(k, v)
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


# HTML body detection — chokepoint defense against malformed body_html.
# 2026-05-19: bridge-chat session passed body_html='true' (literal) and
# render_branded_html_fragment wrapped it as the email content. Validation
# at the gateway means every caller (CLI, sequence runner, n8n, future
# Command Center tools) is protected, not just one.
_HTML_TAG_RE = re.compile(r"<[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?/?>")


def _looks_like_html_body(s: Optional[str]) -> bool:
    """Conservative HTML detector — requires at least one well-formed tag."""
    if not s or len(s) < 4:
        return False
    return bool(_HTML_TAG_RE.search(s))


def _strip_html_tags(html: str) -> str:
    """Tag-strip + whitespace-normalize for the body_text fallback path."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _env_bool(env: dict[str, str], key: str, default: bool) -> bool:
    raw = (env.get(key) or os.environ.get(key) or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_int(env: dict[str, str], key: str, default: int) -> int:
    raw = (env.get(key) or os.environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_ratio(env: dict[str, str], key: str, default: float) -> float:
    raw = (env.get(key) or os.environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value > 1:
        value /= 100.0
    return max(0.0, min(1.0, value))


UNRESOLVED_TEMPLATE_TOKEN_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _find_unresolved_template_tokens(**fields: Optional[str]) -> list[str]:
    """Return unresolved template token names still present in message fields."""
    found: list[str] = []
    for field_name, value in fields.items():
        for token in UNRESOLVED_TEMPLATE_TOKEN_RE.findall(value or ""):
            name = token.strip()
            label = f"{field_name}:{name}"
            if label not in found:
                found.append(label)
    return found


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _json_sql_literal(value: Any) -> str:
    return _sql_literal(json.dumps(value or {}, separators=(",", ":"))) + "::jsonb"


def _extract_domain(to_email: Optional[str]) -> Optional[str]:
    normalized = (to_email or "").strip().lower()
    if "@" not in normalized:
        return None
    _, _, domain = normalized.rpartition("@")
    return domain or None


def _count_window(db: Any, channel: str, window_start: datetime) -> int:
    rows = (
        db.table("lead_interactions")
        .select("id", count="exact")
        .eq("channel", channel)
        .gte("created_at", window_start.isoformat())
        .execute()
    )
    return rows.count or 0


def _daily_alert_key(channel: str, day_start: datetime) -> str:
    return f"{day_start.date().isoformat()}:{channel}"


def _maybe_notify_daily_cap_threshold(channel: str, count: int, cap: Optional[int]) -> None:
    if cap is None or cap <= 0:
        return
    threshold = max(1, math.ceil(cap * DAILY_ALERT_THRESHOLD))
    if count < threshold:
        return
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    key = _daily_alert_key(channel, day_start)
    if key in _DAILY_CAP_ALERTS_SENT:
        return
    _DAILY_CAP_ALERTS_SENT.add(key)
    try:
        _telegram_notify(
            f"{channel} outbound is at {count}/{cap} today. "
            "Gateway is still open, but you're inside the red zone.",
            category="outreach",
        )
    except Exception:  # noqa: BLE001
        pass


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


def _has_prior_sms_sent(db: Any, lead_id: Optional[str]) -> bool:
    """Return True when this lead already has a completed outbound SMS row.

    On ledger read errors, assume this is a first touch so the compliance
    footer is appended. Extra STOP language is safer than omitting it.
    """
    if not lead_id:
        return False
    try:
        rows = (
            db.table("lead_interactions")
            .select("id", count="exact")
            .eq("lead_id", lead_id)
            .eq("type", "sms_sent")
            .limit(1)
            .execute()
        )
        return bool((rows.count or 0) > 0 or rows.data)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[send_gateway] prior SMS query warning: {exc}; "
            "assuming first SMS for opt-out language.",
            file=sys.stderr,
        )
        return False


def get_bounce_rate(db, last_n_hours: int = 24) -> float:
    """Return failed/total for recent email sends.

    A minimum sample size is enforced so the gateway does not overreact to a
    tiny denominator early in the day.
    """
    stats = _get_bounce_window_stats(db, last_n_hours=last_n_hours)
    return stats["rate"]


def _get_bounce_window_stats(db, last_n_hours: int = 24) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=last_n_hours)
    env = load_env()
    minimum_sample = _env_int(env, "BOUNCE_MIN_SAMPLE_SIZE", 20)
    try:
        rows = (
            db.table("email_log")
            .select("status, sent_at")
            .gte("sent_at", window_start.isoformat())
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] bounce-rate query warning: {exc}", file=sys.stderr)
        return {"rate": 0.0, "failed": 0, "total": 0, "minimum_sample": minimum_sample}

    total = 0
    failed = 0
    for row in rows or []:
        status = (row.get("status") or "").strip().lower()
        if status not in {"sent", "failed"}:
            continue
        total += 1
        if status == "failed":
            failed += 1
    rate = (failed / total) if total >= minimum_sample and total > 0 else 0.0
    return {"rate": rate, "failed": failed, "total": total, "minimum_sample": minimum_sample}


def can_act_domain(
    db: Any,
    to_email: Optional[str],
    channel: str = "email",
    last_n_hours: int = 24,
) -> dict[str, Any]:
    """Enforce a domain-level cap so ten teammates at one company do not all
    get hit inside the same day."""
    env = load_env()
    cap = _env_int(env, "DOMAIN_DAILY_CAP", 3)
    domain = _extract_domain(to_email)
    if not domain or cap <= 0:
        return {"allowed": True, "reason": "ok", "domain": domain, "count": 0, "cap": cap}

    window_start = datetime.now(timezone.utc) - timedelta(hours=last_n_hours)
    try:
        leads = db.table("leads").select("id, email").execute().data or []
        lead_ids = {
            row.get("id")
            for row in leads
            if row.get("id") and (row.get("email") or "").strip().lower().endswith("@" + domain)
        }
        if not lead_ids:
            return {"allowed": True, "reason": "ok", "domain": domain, "count": 0, "cap": cap}

        recent = (
            db.table("lead_interactions")
            .select("lead_id, channel, created_at")
            .eq("channel", channel)
            .gte("created_at", window_start.isoformat())
            .execute()
            .data
        ) or []
        count = sum(1 for row in recent if row.get("lead_id") in lead_ids)
        if count >= cap:
            return {
                "allowed": False,
                "reason": f"domain cap hit: {count}/{cap} {channel} actions to @{domain} in the last 24h",
                "domain": domain,
                "count": count,
                "cap": cap,
            }
        return {"allowed": True, "reason": "ok", "domain": domain, "count": count, "cap": cap}
    except Exception as exc:  # noqa: BLE001
        print(
            f"[send_gateway] domain-cap query failed: {exc}; "
            "blocking send because the domain ledger is unavailable.",
            file=sys.stderr,
        )
        return {
            "allowed": False,
            "reason": f"domain cap ledger unavailable: {exc}",
            "domain": domain,
            "count": 0,
            "cap": cap,
        }


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

    env = load_env()
    result: dict[str, Any] = {
        "allowed": True,
        "reason": "ok",
        "last_action_at": None,
        "cooldown_until": None,
        "daily_count": 0,
        "daily_cap": DAILY_CAPS.get(channel),
        "hourly_count": 0,
        "hourly_cap": HOURLY_CAPS.get(channel),
        "domain_count": 0,
        "domain_cap": _env_int(env, "DOMAIN_DAILY_CAP", 3),
        "bounce_rate": 0.0,
    }

    # Gate 1: bounce-rate circuit breaker.
    try:
        bounce_stats = _get_bounce_window_stats(db, last_n_hours=24)
        result["bounce_rate"] = bounce_stats["rate"]
        bounce_threshold = _env_ratio(env, "BOUNCE_RATE_THRESHOLD", 0.03)
        if bounce_stats["total"] >= bounce_stats["minimum_sample"] and bounce_stats["rate"] > bounce_threshold:
            result.update(
                allowed=False,
                reason=(
                    "bounce-rate circuit breaker active: "
                    f"{bounce_stats['failed']}/{bounce_stats['total']} "
                    f"({bounce_stats['rate']:.1%}) over the last 24h"
                ),
            )
            return result
    except Exception as exc:  # noqa: BLE001
        result.update(allowed=False, reason=f"bounce-rate check failed: {exc}")
        return result

    # Gate 2: empty email (commercial intent will catch suppression separately).
    if to_email is not None and not (to_email or "").strip():
        result.update(allowed=False, reason="empty recipient")
        return result

    # Gate 3: active cooldown on this lead+channel.
    if lead_id:
        last = None
        try:
            rows = (
                db.table("lead_interactions")
                .select("created_at, cooldown_until, type")
                .eq("lead_id", lead_id)
                .eq("channel", channel)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
                .data
            )
        except Exception as exc:  # noqa: BLE001
            # Likely the migration 003 columns do not exist yet. Fall back to
            # querying without cooldown_until so the engine still functions.
            try:
                rows = (
                    db.table("lead_interactions")
                    .select("created_at, type")
                    .eq("lead_id", lead_id)
                    .eq("channel", channel)
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                    .data
                )
                for r in rows or []:
                    r["cooldown_until"] = None
            except Exception as exc2:  # noqa: BLE001
                print(
                    f"[send_gateway] can_act cooldown query failed: {exc2}; "
                    "blocking send because the interaction ledger is unavailable.",
                    file=sys.stderr,
                )
                result.update(
                    allowed=False,
                    reason=f"cooldown ledger unavailable: {exc2}",
                )
                return result

        if rows:
            for candidate in rows:
                ctype = (candidate.get("type") or "").strip().lower()
                if ctype == f"{channel}_failed" or ctype == "email_failed":
                    continue
                if ctype == "reserving":
                    result.update(allowed=False, reason="concurrent send detected")
                    return result
                last = candidate
                break
        if rows and last:
            result["last_action_at"] = last.get("created_at")
            cu_raw = last.get("cooldown_until")
            effective_window = (
                cooldown_hours
                if cooldown_hours is not None
                else DEFAULT_COOLDOWNS.get(channel, 0)
            )
            if cu_raw and effective_window > 0:
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

    # Gate 3b: hourly cap.
    hourly_cap = HOURLY_CAPS.get(channel)
    if hourly_cap is not None:
        try:
            count = _count_window(db, channel, now - timedelta(hours=1))
            result["hourly_count"] = count
            if count >= hourly_cap:
                result.update(
                    allowed=False,
                    reason=f"hourly cap hit: {count}/{hourly_cap} {channel} actions in the last hour",
                )
                return result
        except Exception as exc:  # noqa: BLE001
            result.update(allowed=False, reason=f"hourly cap ledger unavailable: {exc}")
            return result

    # Gate 4: daily cap.
    cap = DAILY_CAPS.get(channel)
    if cap is not None:
        try:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            count = _count_window(db, channel, day_start)
            result["daily_count"] = count
            _maybe_notify_daily_cap_threshold(channel, count, cap)
            if count >= cap:
                result.update(
                    allowed=False,
                    reason=f"daily cap hit: {count}/{cap} {channel} actions today",
                )
                return result
        except Exception as exc:  # noqa: BLE001
            print(
                f"[send_gateway] can_act daily-cap query failed: {exc}; "
                "blocking send because the interaction ledger is unavailable.",
                file=sys.stderr,
            )
            result.update(
                allowed=False,
                reason=f"daily cap ledger unavailable: {exc}",
            )
            return result

    # Gate 5: domain cap.
    domain_check = can_act_domain(db=db, to_email=to_email, channel=channel)
    result["domain_count"] = domain_check.get("count", 0)
    result["domain_cap"] = domain_check.get("cap")
    if not domain_check["allowed"]:
        result.update(allowed=False, reason=domain_check["reason"])
        return result

    return result


# ---- Logging ----------------------------------------------------------------

def _emit_outbound_sent(lead_id: Optional[str], channel: str,
                        interaction_id: Optional[str], intent: str,
                        brand: Optional[str] = None) -> None:
    """V6 BUILD 3 — broadcast a successful send to the cross-agent event bus.

    Fire-and-forget. Wrapped in try/except so a bus outage NEVER affects the
    return value of send(). Lazy-imports event_bus to avoid forcing the
    supabase client load on every send_gateway import (it's heavyweight,
    and some callers — like tests with mocked db — don't want it).

    Idempotency: keyed on interaction_id so a retry of the same send (which
    shouldn't happen given the reservation gate, but defense in depth) is
    a no-op at the bus level.
    """
    if not interaction_id:
        return  # no canonical id → no idempotency anchor → skip
    try:
        # Lazy import: event_bus pulls supabase client; defer until we
        # actually have a sent message to broadcast.
        from event_bus import publish as _bus_publish  # type: ignore[import-not-found]
        _bus_publish(
            "BRAVO_OUTBOUND_SENT",
            {
                "lead_id": lead_id,
                "channel": channel,
                "interaction_id": interaction_id,
                "intent": intent,
                "brand": brand,
            },
            source="bravo",
            target=None,  # broadcast — Atlas (CFO spend gates), Maven (CMO
                           # attribution), Aura (life-context awareness) may
                           # all care about outbound activity
            correlation_id=interaction_id,
            idempotency_key=f"outbound_sent:{interaction_id}",
        )
    except Exception:
        # send_gateway is the V5.6 outbound chokepoint — the bus emit is
        # strictly best-effort and MUST NOT alter the gateway's contract.
        pass


def _mirror_email_log(
    db: Any,
    *,
    to_email: Optional[str],
    subject: Optional[str],
    content_preview: Optional[str],
    status: str,
    lead_id: Optional[str],
    error_message: Optional[str] = None,
) -> None:
    try:
        payload = {
            "to_email": to_email,
            "subject": subject or "",
            "body_preview": (content_preview or "")[:200],
            "status": status,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "lead_id": lead_id,
        }
        if error_message:
            payload["error_message"] = error_message
        db.table("email_log").insert(payload).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] email_log mirror warning: {exc}", file=sys.stderr)


def _touch_lead_last_contact(db: Any, lead_id: Optional[str], action_type: str) -> None:
    if lead_id and action_type in {"email_sent", "dm_sent", "call"}:
        try:
            now = datetime.now(timezone.utc).isoformat()
            db.table("leads").update({
                "last_contacted_at": now,
                "updated_at": now,
            }).eq("id", lead_id).execute()
        except Exception as exc:  # noqa: BLE001
            print(f"[send_gateway] leads.last_contacted_at update warning: {exc}", file=sys.stderr)


def _resolve_tenant_for_lead(db: Any, lead_id: Optional[str]) -> Optional[str]:
    """Look up the tenant for a lead so the new lead_interactions row carries
    tenant_id. Without this, the dashboard's tenant-filtered Pipeline +
    Operations Activity Tape miss every recent send (they fall back to older
    backfill rows that still have tenant_id stamped). Returns None on miss
    so callers can write tenant-less rows as a degraded fallback."""
    if not lead_id:
        return None
    try:
        r = db.table("leads").select("tenant_id").eq("id", lead_id).limit(1).execute()
        if r.data and r.data[0].get("tenant_id"):
            return str(r.data[0]["tenant_id"])
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] tenant lookup warning: {exc}", file=sys.stderr)
    return None


def _writethrough_outbound_log(
    *,
    lead_id: Optional[str],
    to_email: Optional[str],
    subject: Optional[str],
    content_preview: Optional[str],
    action_type: str,
    channel: str,
    agent_source: str,
    metadata: Optional[dict[str, Any]],
    existing_interaction_id: Optional[str] = None,
) -> None:
    """Best-effort POST to /api/outbound/log so the dashboard sees the send +
    the Operations Activity Tape gets an outbound.sent event. Skips silently
    when env vars aren't configured. Never raises — caller is the send loop.

    Only fires for confirmed sends (`*_sent` action types). Blocked / queued
    / dry_run land here as no-ops because we don't want to pollute the tape
    with non-sends.

    `existing_interaction_id` dedupes against the local insert: the RPC
    stamps tenant + publishes agent_events but does NOT insert a second
    lead_interactions row. Always pass this when called from log_action /
    finalize_reserved_action — they already wrote the row.
    """
    if not action_type.endswith("_sent"):
        return
    if not to_email:
        return
    try:
        # Lazy import — avoids circular costs if the module is unused
        from _outbound_log_post import post_outbound_log  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] outbound write-back import warning: {exc}", file=sys.stderr)
        return
    ok, _interaction_id, err = post_outbound_log(
        to_email=to_email,
        subject=subject or "",
        body_preview=content_preview or "",
        lead_id=lead_id,
        status="sent",
        channel=channel,
        agent_source=agent_source,
        metadata=metadata or {},
        existing_interaction_id=existing_interaction_id,
    )
    if not ok and err and err != "missing_env":
        print(f"[send_gateway] outbound write-back failed: {err}", file=sys.stderr)


def _update_interaction_row(db: Any, interaction_id: str, payload: dict[str, Any]) -> bool:
    try:
        db.table("lead_interactions").update(payload).eq("id", interaction_id).execute()
        return True
    except Exception:
        reduced = {
            k: v for k, v in payload.items()
            if k not in {"cooldown_until", "agent_source", "metadata"}
        }
        try:
            db.table("lead_interactions").update(reduced).eq("id", interaction_id).execute()
            return True
        except Exception as exc2:  # noqa: BLE001
            print(f"[send_gateway] lead_interactions update failed: {exc2}", file=sys.stderr)
            return False


def _try_reserve_slot_via_rpc(
    db: Any,
    *,
    lead_id: str,
    channel: str,
    subject: Optional[str],
    content_preview: Optional[str],
    agent_source: str,
    cooldown_hours: Optional[int],
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cooldown_until = (
        (now + timedelta(hours=cooldown_hours)).isoformat()
        if cooldown_hours and cooldown_hours > 0 else None
    )
    reservation_metadata = dict(metadata or {})
    reservation_metadata.update({
        "reservation_status": "pending",
        "reserved_at": now.isoformat(),
    })
    marker = {
        "lead_id": lead_id,
        "channel": channel,
        "subject": (subject or "")[:500],
        "content_preview": (content_preview or "")[:1000],
        "agent_source": agent_source,
        "cooldown_until": cooldown_until,
        "metadata": reservation_metadata,
    }
    sql = (
        f"/* send_gateway_reserve:{json.dumps(marker, separators=(',', ':'))} */ "
        "WITH guard AS ("
        f"  SELECT pg_try_advisory_xact_lock(hashtext({_sql_literal(lead_id + '|' + channel)})) AS acquired"
        "), existing AS ("
        "  SELECT id FROM lead_interactions"
        f"  WHERE lead_id = {_sql_literal(lead_id)}"
        f"    AND channel = {_sql_literal(channel)}"
        "    AND type = 'reserving'"
        f"    AND created_at >= NOW() - INTERVAL '{RESERVATION_WINDOW_MINUTES} minutes'"
        "  ORDER BY created_at DESC"
        "  LIMIT 1"
        "), inserted AS ("
        "  INSERT INTO lead_interactions (lead_id, type, channel, created_at, subject, content, agent_source, cooldown_until, metadata)"
        "  SELECT "
        f"    {_sql_literal(lead_id)},"
        "    'reserving',"
        f"    {_sql_literal(channel)},"
        "    NOW(),"
        f"    {_sql_literal((subject or '')[:500])},"
        f"    {_sql_literal((content_preview or '')[:1000])},"
        f"    {_sql_literal(agent_source)},"
        f"    {_sql_literal(cooldown_until)},"
        f"    {_json_sql_literal(reservation_metadata)} "
        "  FROM guard"
        "  WHERE acquired AND NOT EXISTS (SELECT 1 FROM existing)"
        "  RETURNING id, created_at"
        ") "
        "SELECT "
        "  COALESCE((SELECT acquired FROM guard), false) AS lock_acquired, "
        "  (SELECT id FROM existing LIMIT 1) AS existing_reservation_id, "
        "  (SELECT id FROM inserted LIMIT 1) AS reservation_id, "
        "  (SELECT created_at FROM inserted LIMIT 1) AS reservation_created_at"
    )
    res = db.rpc("exec_sql", {"sql_query": sql}).execute()
    data = getattr(res, "data", None)
    if isinstance(data, dict):
        rows = data.get("rows") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    row = rows[0] if rows else {}
    if not row.get("lock_acquired", True):
        return {"status": "blocked", "reason": "concurrent send detected"}
    if row.get("existing_reservation_id"):
        return {"status": "blocked", "reason": "concurrent send detected"}
    if row.get("reservation_id"):
        return {"status": "reserved", "reservation_id": row["reservation_id"], "mode": "rpc"}
    return {"status": "error", "reason": "reservation RPC returned no reservation_id"}


def reserve_send_slot(
    db: Any,
    *,
    lead_id: Optional[str],
    channel: str,
    subject: Optional[str],
    content_preview: Optional[str],
    agent_source: str,
    cooldown_hours: Optional[int],
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    reservation_metadata = dict(metadata or {})
    reservation_metadata.update({
        "reservation_status": "pending",
        "reserved_at": datetime.now(timezone.utc).isoformat(),
    })
    if lead_id and hasattr(db, "rpc"):
        try:
            return _try_reserve_slot_via_rpc(
                db,
                lead_id=lead_id,
                channel=channel,
                subject=subject,
                content_preview=content_preview,
                agent_source=agent_source,
                cooldown_hours=cooldown_hours,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[send_gateway] reservation RPC unavailable: {exc}", file=sys.stderr)

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "type": "reserving",
        "channel": channel,
        "created_at": now.isoformat(),
        "subject": (subject or "")[:500],
        "content": (content_preview or "")[:1000],
        "agent_source": agent_source,
        "metadata": reservation_metadata,
    }
    if lead_id:
        payload["lead_id"] = lead_id
    if cooldown_hours and cooldown_hours > 0:
        payload["cooldown_until"] = (now + timedelta(hours=cooldown_hours)).isoformat()
    try:
        res = db.table("lead_interactions").insert(payload).execute()
        reservation_id = res.data[0].get("id") if res.data else None
        return {"status": "reserved", "reservation_id": reservation_id, "mode": "fallback"}
    except Exception:
        reduced = {
            k: v for k, v in payload.items()
            if k not in {"cooldown_until", "agent_source", "metadata"}
        }
        try:
            res = db.table("lead_interactions").insert(reduced).execute()
            reservation_id = res.data[0].get("id") if res.data else None
            return {"status": "reserved", "reservation_id": reservation_id, "mode": "fallback_legacy"}
        except Exception as exc2:  # noqa: BLE001
            return {"status": "error", "reason": f"reservation failed: {exc2}"}


def finalize_reserved_action(
    db: Any,
    *,
    interaction_id: Optional[str],
    lead_id: Optional[str],
    channel: str,
    action_type: str,
    subject: Optional[str],
    content_preview: Optional[str],
    agent_source: str,
    cooldown_hours: Optional[int],
    metadata: Optional[dict[str, Any]] = None,
    to_email: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[str]:
    if not interaction_id:
        return log_action(
            db=db,
            lead_id=lead_id,
            channel=channel,
            action_type=action_type,
            subject=subject,
            content_preview=content_preview,
            agent_source=agent_source,
            cooldown_hours=cooldown_hours,
            metadata=metadata,
            to_email=to_email,
        )

    now = datetime.now(timezone.utc)
    final_metadata = dict(metadata or {})
    final_metadata["reservation_status"] = "completed" if action_type.endswith("_sent") else "failed"
    if error_message:
        final_metadata["error_message"] = error_message
    payload: dict[str, Any] = {
        "type": action_type,
        "subject": (subject or "")[:500],
        "content": (content_preview or "")[:1000],
        "agent_source": agent_source,
        "metadata": final_metadata,
    }
    # Stamp tenant_id on the reservation row at finalize time so the dashboard
    # sees the completed send. Reservations are created tenant-less (the
    # pre-send code path doesn't have a lead lookup); finalize is the right
    # spot to attach tenant.
    tenant_id = _resolve_tenant_for_lead(db, lead_id)
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if action_type.endswith("_sent") and cooldown_hours and cooldown_hours > 0:
        payload["cooldown_until"] = (now + timedelta(hours=cooldown_hours)).isoformat()
    else:
        payload["cooldown_until"] = None
    ok = _update_interaction_row(db, interaction_id, payload)
    if not ok:
        return None
    if channel == "email":
        _mirror_email_log(
            db,
            to_email=to_email,
            subject=subject,
            content_preview=content_preview,
            status="sent" if action_type == "email_sent" else "failed",
            lead_id=lead_id,
            error_message=error_message,
        )
    if action_type.endswith("_sent"):
        _touch_lead_last_contact(db, lead_id, action_type)

    # Dashboard write-through (same as log_action). Pass interaction_id
    # so the RPC dedupes — finalize_reserved_action just updated the
    # existing reservation row, no need for the RPC to insert another.
    _writethrough_outbound_log(
        lead_id=lead_id,
        to_email=to_email,
        subject=subject,
        content_preview=content_preview,
        action_type=action_type,
        channel=channel,
        agent_source=agent_source,
        metadata=metadata,
        existing_interaction_id=interaction_id,
    )
    return interaction_id

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

    # Stamp tenant_id from the lead so the dashboard's tenant-filtered
    # Pipeline + Operations queries see this row. Without this, recent
    # sends are invisible (pre-fix: rows landed with tenant_id=NULL,
    # so the UI fell back to older tenant-tagged backfill rows that
    # made "Recent Outbound" appear stale).
    tenant_id = _resolve_tenant_for_lead(db, lead_id)
    if tenant_id:
        row["tenant_id"] = tenant_id

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
        _mirror_email_log(
            db,
            to_email=to_email,
            subject=subject,
            content_preview=content_preview,
            status="sent" if action_type == "email_sent" else "received",
            lead_id=lead_id,
        )

    # Update leads.last_contacted_at so the CRM view stays fresh.
    _touch_lead_last_contact(db, lead_id, action_type)

    # Dashboard write-through: publish outbound.sent to agent_events so the
    # Operations Activity Tape lights up. Best-effort; no-ops if env vars
    # aren't configured. Pass interaction_id so the RPC dedupes against
    # the local insert above (no duplicate Pipeline rows).
    _writethrough_outbound_log(
        lead_id=lead_id,
        to_email=to_email,
        subject=subject,
        content_preview=content_preview,
        action_type=action_type,
        channel=channel,
        agent_source=agent_source,
        metadata=metadata,
        existing_interaction_id=interaction_id,
    )

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
    result: dict[str, Any] = {
        "date": day_start.date().isoformat(),
        "channels": {},
        "hourly_counts": {},
        "bounce_rate": get_bounce_rate(db),
    }
    channels = [channel] if channel else list(KNOWN_CHANNELS)
    for c in channels:
        try:
            r_count = _count_window(db, c, day_start)
            result["channels"][c] = {
                "count": r_count,
                "cap": DAILY_CAPS.get(c),
            }
        except Exception as exc:  # noqa: BLE001
            result["channels"][c] = {"count": None, "cap": DAILY_CAPS.get(c), "error": str(exc)}
        try:
            result["hourly_counts"][c] = {
                "count": _count_window(db, c, now - timedelta(hours=1)),
                "cap": HOURLY_CAPS.get(c),
            }
        except Exception as exc:  # noqa: BLE001
            result["hourly_counts"][c] = {"count": None, "cap": HOURLY_CAPS.get(c), "error": str(exc)}
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
    # Explicit charset="utf-8" prevents edge-case mojibake on Windows
    # where Python's auto-detect can pick the wrong encoding for
    # characters like em dash (U+2014). See 2026-05-13 incident.
    body_alt = MIMEMultipart("alternative")
    body_alt.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        body_alt.attach(MIMEText(body_html, "html", "utf-8"))
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


def _send_sms_via_provider(
    *,
    env: dict[str, str],
    provider: str,
    to_phone: str,
    body_text: str,
    brand: str,
) -> tuple[bool, Optional[str], dict]:
    """Physical SMS send. Dispatches to TextTorrent or Twilio based on
    `provider`. Returns (ok, error_message, metadata).

    Metadata is what the gateway folds into the lead_interactions row
    so operators can audit provider + message ID + send timestamp from
    one place. Phase 5.3 of the SunBiz CRM build (2026-05-15).

    Why inline (vs subprocess to text_torrent_tool.py / a twilio
    wrapper): send_gateway is called from autonomous code paths
    (sequence_runner.py drip engine, future agent tool calls). A
    subprocess hop per send is ~150ms of forking + Python init, on
    top of the actual HTTP call. Inline keeps the send synchronous
    + cheap, matching the email path's _send_email_smtp pattern.
    """
    if provider not in ("texttorrent", "twilio"):
        return False, f"unknown SMS provider '{provider}' (expected 'texttorrent' or 'twilio')", {}

    try:
        import requests as _requests
    except ImportError:
        return False, "'requests' package not installed (pip install requests)", {}

    if provider == "texttorrent":
        api_key = (env.get("TEXTTORRENT_API_KEY") or "").strip()
        if not api_key:
            return False, "TEXTTORRENT_API_KEY missing — set it in the agents env file", {}
        api_url = (
            env.get("TEXTTORRENT_API_URL") or "https://api.texttorrent.com/v1"
        ).rstrip("/")
        try:
            r = _requests.post(
                f"{api_url}/messages",
                headers={
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                    "user-agent": "oasis-bravo/send-gateway/1.0",
                },
                json={"to": to_phone, "message": body_text},
                timeout=30,
            )
        except _requests.RequestException as e:
            return False, f"network error contacting TT: {e}", {}
        if r.status_code >= 400:
            try:
                err = r.json()
            except ValueError:
                err = r.text[:400]
            return False, f"TT HTTP {r.status_code}: {err}", {}
        try:
            data = r.json()
        except ValueError:
            data = {}
        return True, None, {
            "provider_message_id": data.get("id") or data.get("message_id"),
        }

    # Twilio path. Twilio's REST API is dead simple: POST to
    # api.twilio.com/2010-04-01/Accounts/<sid>/Messages.json with
    # basic auth (sid + auth token). We don't need the Twilio SDK
    # for this single call.
    sid = (env.get("TWILIO_ACCOUNT_SID") or "").strip()
    token = (env.get("TWILIO_AUTH_TOKEN") or "").strip()
    # Per-brand phone-number selection (CC has multi-brand setup —
    # oasis / nostalgic / conaugh_mckenna). Operators set
    # TWILIO_FROM_NUMBER_OASIS, TWILIO_FROM_NUMBER_NOSTALGIC, etc.,
    # plus a default TWILIO_FROM_NUMBER for back-compat. Brand-specific
    # number is checked first; falls back to the default so existing
    # single-brand operators keep working without an env tweak.
    brand_upper = (brand or "").upper().replace("-", "_")
    from_number = (
        env.get(f"TWILIO_FROM_NUMBER_{brand_upper}")
        or env.get("TWILIO_FROM_NUMBER")
        or env.get("TWILIO_PHONE_NUMBER")
        or ""
    ).strip()
    if not sid or not token:
        return False, "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN required in the agents env file", {}
    if not from_number:
        return False, (
            f"no Twilio from-number for brand '{brand}'. Set "
            f"TWILIO_FROM_NUMBER_{brand_upper} or a default TWILIO_FROM_NUMBER."
        ), {}
    try:
        r = _requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"To": to_phone, "From": from_number, "Body": body_text},
            auth=(sid, token),
            timeout=30,
            headers={"user-agent": "oasis-bravo/send-gateway/1.0"},
        )
    except _requests.RequestException as e:
        return False, f"network error contacting Twilio: {e}", {}
    if r.status_code >= 400:
        try:
            err = r.json()
            err_msg = err.get("message") or err
        except ValueError:
            err_msg = r.text[:400]
        return False, f"Twilio HTTP {r.status_code}: {err_msg}", {}
    try:
        data = r.json()
    except ValueError:
        data = {}
    return True, None, {
        "provider_message_id": data.get("sid"),
        "twilio_status": data.get("status"),
    }


def _send_email_smtp(
    env: dict[str, str],
    mime: MIMEMultipart,
    to_email: str,
) -> tuple[bool, Optional[str]]:
    gmail_user = env.get("GMAIL_USER") or env.get("GMAIL_ADDRESS", "")
    gmail_pass = env.get("GMAIL_APP_PASSWORD", "")
    ok, err = _smtp_send(gmail_user, gmail_pass, mime, to_email)
    if ok:
        _ping_health("gws", status="healthy", metadata={"source": "send_gateway.smtp_send"})
    else:
        if "authentication" in (err or "").lower():
            _ping_health("gws", status="down", error="SMTP authentication failed")
        elif "recipient refused" in (err or "").lower():
            pass  # per-message issue, not service health
        else:
            _ping_health("gws", status="degraded", error=err or "unknown")
    return ok, err


def _ping_health(service: str, *, status: str = "healthy", error: Optional[str] = None, metadata: Optional[dict] = None) -> None:
    """Best-effort ping to integrations_health. Never raises."""
    try:
        from integration_health import ping
        ping(service, status=status, error=error, metadata=metadata or {})
    except Exception:
        pass  # Health pings must never break the send path


# ---- Public API -------------------------------------------------------------

def send(
    channel: str,
    agent_source: str,
    *,
    to_email: Optional[str] = None,
    to_phone: Optional[str] = None,    # SMS: E.164 phone (added Phase 5.3, SunBiz CRM)
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
    sms_provider: Optional[str] = None,  # "texttorrent" | "twilio" | None (auto, env-resolved)
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
    # body_html must contain HTML if provided. 2026-05-19 incident: a CLI
    # caller passed body_html='true' (literal string) and the brand template
    # wrapped that as the email body. Validation here is the chokepoint
    # defense for every caller, not just the CLI.
    if body_html is not None and body_html != "" and not _looks_like_html_body(body_html):
        return {"status": "error",
                "reason": f"body_html must contain HTML markup; got {body_html[:60]!r}",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # Auto-promote: if body_html is missing but body_text looks like HTML,
    # treat body_text as the HTML body. Catches the common caller mistake
    # of putting HTML in the text slot (same root cause as the validation
    # above, different shape). Keeps body_text populated with the
    # tag-stripped version so the suppression-list/cooldown/log paths
    # still get a clean text preview.
    if (body_html is None or body_html == "") and body_text and _looks_like_html_body(body_text):
        body_html = body_text
        body_text = _strip_html_tags(body_html)

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
    elif channel == "sms":
        # Phase 5.3 of SunBiz CRM — SMS now goes through the chokepoint
        # so cooldown / daily-cap / suppression apply uniformly with
        # email. Drip sequence runner (Phase 4) is the primary caller.
        if not to_phone or not body_text:
            return {"status": "error",
                    "reason": "sms channel requires to_phone (E.164) and body_text",
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}
        # Light E.164 sanity check — full validation is the provider's
        # job (they reject bad numbers with a clear error). Catching
        # the egregious cases here saves a round-trip.
        normalized_phone = to_phone.strip()
        if not normalized_phone.startswith("+") or len(normalized_phone) < 8:
            return {"status": "error",
                    "reason": f"sms to_phone must be E.164 starting with '+', got '{to_phone}'",
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

    # ---- Multi-AI safety killswitch (highest precedence) ----
    # BRAVO_FORCE_DRY_RUN=1 forces dry_run regardless of what the caller
    # passed. Set this in any environment where you don't fully trust the
    # invoking AI (low-capability models, IDE chat sandboxes, CI). It is
    # a HARD override and short-circuits BEFORE the gateway touches
    # Supabase, the suppression list, the cooldown ledger, the daily cap,
    # the bounce-rate breaker, the DNS doctor, or the draft critic.
    # Nothing can leak even if every downstream gate is unreachable.
    env = load_env()
    if _env_bool(env, "BRAVO_FORCE_DRY_RUN", False):
        return {"status": "dry_run",
                "reason": "BRAVO_FORCE_DRY_RUN=1 — killswitch engaged, no gates evaluated, no send",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- Resolve DB + lead ----
    try:
        db = db if db is not None else get_supabase(env)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": f"supabase unavailable: {exc}",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    lead_id = resolve_lead_id(db, to_email, lead_id)

    # ---- SMS STOP / DNC suppression ----
    # STOP is a channel-level opt-out. Once a phone is on the local DNC CSV,
    # no SMS intent should burn cooldown/reservation capacity or reach a
    # provider.
    if channel == "sms" and to_phone and should_suppress_phone(to_phone):
        return {"status": "suppressed",
                "reason": f"{to_phone} is on the SMS DNC list",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- Gate 1: commercial suppression ----
    if intent == "commercial" and to_email and should_suppress(to_email):
        return {"status": "suppressed",
                "reason": f"{to_email} is on CASL suppression list",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- First-touch SMS opt-out language ----
    # TCPA/CTIA expectation for commercial SMS: the first outbound message
    # must tell the recipient how to opt out. Do this before cooldown /
    # reservation so the ledger stores the exact body that gets dispatched.
    if (
        channel == "sms"
        and intent == "commercial"
        and body_text
        and "stop" not in body_text.lower()
        and not _has_prior_sms_sent(db, lead_id)
    ):
        body_text = body_text.rstrip() + "\n\nReply STOP to opt out."

    # ---- Gate 1a: reserved / placeholder domain rejection ----
    # 2026-04-27: Firecrawl scraped a lead with email=info@example.com from a
    # page template; SMTP accepted it but the address is RFC 2606 reserved
    # (test domain, no real mailbox). Belt-and-suspenders block at the gate
    # so manual sends, future scrapers, and any caller that misses scrape-
    # time validation can never ship to a placeholder domain.
    if to_email and is_reserved_domain(to_email):
        return {"status": "blocked",
                "reason": f"{to_email} is on a reserved/test domain "
                          f"(RFC 2606) — refusing send.",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- Gate 1b: HTML required for OASIS commercial sends ----
    # 2026-04-27 incident: opencode shipped 10 plain-text-only OASIS commercial
    # sends (no body_html → no booking link button, no branded signature, looks
    # like spam). Architectural rule: every OASIS commercial send MUST include
    # HTML. Transactional intent (booking confirmations / reminders) and other
    # brands (conaugh_mckenna, nostalgic) are exempt — short contextual sends and
    # non-OASIS brands don't need the marketing chrome. Tests can opt out by
    # passing intent="transactional" or providing body_html.
    if (channel == "email" and intent == "commercial" and brand == "oasis"
            and not (body_html and body_html.strip())):
        return {"status": "blocked",
                "reason": ("oasis commercial sends require body_html "
                           "(branded HTML + booking link). Use email_engine "
                           "send-template, or pass body_html explicitly."),
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}

    # ---- Gate 1c: unresolved template placeholder rejection ----
    # This is deliberately deterministic and independent of the AI critic.
    # The 2026-05-13 incident shipped `{{company}}` because the renderer left
    # missing variables in place and the critic gate had been made advisory.
    # No real email should ever leave with raw template tokens visible.
    if channel == "email":
        unresolved_tokens = _find_unresolved_template_tokens(
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        if unresolved_tokens:
            return {"status": "blocked",
                    "reason": ("unresolved template placeholder(s): "
                               f"{', '.join(unresolved_tokens[:10])}"),
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

    # ---- Gate 2 + 3: cooldown + daily cap (skipped for internal/transactional) ----
    if intent not in {"internal", "transactional"}:
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

        if intent == "commercial" and _env_bool(env, "DRAFT_CRITIC_ENABLED", True):
            # Fail-closed quality gate. Non-ship verdicts block. The only
            # optional fail-open path is an explicit operator env override for
            # critic unavailability, never for a real rejection.
            fail_open_unavailable = _env_bool(env, "DRAFT_CRITIC_FAIL_OPEN", False)
            try:
                critic_result = critique_draft(
                    draft_subject=subject,  # type: ignore[arg-type]
                    draft_body=body_text,  # type: ignore[arg-type]
                    brand=brand,
                    intent=intent,
                    env=env,
                )
            except Exception as critic_exc:  # noqa: BLE001
                if fail_open_unavailable:
                    print(
                        f"[send_gateway] draft_critic unavailable ({critic_exc})"
                        " — DRAFT_CRITIC_FAIL_OPEN=true, sending anyway.",
                        file=sys.stderr,
                    )
                    critic_result = {"verdict": "ship", "score": 0,
                                     "notes": f"critic unavailable: {critic_exc}"}
                else:
                    return {"status": "blocked",
                            "reason": f"draft_critic unavailable: {critic_exc}",
                            "lead_id": lead_id, "interaction_id": None,
                            "cooldown_until": None, "daily_count": None}
            verdict = critic_result.get("verdict")
            if verdict != "ship":
                reasons = critic_result.get("reasons") or []
                issues = critic_result.get("issues") or []
                reason_text = (
                    "; ".join(str(r) for r in reasons[:5])
                    or critic_result.get("notes")
                    or verdict
                    or "rejected"
                )
                issue_types = {
                    str(i.get("type") or "").strip()
                    for i in issues
                    if isinstance(i, dict)
                }
                critic_unavailable = (
                    ("draft_critic unavailable" in reason_text.lower()
                     or "critic failed" in reason_text.lower()
                     or "critic unavailable" in reason_text.lower())
                    and (not issue_types or issue_types == {"critic_unavailable"})
                )
                if fail_open_unavailable and critic_unavailable:
                    print(
                        f"[send_gateway] draft_critic unavailable ({reason_text})"
                        " — DRAFT_CRITIC_FAIL_OPEN=true, sending anyway.",
                        file=sys.stderr,
                    )
                else:
                    return {"status": "blocked",
                            "reason": f"draft_critic rejected: {reason_text}",
                            "lead_id": lead_id, "interaction_id": None,
                            "cooldown_until": None, "daily_count": None}

        reservation = reserve_send_slot(
            db=db,
            lead_id=lead_id,
            channel=channel,
            subject=subject,
            content_preview=body_text,
            agent_source=agent_source,
            cooldown_hours=effective_cooldown,
            metadata=full_metadata,
        )
        if reservation["status"] == "blocked":
            return {"status": "blocked",
                    "reason": reservation["reason"],
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}
        if reservation["status"] != "reserved":
            return {"status": "error",
                    "reason": reservation.get("reason", "reservation failed"),
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

        # Wrap in the OASIS branded shell so EVERY outbound surface
        # ships the same brand — INCLUDING internal sends. Three cases:
        #   1. body_html is None  →  wrap body_text in the shell
        #   2. body_html is a CONTENT FRAGMENT (no <!doctype>, no
        #      <html>) → it's a stored template's inner content;
        #      wrap it in the shell so the operator's templates also
        #      inherit the brand without rewriting every row.
        #   3. body_html is a COMPLETE DOCUMENT (<!doctype> / <html>)
        #      → respect the caller's choice and don't double-wrap.
        #
        # Internal vs commercial vs transactional only differ in CASL
        # footer (line 1233) + suppression checks (line 1416), NOT in
        # branding. The earlier `if intent != "internal"` guard here was
        # a real bug: a Gemini-Flash-driven test send on 2026-05-10
        # passed intent="internal" (reasonable LLM interpretation of
        # "test email") and arrived as bare plaintext, breaking CC's
        # "every surface ships the brand" invariant. Removed the guard.
        # If a future caller genuinely needs unbranded output, they
        # should pass body_html as a complete document (case 3 above).
        # Single source of truth: scripts/email_template.py.
        _is_full_doc = bool(
            body_html
            and (
                "<!doctype" in body_html.lower()[:40]
                or "<html" in body_html.lower()[:200]
            )
        )
        if not _is_full_doc:
            try:
                _here = os.path.dirname(os.path.abspath(__file__))
                if _here not in sys.path:
                    sys.path.insert(0, _here)
                from email_template import (  # type: ignore
                    render_branded_html,
                    render_branded_html_fragment,
                )
                if body_html:
                    # Templates pass formatted HTML content (e.g.
                    # `<p>Hi {{name}}</p>`). Wrap that fragment in
                    # the shell so the body retains its formatting
                    # but inherits the OASIS chrome.
                    body_html = render_branded_html_fragment(
                        body_html,
                        subject=subject,
                        show_booking=False,
                    )
                else:
                    # Plaintext-only path (cold outreach, agent
                    # one-off sends, internal verification mails):
                    # wrap the text body so it ships branded.
                    body_html = render_branded_html(
                        body_text or "",
                        subject=subject,
                        show_booking=False,
                    )
            except Exception:
                # Template missing or borked — keep whatever the
                # caller passed (plaintext if None, original HTML
                # if they supplied one).
                pass

        # ----------------------------------------------------------------
        # Email-open tracking pixel (Phase 19, 2026-05-17)
        # ----------------------------------------------------------------
        # Inject a 1x1 transparent tracking pixel into the HTML body whose
        # GET hit lands in /api/track/open/<reservation_id>. The route
        # writes one email_open_events row per hit + emits
        # BRAVO_EMAIL_OPENED on the event bus so sequence_runner can
        # fast-forward an on-open follow-up step. Skipped for internal
        # sends + when body_html is None (plain-text-only).
        #
        # Tracking ID is the reservation_id we already created above. It
        # is a uuid, tenant-scoped, and lives in send_gateway's
        # interactions table so the API route can resolve tenant_id +
        # lead_id by lookup without trusting the URL parameter.
        if intent != "internal" and body_html and reservation.get("reservation_id"):
            try:
                pixel_base = (
                    os.environ.get("EMAIL_TRACKING_BASE_URL")
                    or os.environ.get("DASHBOARD_BASE_URL")
                    or "https://agent-dashboard-cc90210.vercel.app"
                ).rstrip("/")
                pixel = (
                    f'<img src="{pixel_base}/api/track/open/{reservation["reservation_id"]}" '
                    'width="1" height="1" alt="" '
                    'style="display:none;border:0;outline:none;text-decoration:none;" />'
                )
                # Inject just before </body> if present, else append.
                if "</body>" in body_html.lower():
                    # case-insensitive replace of first </body>
                    idx = body_html.lower().rfind("</body>")
                    body_html = body_html[:idx] + pixel + body_html[idx:]
                else:
                    body_html = body_html + pixel
            except Exception as _e:
                # Tracking is best-effort — never block a send because
                # pixel injection hit an edge case.
                pass

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
            finalize_reserved_action(
                db=db,
                interaction_id=reservation.get("reservation_id"),
                lead_id=lead_id,
                channel=channel,
                action_type="email_failed",
                subject=subject,
                content_preview=body_text,
                agent_source=agent_source,
                cooldown_hours=None,
                metadata=full_metadata,
                to_email=to_email,
                error_message=err,
            )
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
        interaction_id = finalize_reserved_action(
            db=db,
            interaction_id=reservation.get("reservation_id"),
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
        # V6 BUILD 3 — broadcast to the cross-agent event bus AFTER the
        # send + log have both succeeded. Never blocks; never raises; never
        # mutates the gateway's return value.
        _emit_outbound_sent(lead_id, channel, interaction_id, intent, brand)
        return {"status": "sent",
                "reason": "ok",
                "lead_id": lead_id,
                "interaction_id": interaction_id,
                "cooldown_until": (datetime.now(timezone.utc)
                                   + timedelta(hours=effective_cooldown)).isoformat()
                if effective_cooldown else None,
                "daily_count": None}

    # ---- SMS dispatch (Phase 5.3 of SunBiz CRM, reservation-pattern
    # fix per Codex adversarial review 2026-05-15) ----
    # SMS goes through the chokepoint inline (mirrors email) rather than
    # log-only (which is what instagram / phone / skool / telegram do).
    # The drip sequence runner calls this from autonomous code paths;
    # it can't perform the physical send itself without re-implementing
    # provider routing, retry, and credential loading.
    #
    # Codex flagged: the prior implementation skipped the reservation
    # idempotency pattern that email uses. Two concurrent send() calls
    # could both pass can_act + both dispatch + both log, double-spending
    # the cooldown budget without the ledger reflecting it. The
    # reservation-then-dispatch-then-finalize pattern fixes that:
    #   1. reserve_send_slot inserts a lead_interactions row in
    #      "reserving" state BEFORE provider dispatch (atomic claim)
    #   2. If reservation fails -> early return error (no double-claim)
    #   3. Provider dispatch
    #   4. finalize_reserved_action flips the reservation row to
    #      sms_sent / sms_failed AFTER provider response
    if channel == "sms":
        # to_phone is guaranteed non-None here by the per-channel
        # validation above. Type narrowing for the type checker.
        assert to_phone is not None and body_text is not None

        # Provider resolution — explicit beats env beats auto-detect.
        # Auto-detect: if only ONE of TT/Twilio has credentials, route
        # there. This prevents the silent-fail case where an operator
        # set up only TextTorrent but every send routes to Twilio +
        # fails because TWILIO_ACCOUNT_SID is unset.
        explicit = (sms_provider or "").lower() or (env.get("SMS_PROVIDER") or "").lower()
        if explicit in ("texttorrent", "twilio"):
            provider_choice = explicit
        else:
            has_twilio = bool((env.get("TWILIO_ACCOUNT_SID") or "").strip() and (env.get("TWILIO_AUTH_TOKEN") or "").strip())
            has_tt = bool((env.get("TEXTTORRENT_API_KEY") or "").strip())
            if has_twilio and not has_tt:
                provider_choice = "twilio"
            elif has_tt and not has_twilio:
                provider_choice = "texttorrent"
            elif has_twilio and has_tt:
                # Both configured -- default to twilio for back-compat
                # (Twilio was the only SMS path pre-Phase 5). Operator
                # who wants TT-by-default sets SMS_PROVIDER=texttorrent.
                provider_choice = "twilio"
            else:
                return {"status": "error",
                        "reason": "sms channel needs either TWILIO_ACCOUNT_SID+TWILIO_AUTH_TOKEN or TEXTTORRENT_API_KEY configured in the agents env file",
                        "lead_id": lead_id, "interaction_id": None,
                        "cooldown_until": None, "daily_count": None}

        effective_cooldown = (
            cooldown_hours
            if cooldown_hours is not None
            else DEFAULT_COOLDOWNS.get(channel, 0)
        )
        full_metadata = dict(metadata or {})
        full_metadata.update({
            "brand": brand,
            "intent": intent,
            "sms_provider": provider_choice,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

        # ── 1. Reserve the slot BEFORE provider dispatch ──────────────
        # Atomic claim via reserve_send_slot. If two concurrent sends
        # race, only one wins the reservation; the other gets blocked
        # or errors at this gate, BEFORE the provider gets called.
        reservation = reserve_send_slot(
            db=db,
            lead_id=lead_id,
            channel=channel,
            subject=None,  # SMS has no subject
            content_preview=body_text,
            agent_source=agent_source,
            cooldown_hours=effective_cooldown,
            metadata=full_metadata,
        )
        if reservation["status"] == "blocked":
            return {"status": "blocked",
                    "reason": reservation["reason"],
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}
        if reservation["status"] != "reserved":
            return {"status": "error",
                    "reason": reservation.get("reason", "reservation failed"),
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

        # ── 2. Provider dispatch ──────────────────────────────────────
        ok, sms_err, sms_meta = _send_sms_via_provider(
            env=env,
            provider=provider_choice,
            to_phone=to_phone,
            body_text=body_text,
            brand=brand,
        )

        # ── 3. Finalize the reservation with sent or failed state ─────
        if not ok:
            finalize_reserved_action(
                db=db,
                interaction_id=reservation.get("reservation_id"),
                lead_id=lead_id,
                channel=channel,
                action_type="sms_failed",
                subject=None,
                content_preview=body_text,
                agent_source=agent_source,
                cooldown_hours=None,  # don't burn cooldown on a failed send
                metadata=full_metadata,
                to_email=None,
                error_message=sms_err,
            )
            return {"status": "error",
                    "reason": f"sms provider '{provider_choice}': {sms_err}",
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}

        full_metadata.update(sms_meta)
        interaction_id = finalize_reserved_action(
            db=db,
            interaction_id=reservation.get("reservation_id"),
            lead_id=lead_id,
            channel=channel,
            action_type="sms_sent",
            subject=None,
            content_preview=body_text,
            agent_source=agent_source,
            cooldown_hours=effective_cooldown,
            metadata=full_metadata,
            to_email=None,
        )
        _emit_outbound_sent(lead_id, channel, interaction_id, intent, brand)
        return {"status": "sent",
                "reason": f"sms via {provider_choice}",
                "lead_id": lead_id,
                "interaction_id": interaction_id,
                "cooldown_until": (datetime.now(timezone.utc)
                                   + timedelta(hours=effective_cooldown)).isoformat()
                if effective_cooldown else None,
                "daily_count": None}

    # Non-email channels are logged only — the real send happens in the
    # channel-specific engine (instagram_engine, etc.). The gateway still
    # enforces cooldown + cap BEFORE those engines act; they import
    # can_act() directly.
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
    # V6 BUILD 3 — broadcast to the cross-agent event bus AFTER the
    # log has succeeded. The non-email channel path logs only; the
    # physical send happens in the channel-specific engine. Emitting
    # here is still correct because the contract guarantees the log
    # happened — downstream subscribers care that send_gateway approved
    # the action, not which engine eventually delivered it.
    _emit_outbound_sent(lead_id, channel, interaction_id, intent, brand)
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
        print(f"Bounce rate (24h): {s['bounce_rate']:.1%}")
        print("Hourly counts:")
        for ch, d in s["hourly_counts"].items():
            cap = d.get("cap")
            cnt = d.get("count")
            print(f"  {ch:10}  {cnt}/{cap if cap is not None else '-'}")
        print(f"  TOTAL      {s['total']}")
    return 0


def _cmd_doctor(args) -> int:
    from dns_reputation import check_sender_reputation, format_reputation_report

    env = load_env()
    default_sender = env.get("GMAIL_USER") or env.get("GMAIL_ADDRESS") or ""
    domain = args.domain or _extract_domain(default_sender)
    report = check_sender_reputation(domain or "")
    if args.output_json:
        _print_json(report)
    else:
        print(format_reputation_report(report))
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

    pd = sub.add_parser("doctor", help="Check sender-domain SPF/DKIM/DMARC")
    pd.add_argument("--domain", default=None, help="Override sender domain")

    args = p.parse_args()

    if args.command == "send":
        sys.exit(_cmd_send(args))
    elif args.command == "can-act":
        sys.exit(_cmd_can_act(args))
    elif args.command == "history":
        sys.exit(_cmd_history(args))
    elif args.command == "stats":
        sys.exit(_cmd_stats(args))
    elif args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
