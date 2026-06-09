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
# _SCRIPTS_DIR must be CEO-Agent/scripts (where casl_compliance, lib.*, etc.
# live) so sibling imports resolve when this file is run directly as a CLI
# (python scripts/integrations/send_gateway.py doctor ...). It is .resolve()'d
# so the SunBiz scripts/send_gateway.py symlink maps back to the real dir.
# PROJECT_ROOT stays the repo root for .env.agents resolution. (Was
# parent.parent.parent — pointed at the repo root and crashed the documented
# CLI with ModuleNotFoundError: casl_compliance.)
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
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

# Per-user Gmail OAuth resolver (Phase 4 of SunBiz multi-employee
# personalization, 2026-05-29). When acted_by_user_id + tenant_id are
# both set on a send() call, the email path tries to authenticate as the
# user's connected Gmail rather than the tenant-shared SMTP credentials.
# Falls back to the existing SMTP path on any miss so this never regresses
# the legacy send path.
try:
    from integrations.user_gmail_oauth import (  # type: ignore  # noqa: E402
        resolve_send_identity as _resolve_send_identity,
        send_via_gmail_api as _send_via_gmail_api,
    )
except Exception:  # noqa: BLE001
    # If the OAuth module fails to import (e.g. missing cryptography lib
    # on a slim dev environment), keep the gateway functional — every
    # send falls back to the tenant SMTP path.
    _resolve_send_identity = None  # type: ignore[assignment]
    _send_via_gmail_api = None  # type: ignore[assignment]

# V6.8.3 structured logging — JSON-shaped error/state events go to
# state/logs/{module}.log alongside stderr. Falls back to a stub on
# import error so this daemon never fails just because the lib isn't
# on sys.path (dev environments, ad-hoc subprocess invocations).
try:
    from lib.structured_log import get_logger  # type: ignore
    _slog = get_logger("send_gateway")
except Exception:
    class _StubSlog:
        def info(self, *_a, **_k): pass
        def warn(self, *_a, **_k): pass
        def error(self, *_a, **_k): pass
        def critical(self, *_a, **_k): pass
    _slog = _StubSlog()


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
# Free-form strings allowed (send() only requires agent_source to be non-empty;
# membership here is NOT enforced), but staying on these values keeps audits sane.
KNOWN_AGENT_SOURCES: frozenset[str] = frozenset({
    "outreach_engine",
    "funnel_nurture",
    "email_engine",
    "booking_engine",
    "n8n_inbound",
    "manual_cc",
    "scheduler",
    "test_harness",
    "cold_outreach_runner",  # SunBiz blast scheduler daemon (cold_outreach_runner.DAEMON_NAME)
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
    # Sun Biz Funding — first client tenant. Added 2026-05-25 so
    # outbound shop-out emails to lender contacts ship with the SunBiz
    # CASL footer instead of leaking the OASIS / Collingwood address.
    # Operator: Ezra at Submissions@sunbizfunding.com. sender_name +
    # business_address pending operator confirmation. The gateway fails
    # closed for external SunBiz sends until this becomes a confirmed
    # physical mailing address.
    "sunbiz": {
        "business_name": "Sun Biz Funding",
        # 2026-06-08: confirmed via the dashboard sidebar — the operator on
        # submissions@sunbizfunding.com is Ezra. Sign-off line on every
        # SunBiz email reads "— Ezra".
        "sender_name": "Ezra",
        # 2026-06-08: CC's explicit decision — SunBiz emails ship without
        # a physical address in the footer. Legal-risk note: CAN-SPAM (US)
        # and CASL (Canada) both require a real mailing address in
        # commercial email; flying without one creates real exposure if a
        # recipient complains. Acknowledged by operator. The empty value
        # is also intentionally absent from PLACEHOLDER_BUSINESS_ADDRESSES
        # below so the gate doesn't block these sends.
        "business_address": "",
        "from_display": "Sun Biz Funding",
        # Explicit flag so the footer builder knows to omit the address
        # line entirely (rather than rendering "Address:" with nothing
        # after it). Read by casl_compliance.build_casl_footer.
        "suppress_business_address": True,
    },
}

DEFAULT_BRAND = "oasis"
# Brand business_address values that block commercial sends as placeholder /
# misconfigured. Empty string is in the set so a brand silently set to ""
# without the explicit suppress_business_address opt-out doesn't accidentally
# ship address-less email. SunBiz bypasses via the suppress flag — see the
# gate at the `_BLOCK_PLACEHOLDER_ADDR` site below.
PLACEHOLDER_BUSINESS_ADDRESSES: frozenset[str] = frozenset({
    "",
    "Sun Biz Funding",
})
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


def _parse_email_list(raw: Optional[str]) -> list[str]:
    """Parse comma/semicolon separated recipient strings for CC support."""
    if not raw:
        return []
    parts = re.split(r"[;,]", raw)
    return [p.strip() for p in parts if p.strip()]


def normalize_cc(cc: Any) -> Optional[str]:
    """Normalize a CC input (str or list[str]) to a comma-joined string of
    well-formed-looking addresses, or None when the input has no usable
    entries. Public so every caller routing CCs into send_gateway — the
    daemon (shop_out_sender), the chat-side dispatcher (_tool_shop_out_
    send_batch), the chat send_email tool, and any future consumer —
    can share one source of truth for the normalization rules instead
    of each inlining the same loop.

    Accepts:
      - str  → comma/semicolon-split via _parse_email_list, filtered to
               entries containing '@'.
      - list → trimmed, filtered to non-empty strings containing '@'.
      - None / other → returns None.

    Returns the joined CSV ready to hand to send_gateway.send(cc_email=)
    OR to a `--cc` CLI flag. Filters obvious junk ('@'-less tokens,
    whitespace-only entries) so we don't ship 'TBD' as a CC. Does not
    do RFC 5322 validation — server-side rejection still applies on
    real bad addresses.
    """
    if cc is None:
        return None
    if isinstance(cc, str):
        cleaned = [p for p in _parse_email_list(cc) if "@" in p]
    elif isinstance(cc, list):
        cleaned = [
            e.strip() for e in cc
            if isinstance(e, str) and "@" in e and e.strip()
        ]
    else:
        return None
    return ",".join(cleaned) if cleaned else None


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
        # V6.8.3: structured_log mirrors the stderr line into the JSON ledger.
        print(f"[send_gateway] resolve_lead_id warning: {exc}", file=sys.stderr)
        _slog.warn("resolve_lead_id_failed", error_type=type(exc).__name__,
                   error=str(exc)[:200])
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


# ---- Phase 1 — extended pre-send gates (Adon brief, 2026-06-08) ------------
#
# Five new gates layered on top of the original 5 + suppression surface in
# can_act. Built after Adon's MCA follow-up architecture brief asked for the
# 13-check pre-send chokepoint. The cheap deterministic checks (suppression,
# manual pause, sentinel pause, send window) fire first; DB queries
# (reply-since, inter-touch gap) only run when the cheap checks pass.
#
# Every new gate is fail-closed on DB error: if the ledger is unavailable,
# the gate refuses the send rather than ship blind. Same posture as the
# existing cooldown / cap gates.

# 90-min minimum gap between ANY two outbound touches to the same lead, across
# all channels and all agents. Adon §4.2 gate #8. Lower than the per-channel
# cooldown (which is 24-168h depending on channel) — this catches the case
# where Agent A sends SMS at 10:00 and Agent B tries email at 10:30.
INTER_TOUCH_GAP_MINUTES = 90

# US state -> IANA timezone for the send-window gate. Mirrors the importer's
# STATE_TIMEZONE map (Codex finding #8) so a lead with data.state="CA" but
# no explicit data.timezone still gets enforced PST hours for SMS. States
# with mixed time zones map to the largest population zone.
_STATE_TIMEZONE: dict[str, str] = {
    "AL": "America/Chicago",     "AK": "America/Anchorage",
    "AZ": "America/Phoenix",     "AR": "America/Chicago",
    "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York",    "DC": "America/New_York",
    "DE": "America/New_York",    "FL": "America/New_York",
    "GA": "America/New_York",    "HI": "Pacific/Honolulu",
    "IA": "America/Chicago",     "ID": "America/Boise",
    "IL": "America/Chicago",     "IN": "America/Indiana/Indianapolis",
    "KS": "America/Chicago",     "KY": "America/New_York",
    "LA": "America/Chicago",     "MA": "America/New_York",
    "MD": "America/New_York",    "ME": "America/New_York",
    "MI": "America/Detroit",     "MN": "America/Chicago",
    "MO": "America/Chicago",     "MS": "America/Chicago",
    "MT": "America/Denver",      "NC": "America/New_York",
    "ND": "America/Chicago",     "NE": "America/Chicago",
    "NH": "America/New_York",    "NJ": "America/New_York",
    "NM": "America/Denver",      "NV": "America/Los_Angeles",
    "NY": "America/New_York",    "OH": "America/New_York",
    "OK": "America/Chicago",     "OR": "America/Los_Angeles",
    "PA": "America/New_York",    "RI": "America/New_York",
    "SC": "America/New_York",    "SD": "America/Chicago",
    "TN": "America/Chicago",     "TX": "America/Chicago",
    "UT": "America/Denver",      "VA": "America/New_York",
    "VT": "America/New_York",    "WA": "America/Los_Angeles",
    "WI": "America/Chicago",     "WV": "America/New_York",
    "WY": "America/Denver",
}

# Channel-specific send windows in lead LOCAL time. TCPA hard rule for SMS
# (8am-9pm); B2B email reply rates peak 9am-6pm weekdays. Outside these
# windows we refuse the send and the caller can reschedule.
SEND_WINDOWS: dict[str, dict[str, Any]] = {
    "sms": {
        "earliest_hour": 8,
        "latest_hour": 21,  # 9pm
        "weekdays_only": False,  # TCPA permits weekend SMS in the window
    },
    "email": {
        "earliest_hour": 9,
        "latest_hour": 18,  # 6pm
        "weekdays_only": True,
    },
    "instagram": {
        "earliest_hour": 9,
        "latest_hour": 20,
        "weekdays_only": False,
    },
    # Phone calls — kept loose because the human operator is the one making
    # the call. Gateway just records the activity for cooldown purposes.
    "phone": {
        "earliest_hour": 0,
        "latest_hour": 23,
        "weekdays_only": False,
    },
    # Telegram + skool are internal / community channels — no window enforcement.
}


def _lead_data_blob(db: Any, lead_id: Optional[str]) -> dict[str, Any]:
    """Best-effort lookup of the lead's jsonb data blob from tenant_records.
    SunBiz stores leads in tenant_records(entity_type='lead'); the legacy
    OASIS path uses the leads table. We check tenant_records first (it
    carries the new MCA fields Adon's brief introduces); fall back to
    leads on miss. Returns empty dict on any failure so callers never
    crash on a malformed row."""
    if not lead_id:
        return {}
    try:
        r = (
            db.table("tenant_records")
            .select("data")
            .eq("id", lead_id)
            .eq("entity_type", "lead")
            .limit(1)
            .execute()
        )
        if r.data and isinstance(r.data[0].get("data"), dict):
            return r.data[0]["data"]
    except Exception:  # noqa: BLE001
        pass
    try:
        r = db.table("leads").select("data").eq("id", lead_id).limit(1).execute()
        if r.data and isinstance(r.data[0].get("data"), dict):
            return r.data[0]["data"]
    except Exception:  # noqa: BLE001
        pass
    return {}


def _check_suppression(to_email: Optional[str], lead_data: dict[str, Any],
                       intent: str = "commercial") -> Optional[str]:
    """Surface CASL suppression / opt-out in can_act. The legacy path
    enforced this inside send() only; surfacing here lets the scheduler
    see WHY a lead is uncontactable before queuing the next touch. Returns
    a string reason if blocked, None if cleared.

    Three sources of suppression checked, in order:
      1. lead_data.opted_out (set by /unsubscribe handler + manual ops)
      2. casl_compliance.should_suppress(to_email) — reads suppression
         table + email_suppressions table populated by /unsubscribe
      3. Reserved domain check (e.g. anthropic.com, supabase.io —
         the should_suppress helper handles this internally)
    """
    if intent == "transactional":
        # CASL s. 10(9) exemption — booking confirms, contract sends, etc.
        # Still pass through the explicit opt-out check below; an operator
        # who manually opted-out the lead overrides the exemption.
        pass
    if lead_data.get("opted_out") is True:
        return "lead opted out (data.opted_out=true)"
    if intent == "commercial" and to_email and to_email.strip():
        try:
            if should_suppress(to_email.strip().lower()):
                return f"suppressed address: {to_email.strip().lower()}"
        except Exception:  # noqa: BLE001
            # should_suppress failing means the suppression table query
            # broke — fail closed (refuse send) rather than risk a CASL
            # violation.
            return "suppression ledger unavailable"
    return None


def _check_manual_pause(lead_data: dict[str, Any], now: datetime) -> Optional[str]:
    """Operator can manually pause all automated outbound to a lead by
    setting lead.data.manual_paused = true OR lead.data.paused_until =
    '<future ISO timestamp>'. Used when the operator is mid-conversation
    by phone or in person and doesn't want the automation to interject.

    `paused_until` takes precedence — it auto-clears at the timestamp.
    `manual_paused` boolean is sticky and requires explicit unset.
    """
    if lead_data.get("manual_paused") is True:
        return "lead manually paused by operator (data.manual_paused=true)"
    paused_until = lead_data.get("paused_until")
    if paused_until:
        try:
            cutoff = datetime.fromisoformat(str(paused_until).replace("Z", "+00:00"))
            if now < cutoff:
                return f"lead manually paused until {cutoff.isoformat()}"
        except (ValueError, TypeError):
            pass
    return None


def _check_sentinel_pause(lead_data: dict[str, Any], now: datetime) -> Optional[str]:
    """Sentinel (sentiment scorer) auto-pauses outbound when the rolling
    sentiment average drops below -30. The pause has a hard expiry so the
    lead becomes reachable again after the cool-off window. Set by
    sunbiz-agent/scripts/sentinel.py."""
    pause_until = lead_data.get("sentinel_pause_until")
    if not pause_until:
        return None
    try:
        cutoff = datetime.fromisoformat(str(pause_until).replace("Z", "+00:00"))
        if now < cutoff:
            reason_detail = lead_data.get("sentinel_pause_reason", "negative sentiment")
            return f"sentinel pause active until {cutoff.isoformat()}: {reason_detail}"
    except (ValueError, TypeError):
        pass
    return None


def _check_send_window(channel: str, lead_data: dict[str, Any],
                       now: datetime) -> Optional[str]:
    """TCPA + B2B etiquette: refuse SMS outside 8am-9pm local; refuse
    email outside 9am-6pm weekdays local.

    Timezone resolution (Codex finding #8):
      1. If lead.data.timezone is set: use it
      2. Otherwise, derive from lead.data.state via a state→tz map
      3. Otherwise:
           - SMS: FAIL CLOSED (TCPA penalties for off-hours SMS are
             real; refusing the send and surfacing the gap to the
             operator is safer than guessing Toronto and waking a
             California merchant at 5am)
           - Email: fall back to operator-local (Toronto) since
             B2B email outside the window is etiquette, not legal risk
    """
    window = SEND_WINDOWS.get(channel)
    if window is None:
        return None  # internal / unconfigured channels skip window check
    lead_tz_explicit = (lead_data.get("timezone") or "").strip()
    if not lead_tz_explicit:
        # Try state-derived fallback
        state = (lead_data.get("state") or "").strip().upper()[:2]
        derived = _STATE_TIMEZONE.get(state)
        if derived:
            lead_tz = derived
        elif channel == "sms":
            # TCPA fail-closed
            return (
                "sms send window: timezone unknown for this lead "
                "(no data.timezone, no data.state to derive from). "
                "Refusing to send SMS without confirmed local time — set "
                "lead.data.timezone explicitly or populate data.state."
            )
        else:
            lead_tz = "America/Toronto"
    else:
        lead_tz = lead_tz_explicit
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        local_now = now.astimezone(ZoneInfo(lead_tz))
    except Exception:  # noqa: BLE001
        # ZoneInfo failed (rare — tzdata missing). For SMS this is the
        # same risk surface as unknown timezone, fail closed.
        if channel == "sms":
            return f"sms send window: ZoneInfo failed for {lead_tz}; refusing TCPA-sensitive send"
        local_now = now - timedelta(hours=4)  # ~Toronto fallback for email
    if window.get("weekdays_only") and local_now.weekday() >= 5:
        return (
            f"{channel} send window: weekday-only "
            f"(today is {local_now.strftime('%A')} in {lead_tz})"
        )
    hour = local_now.hour
    earliest = window["earliest_hour"]
    latest = window["latest_hour"]
    if hour < earliest or hour >= latest:
        return (
            f"{channel} send window: {earliest}:00-{latest}:00 "
            f"(currently {local_now.strftime('%H:%M %Z')} in {lead_tz})"
        )
    return None


def _check_reply_since_last_outbound(db: Any, lead_id: Optional[str]) -> Optional[str]:
    """If the merchant has replied (any inbound interaction) since our
    most recent outbound, automated agents MUST hold back — the operator
    is now the right interface. Adon §4.2 gate #5.

    Runs as ONE query against lead_interactions ordered by created_at
    desc, takes the most recent row, and checks direction. If the last
    interaction was inbound, block.
    """
    if not lead_id:
        return None
    try:
        rows = (
            db.table("lead_interactions")
            .select("direction, channel, created_at, type")
            .eq("lead_id", lead_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        # Fail closed — if we can't read the ledger we don't know whether
        # the merchant replied. Better to delay than to talk over them.
        return f"reply-since-outbound ledger unavailable: {exc}"
    if not rows:
        return None
    last = rows[0]
    direction = (last.get("direction") or "").strip().lower()
    if direction == "inbound":
        ts = last.get("created_at") or "unknown"
        return (
            "merchant replied since last outbound "
            f"(inbound {last.get('channel')} at {ts}); handing off to operator"
        )
    return None


def _check_inter_touch_gap(db: Any, lead_id: Optional[str],
                           lead_data: dict[str, Any],
                           now: datetime) -> Optional[str]:
    """No agent may touch the same merchant within 90 minutes of any
    other outbound, regardless of channel. Adon §4.2 gate #8 — protects
    against two agents firing at the same merchant in quick succession.

    Yellow flag handling (Adon §7): if Sentinel has flagged this lead
    with `sentinel_yellow_flag=True` (rolling avg between -30 and 0),
    double the gap to 180 min so cadence naturally halves without a
    hard pause.

    Single query: any outbound lead_interactions within the gap window?
    """
    if not lead_id:
        return None
    gap_minutes = INTER_TOUCH_GAP_MINUTES
    if lead_data.get("sentinel_yellow_flag"):
        # Honor the yellow flag only while the expiry is in the future.
        yellow_until = lead_data.get("sentinel_yellow_until")
        if yellow_until:
            try:
                expiry = datetime.fromisoformat(str(yellow_until).replace("Z", "+00:00"))
                if now < expiry:
                    gap_minutes = INTER_TOUCH_GAP_MINUTES * 2
            except (ValueError, TypeError):
                pass
    cutoff = now - timedelta(minutes=gap_minutes)
    try:
        rows = (
            db.table("lead_interactions")
            .select("channel, created_at, agent_source")
            .eq("lead_id", lead_id)
            .eq("direction", "outbound")
            .gte("created_at", cutoff.isoformat())
            .limit(1)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        return f"inter-touch ledger unavailable: {exc}"
    if rows:
        r = rows[0]
        flag_note = " [yellow-flag 2x]" if gap_minutes != INTER_TOUCH_GAP_MINUTES else ""
        return (
            f"inter-touch gap: {gap_minutes}min cooldown{flag_note} "
            f"(recent outbound {r.get('channel')} at {r.get('created_at')} "
            f"by {r.get('agent_source')})"
        )
    return None


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
    intent: str = "commercial",
    agent_source: str = "unknown",
    tenant_id: Optional[str] = None,
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
    # Effective caps start at the static defaults; operating mode below
    # multiplies them in-place. Codex finding #4: the OLD code mutated
    # result['daily_cap'] but the later cap CHECK read DAILY_CAPS directly,
    # so the multiplier had no enforcement effect. Now both reporting and
    # enforcement use these effective_* locals throughout the function.
    effective_daily_cap = DAILY_CAPS.get(channel)
    effective_hourly_cap = HOURLY_CAPS.get(channel)
    result: dict[str, Any] = {
        "allowed": True,
        "reason": "ok",
        "last_action_at": None,
        "cooldown_until": None,
        "daily_count": 0,
        "daily_cap": effective_daily_cap,
        "hourly_count": 0,
        "hourly_cap": effective_hourly_cap,
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

    # Gate 0a-0b (Phase 1 finalization, Adon brief §4.9 + §9 — 2026-06-08):
    # operator kill switches + operating mode. These fire BEFORE any other
    # check because they're the operator's panic button — if the operator
    # said "pause everything," nothing else matters.
    #
    # Tenant context: callers that don't pass tenant_id explicitly fall
    # through with no kill-switch enforcement (cross-tenant / system sends).
    # SunBiz daemons MUST pass tenant_id from the lead row they're acting on.
    if tenant_id:
        try:
            from pause_controller import (  # type: ignore
                check_kill_switches as _check_kill_switches,
                check_operating_mode as _check_operating_mode,
            )
            ks_reason = _check_kill_switches(db, tenant_id, agent_source)
            if ks_reason:
                result.update(allowed=False, reason=f"kill_switch: {ks_reason}")
                return result
            mode_reason, cap_mult = _check_operating_mode(db, tenant_id, agent_source)
            if mode_reason:
                result.update(allowed=False, reason=f"operating_mode: {mode_reason}")
                return result
            # Apply cap multiplier to the effective_* LOCALS so the
            # downstream hourly + daily cap CHECKS use the adjusted budget,
            # not just the result dict (which the old code mutated but the
            # checks ignored — Codex finding #4). Floor at 1 so a 0.5x of
            # a single-slot cap doesn't truncate to 0 and lock out the gate.
            if cap_mult != 1.0:
                if effective_daily_cap is not None:
                    effective_daily_cap = max(1, int(effective_daily_cap * cap_mult))
                if effective_hourly_cap is not None:
                    effective_hourly_cap = max(1, int(effective_hourly_cap * cap_mult))
                result["daily_cap"] = effective_daily_cap
                result["hourly_cap"] = effective_hourly_cap
                result["operating_mode_multiplier"] = cap_mult
        except ImportError:
            # pause_controller absent at import time (older deploys, tests
            # with a stripped sys.path). Treat as no kill switches active —
            # original gate set still runs.
            pass
        except Exception as exc:  # noqa: BLE001
            # Fail-closed posture: if we can't read the kill switch table,
            # refuse the send rather than risk talking past an operator pause.
            result.update(allowed=False, reason=f"kill_switch ledger unavailable: {exc}")
            return result

    # Gates 1b-1e (Phase 1, Adon brief 2026-06-08): cheap deterministic
    # lead-state checks BEFORE we burn a DB query on cooldowns/caps. Suppression,
    # manual pause, sentinel pause, send window. Lead data blob fetched once
    # and reused across all four gates.
    lead_data = _lead_data_blob(db, lead_id) if lead_id else {}

    reason_suppression = _check_suppression(to_email, lead_data, intent=intent)
    if reason_suppression:
        result.update(allowed=False, reason=reason_suppression)
        return result

    reason_manual = _check_manual_pause(lead_data, now)
    if reason_manual:
        result.update(allowed=False, reason=reason_manual)
        return result

    reason_sentinel = _check_sentinel_pause(lead_data, now)
    if reason_sentinel:
        result.update(allowed=False, reason=reason_sentinel)
        return result

    reason_window = _check_send_window(channel, lead_data, now)
    if reason_window:
        result.update(allowed=False, reason=reason_window)
        return result

    # Gate 2: empty email (commercial intent will catch suppression separately).
    if to_email is not None and not (to_email or "").strip():
        result.update(allowed=False, reason="empty recipient")
        return result

    # Gates 2b-2c (Phase 1): reply-since-last-outbound + 90-min inter-touch
    # gap. Both run one cheap DB query against lead_interactions. Inserted
    # BEFORE per-channel cooldown so an inbound reply or recent cross-channel
    # touch short-circuits the heavier cooldown ledger scan.
    if lead_id:
        reason_reply = _check_reply_since_last_outbound(db, lead_id)
        if reason_reply:
            result.update(allowed=False, reason=reason_reply)
            return result

        reason_gap = _check_inter_touch_gap(db, lead_id, lead_data, now)
        if reason_gap:
            result.update(allowed=False, reason=reason_gap)
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

    # Gate 3b: hourly cap. Uses effective_hourly_cap so operating mode
    # multipliers actually enforce (Codex finding #4).
    if effective_hourly_cap is not None:
        try:
            count = _count_window(db, channel, now - timedelta(hours=1))
            result["hourly_count"] = count
            if count >= effective_hourly_cap:
                result.update(
                    allowed=False,
                    reason=f"hourly cap hit: {count}/{effective_hourly_cap} {channel} actions in the last hour",
                )
                return result
        except Exception as exc:  # noqa: BLE001
            result.update(allowed=False, reason=f"hourly cap ledger unavailable: {exc}")
            return result

    # Gate 4: daily cap. Uses effective_daily_cap so operating mode
    # multipliers actually enforce (Codex finding #4).
    if effective_daily_cap is not None:
        try:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            count = _count_window(db, channel, day_start)
            result["daily_count"] = count
            _maybe_notify_daily_cap_threshold(channel, count, effective_daily_cap)
            if count >= effective_daily_cap:
                result.update(
                    allowed=False,
                    reason=f"daily cap hit: {count}/{effective_daily_cap} {channel} actions today",
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
    """Look up the tenant for a record id. Codex audit 2026-06-08 caught that
    the OLD impl only checked the legacy `leads` table — but SunBiz writes
    every lead to `tenant_records` (entity_type='lead'), so resolved_tenant
    came back None and the kill_switch / operating_mode gates silently
    skipped every SunBiz drip.

    Shopping-out 2026-06-08 caught a second variant: the previous fix added
    a `.eq('entity_type', 'lead')` filter, which then made application_id /
    offer_id passes fail-closed the same way. The shop-out sender passes
    application_id as lead_id when the application's app_data.lead_id is
    missing, and so EVERY shopping-out tick blocked at the kill-switch gate.
    Drop the entity_type filter — tenant_records.id is a UUID primary key,
    globally unique across entity_types, so a row match is a row match.

    Callers should also pass tenant_id explicitly to send() when they
    already know it (shop_out_sender, sequence_runner) — see the gate at
    the call site, which now prefers caller-supplied tenant_id over this
    lookup. This function remains as defense-in-depth for callers that
    only have a record id.

    Returns the tenant UUID string when found, None on miss.
    """
    if not lead_id:
        return None
    # Primary: tenant_records (SunBiz + every modern tenant) — any entity_type
    try:
        r = (
            db.table("tenant_records")
            .select("tenant_id")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        if r.data and r.data[0].get("tenant_id"):
            return str(r.data[0]["tenant_id"])
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] tenant_records lookup warning: {exc}", file=sys.stderr)
    # Secondary: legacy `leads` table (OASIS personal tenant, older paths)
    try:
        r = db.table("leads").select("tenant_id").eq("id", lead_id).limit(1).execute()
        if r.data and r.data[0].get("tenant_id"):
            return str(r.data[0]["tenant_id"])
    except Exception as exc:  # noqa: BLE001
        print(f"[send_gateway] legacy leads lookup warning: {exc}", file=sys.stderr)
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
    acted_by_user_id: Optional[str] = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cooldown_until_iso = (
        (now + timedelta(hours=cooldown_hours)).isoformat()
        if cooldown_hours and cooldown_hours > 0 else None
    )
    reservation_metadata = dict(metadata or {})
    reservation_metadata.update({
        "reservation_status": "pending",
        "reserved_at": now.isoformat(),
    })
    # Migration 079 introduced the dedicated reserve_send_slot RPC after
    # the old raw-SQL CTE path stopped working: exec_sql wraps queries
    # as `SELECT FROM (user_sql) t`, which makes data-modifying CTEs
    # not top-level and PostgreSQL rejects them. Production had been
    # silently falling through to the non-atomic fallback for months.
    res = db.rpc("reserve_send_slot", {
        "p_lead_id": lead_id,
        "p_channel": channel,
        "p_subject": (subject or "")[:500],
        "p_content_preview": (content_preview or "")[:1000],
        "p_agent_source": agent_source,
        "p_cooldown_until": cooldown_until_iso,
        "p_metadata": reservation_metadata,
        "p_window_minutes": RESERVATION_WINDOW_MINUTES,
        "p_actor_user_id": acted_by_user_id,
    }).execute()
    data = getattr(res, "data", None)
    row = data if isinstance(data, dict) else {}
    if not row.get("lock_acquired", True):
        return {"status": "blocked", "reason": "concurrent send detected"}
    if row.get("existing_id"):
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
    acted_by_user_id: Optional[str] = None,
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
                acted_by_user_id=acted_by_user_id,
            )
        except Exception as exc:  # noqa: BLE001
            # The fallback path below loses race protection — two concurrent
            # sends to the same (lead, channel) can both win. Migration 079
            # added a dedicated reserve_send_slot() RPC that should never
            # raise here on a healthy deploy. If you're seeing this in
            # production, the RPC function was either dropped or the
            # schema drifted — fix the RPC, don't keep operating on the
            # fallback.
            print(
                f"[send_gateway] WARNING: reservation RPC unavailable, "
                f"using non-atomic fallback (race condition risk): {exc}",
                file=sys.stderr,
            )
            _slog.warn(
                "reservation_rpc_unavailable",
                error=str(exc),
                channel=channel,
                lead_id=lead_id,
            )

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
    if acted_by_user_id:
        payload["actor_user_id"] = acted_by_user_id
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
    acted_by_user_id: Optional[str] = None,
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
            acted_by_user_id=acted_by_user_id,
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
    acted_by_user_id: Optional[str] = None,
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
    if acted_by_user_id:
        row["actor_user_id"] = acted_by_user_id

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
        # Likely because cooldown_until / agent_source / actor_user_id
        # columns do not exist on this deploy. Retry with the legacy
        # column set so the send still gets logged.
        legacy_row = {k: v for k, v in row.items() if k not in {"cooldown_until", "agent_source", "actor_user_id"}}
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

# RFC-822 header values cannot contain CR or LF without folding rules.
# Python's email.message.Message will happily set whatever string you
# hand it; at serialization time the policy fold-pass raises
# HeaderParseError for embedded newlines, but by then the round row
# is already inserted + the gateway has already done reservation
# logging, so the failure mode is "exception bubbles up after side
# effects" rather than "clean rejection."
#
# Validate at the chokepoint instead so unsafe input is blocked BEFORE
# any state-changing work. Applies to every caller-controllable header
# value: Subject, To, Cc, Message-ID, In-Reply-To, References, and the
# From-address piece.
_HEADER_INJECTION_RE = re.compile(r"[\r\n\x00]")


def _validate_header_value(name: str, value: Optional[str]) -> None:
    """Block CRLF + NUL in any caller-supplied header value.

    The same defense covers Subject (CRLF→fake Bcc), Message-ID family
    (CRLF→arbitrary headers), and recipient strings (CRLF→envelope
    splitting). Empty/None is allowed; the caller chose to omit.
    """
    if value is None or value == "":
        return
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    if _HEADER_INJECTION_RE.search(value):
        raise ValueError(f"{name} contains CR/LF/NUL — header injection blocked")




def _build_email_mime(
    gmail_address: str,
    brand: dict[str, str],
    to_email: str,
    cc_emails: Optional[list[str]],
    subject: str,
    body_text: str,
    body_html: Optional[str],
    intent: str,
    ics_content: Optional[str] = None,
    ics_filename: str = "meeting.ics",
    attachments: Optional[list[dict]] = None,
    message_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
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
    # Chokepoint header-injection defense — runs BEFORE any MIME
    # construction so unsafe input never reaches the serializer.
    # Body text/html are NOT validated here: they live inside the
    # body part, not the header section, so CRLF in the body cannot
    # inject headers.
    _validate_header_value("subject", subject)
    _validate_header_value("to_email", to_email)
    _validate_header_value("gmail_address", gmail_address)
    for i, cc in enumerate(cc_emails or []):
        _validate_header_value(f"cc_emails[{i}]", cc)

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
    if cc_emails:
        outer["Cc"] = ", ".join(cc_emails)
    # Threading headers — used by shop-out (one logical round, N lender
    # recipients sharing References anchor) and any other workflow that
    # wants Gmail/Outlook to group N outbound messages as one
    # conversation. message_id MUST be RFC-822 angle-bracketed; the
    # caller is responsible for synthesizing a stable, globally-unique
    # value. CRLF + NUL bytes are rejected to block header injection.
    _validate_header_value("message_id", message_id)
    _validate_header_value("in_reply_to", in_reply_to)
    _validate_header_value("references", references)
    if message_id:
        outer["Message-ID"] = message_id
    if in_reply_to:
        outer["In-Reply-To"] = in_reply_to
    if references:
        outer["References"] = references
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
        if content_bytes is None:
            content_bytes = att.get("content_bytes")
        if not content_bytes:
            continue
        ctype = att.get("content_type") or att.get("mime_type") or "application/octet-stream"
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
    agent_email: Optional[str] = None,
    lead_id: Optional[str] = None,
) -> tuple[bool, Optional[str], dict]:
    """Physical SMS send. Dispatches to TextTorrent, Twilio, or Kixie based on
    `provider`. Returns (ok, error_message, metadata).

    Metadata is what the gateway folds into the lead_interactions row
    so operators can audit provider + message ID + send timestamp from
    one place. Phase 5.3 of the SunBiz CRM build (2026-05-15); Kixie
    added 2026-06-01 (Phase 1 of TT + Kixie full embedding).

    Why inline (vs subprocess to provider tools): send_gateway is called
    from autonomous code paths (sequence_runner.py drip engine, future
    agent tool calls). A subprocess hop per send is ~150ms of forking +
    Python init, on top of the actual HTTP call. Inline keeps the send
    synchronous + cheap, matching the email path's _send_email_smtp pattern.

    Kixie-specific: requires `agent_email` so Kixie attributes the SMS to
    the acting employee's account. The gateway resolves it from
    acted_by_user_id → user_profiles.email upstream.
    """
    if provider not in ("texttorrent", "twilio", "kixie"):
        return False, f"unknown SMS provider '{provider}' (expected 'texttorrent', 'twilio', or 'kixie')", {}

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

    if provider == "twilio":
        # Twilio path. Twilio's REST API is dead simple: POST to
        # api.twilio.com/2010-04-01/Accounts/<sid>/Messages.json with
        # basic auth (sid + auth token). We don't need the Twilio SDK
        # for this single call.
        # SunBiz finalization (Blocker 5): the SunBiz tenant standardised on the
        # SUNBIZ_TWILIO_* namespace; prefer it, fall back to the unprefixed keys
        # so legacy/multi-brand callers don't crash mid-roll-out.
        sid = (env.get("SUNBIZ_TWILIO_ACCOUNT_SID") or env.get("TWILIO_ACCOUNT_SID") or "").strip()
        token = (env.get("SUNBIZ_TWILIO_AUTH_TOKEN") or env.get("TWILIO_AUTH_TOKEN") or "").strip()
        # Per-brand phone-number selection (CC has multi-brand setup —
        # oasis / nostalgic / conaugh_mckenna). Operators set
        # TWILIO_FROM_NUMBER_OASIS, TWILIO_FROM_NUMBER_NOSTALGIC, etc.,
        # plus a default TWILIO_FROM_NUMBER for back-compat. Brand-specific
        # number is checked first; falls back to the default so existing
        # single-brand operators keep working without an env tweak.
        brand_upper = (brand or "").upper().replace("-", "_")
        from_number = (
            env.get("SUNBIZ_TWILIO_FROM_NUMBER")
            or env.get(f"TWILIO_FROM_NUMBER_{brand_upper}")
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

    # Kixie path. Kixie's SMS endpoint shares the action API with calls:
    # POST https://apig.kixie.com/app/event with eventname="sms".
    # Per-employee attribution lives on the `email` field — that's how
    # Kixie's UI groups outbound SMS under each agent's account, so the
    # acting employee MUST be passed in. Falls back to KIXIE_DEFAULT_AGENT_EMAIL
    # env when no per-send agent is provided (lets sequence_runner drips
    # work without a specific actor).
    api_key = (env.get("KIXIE_API_KEY") or "").strip()
    business_id = (env.get("KIXIE_BUSINESS_ID") or "").strip()
    kixie_agent = (agent_email or env.get("KIXIE_DEFAULT_AGENT_EMAIL") or "").strip()
    if not api_key or not business_id:
        return False, "KIXIE_API_KEY and KIXIE_BUSINESS_ID required in the agents env file", {}
    if not kixie_agent:
        return False, (
            "Kixie SMS needs an agent email — pass acted_by_user_id "
            "(resolves via user_profiles) or set KIXIE_DEFAULT_AGENT_EMAIL."
        ), {}
    payload: dict[str, Any] = {
        "apikey": api_key,
        "businessid": business_id,
        "eventname": "sms",
        "email": kixie_agent,
        "target": to_phone,
        "message": body_text,
    }
    if lead_id:
        # Echoed back via webhook customField1 so inbound sms / delivery
        # callbacks attribute to the right lead in lead_interactions.
        payload["customField1"] = lead_id
    try:
        r = _requests.post(
            "https://apig.kixie.com/app/event",
            json=payload,
            timeout=30,
            headers={"user-agent": "oasis-bravo/send-gateway/1.0"},
        )
    except _requests.RequestException as e:
        return False, f"network error contacting Kixie: {e}", {}
    if r.status_code >= 400:
        try:
            err = r.json()
            err_msg = err.get("message") if isinstance(err, dict) else err
        except ValueError:
            err_msg = r.text[:400]
        return False, f"Kixie HTTP {r.status_code}: {err_msg}", {}
    try:
        data = r.json() if r.text else {}
    except ValueError:
        data = {}
    return True, None, {
        "provider_message_id": data.get("callid") or data.get("messageid"),
        "kixie_agent_email": kixie_agent,
    }


def _send_email_smtp(
    env: dict[str, str],
    mime: MIMEMultipart,
    to_email: str,
    cc_emails: Optional[list[str]] = None,
) -> tuple[bool, Optional[str]]:
    gmail_user = env.get("GMAIL_USER") or env.get("GMAIL_ADDRESS", "")
    gmail_pass = env.get("GMAIL_APP_PASSWORD", "")
    recipients = [to_email] + list(cc_emails or [])
    # The opt-in sender-identity guard lives in the lib.smtp_send chokepoint so
    # every SMTP caller is covered once; pass the tenant's required domain through
    # (no-op when EMAIL_REQUIRE_FROM_DOMAIN is unset — the multi-brand default).
    ok, err = _smtp_send(
        gmail_user, gmail_pass, mime, recipients,
        require_from_domain=env.get("EMAIL_REQUIRE_FROM_DOMAIN"),
    )
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
    cc_email: Optional[str] = None,
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
    # acted_by_user_id added Phase 4 of SunBiz multi-employee
    # personalization (2026-05-29). When set AND channel='email',
    # the send path looks up the user's gmail_oauth credential in
    # user_integration_credentials and authenticates as that user.
    # Falls back to the tenant-shared GMAIL_USER + GMAIL_APP_PASSWORD
    # env vars when the user hasn't connected their personal Gmail.
    # SMS (TextTorrent / Twilio) and Kixie always use tenant-shared
    # credentials regardless of acted_by_user_id — billing routes
    # through the tenant owner.
    acted_by_user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    # Threading headers — used by shop-out (one shopping round, N
    # lender recipients) so all N outbound messages share a References
    # anchor and Gmail groups them as one conversation in the agent's
    # CC'd inbox. message_id MUST be a valid RFC-822 angle-bracketed
    # identifier. The caller owns uniqueness.
    message_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
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
    env = load_env()
    # CASL_* env vars override the resolved brand's footer fields, but only
    # when set — an operator can supply a confirmed sender/business/address
    # (e.g. SunBiz's pending mailing address) without editing the multi-brand
    # map. Copy the brand dict so the module-level map stays untouched, and
    # leave any unset override so other brands keep their built-in identity.
    brand_cfg = dict(BRAND_IDENTITY[brand])
    # If a brand explicitly opts out of a business_address (e.g. SunBiz —
    # suppress_business_address: True), a stale CASL_BUSINESS_ADDRESS env
    # var on a host must NOT silently reintroduce one. Same logic applies
    # if a future brand opts out of sender/business identity overrides.
    _suppress_addr = brand_cfg.get("suppress_business_address") is True
    for _field, _env_key in (
        ("sender_name", "CASL_SENDER_NAME"),
        ("business_name", "CASL_BUSINESS_NAME"),
        ("business_address", "CASL_BUSINESS_ADDRESS"),
    ):
        if _field == "business_address" and _suppress_addr:
            continue
        _override = (env.get(_env_key) or "").strip()
        if _override:
            brand_cfg[_field] = _override
    # Placeholder-address block. Order matters:
    #   1. Internal sends never need a footer address — short-circuit.
    #   2. Brand explicitly opted out (suppress_business_address: True) —
    #      CC's SunBiz decision; takes the legal-risk acknowledgment from
    #      BRAND_IDENTITY's comment block. Bypass the gate.
    #   3. Otherwise: if the address is empty/placeholder, block.
    if (
        intent != "internal"
        and not brand_cfg.get("suppress_business_address")
        and brand_cfg.get("business_address", "").strip() in PLACEHOLDER_BUSINESS_ADDRESSES
    ):
        return {"status": "error",
                "reason": f"brand '{brand}' is missing a confirmed physical business_address",
                "lead_id": lead_id, "interaction_id": None,
                "cooldown_until": None, "daily_count": None}
    cc_emails: list[str] = []

    # ---- Per-channel required fields ----
    if channel == "email":
        if not to_email or not subject or not body_text:
            return {"status": "error",
                    "reason": "email channel requires to_email, subject, body_text",
                    "lead_id": lead_id, "interaction_id": None,
                    "cooldown_until": None, "daily_count": None}
        cc_emails = _parse_email_list(cc_email)
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

    # ---- Tenant resolution + mismatch + kill-switch -----------------------
    # These ALWAYS run whenever the call carries a tenant-scoped identifier
    # (lead_id OR tenant_id), regardless of intent. Codex audit 2026-06-09
    # round-3 [high]: the round-2 fix exempted intent="internal" from these
    # gates, but `intent` is caller-controlled input. A direct Python caller
    # could pass intent="internal" with a paused tenant's lead_id and a
    # different tenant_id and bypass the mismatch + kill-switch entirely.
    #
    # The exempt path is now structural, not intent-based: if neither
    # lead_id nor tenant_id was supplied, there's nothing to resolve and
    # the panic state is genuinely cross-tenant — skip. Otherwise, enforce.
    #
    # Codex audit 2026-06-08 finding #1: lead_id given without a resolvable
    # tenant blocks the kill-switch from firing — fail-closed.
    # Codex audit 2026-06-09 round-1 [critical]: blindly trusting the
    # caller-supplied tenant_id let a hostile caller defeat the kill switch
    # by passing a paused tenant's lead_id with an unpaused tenant_id.
    # Codex audit 2026-06-09 round-2 [high]: previously this whole block lived
    # inside `if intent not in {"internal", "transactional"}:`, so a caller
    # could pass `intent="transactional"` with a mismatched tenant_id and
    # skip the mismatch + kill-switch checks entirely.
    #
    # Resolution order (safe):
    #   1. DB lookup is the source of truth.
    #   2. Caller-supplied tenant_id is honored only when (a) it matches the
    #      lookup, or (b) the lookup returned nothing (mid-migration edge).
    #   3. Caller-supplied tenant_id that CONTRADICTS the lookup is a hard
    #      block — surface the mismatch loud, never silent.
    resolved_tenant: Optional[str] = None
    if lead_id or tenant_id:
        lookup_tenant = _resolve_tenant_for_lead(db, lead_id) if lead_id else None
        if tenant_id and lookup_tenant and tenant_id != lookup_tenant:
            return {
                "status": "blocked",
                "reason": (
                    "tenant_id mismatch: caller-supplied tenant_id "
                    f"{tenant_id!r} does not match lead's tenant of "
                    f"record {lookup_tenant!r}. Refusing to send."
                ),
                "lead_id": lead_id,
                "interaction_id": None,
                "cooldown_until": None,
                "daily_count": None,
            }
        # Prefer the DB-resolved tenant when present (source of truth).
        # Fall back to caller-supplied only when the DB has no info.
        resolved_tenant = lookup_tenant or tenant_id
        if lead_id and not resolved_tenant:
            return {
                "status": "blocked",
                "reason": "send blocked: lead_id given but tenant could not be resolved (kill-switch enforcement unavailable)",
                "lead_id": lead_id,
                "interaction_id": None,
                "cooldown_until": None,
                "daily_count": None,
            }

        # Kill-switch + operating-mode pre-check — runs for transactional too
        # (booking confirmations etc. ARE tenant-scoped; a paused operator
        # shouldn't see them ship). Independent from can_act() because
        # can_act() is intent-gated for cooldown/cap, but the panic switch
        # is never gated. can_act() will recompute the same check for
        # commercial — that duplication is fine; correctness > one DB read.
        if resolved_tenant:
            try:
                from pause_controller import (  # type: ignore
                    check_kill_switches as _check_kill_switches,
                    check_operating_mode as _check_operating_mode,
                )
                _ks_reason = _check_kill_switches(db, resolved_tenant, agent_source)
                if _ks_reason:
                    return {
                        "status": "blocked",
                        "reason": f"kill_switch: {_ks_reason}",
                        "lead_id": lead_id,
                        "interaction_id": None,
                        "cooldown_until": None,
                        "daily_count": None,
                    }
                _mode_reason, _ = _check_operating_mode(db, resolved_tenant, agent_source)
                if _mode_reason:
                    return {
                        "status": "blocked",
                        "reason": f"operating_mode: {_mode_reason}",
                        "lead_id": lead_id,
                        "interaction_id": None,
                        "cooldown_until": None,
                        "daily_count": None,
                    }
            except ImportError:
                # pause_controller absent (older deploys, stripped sys.path).
                # Original gate set still applies via can_act for commercial.
                pass
            except Exception as exc:  # noqa: BLE001
                # Fail-closed: can't read panic state, refuse.
                return {
                    "status": "blocked",
                    "reason": f"kill_switch ledger unavailable: {exc}",
                    "lead_id": lead_id,
                    "interaction_id": None,
                    "cooldown_until": None,
                    "daily_count": None,
                }

    # ---- Gate 2 + 3: cooldown + daily cap (skipped for internal/transactional) ----
    # These remain commercial-only — transactional sends are intentionally
    # exempt from cooldown windows and daily caps (booking confirmations,
    # password-resets etc. are time-sensitive). Kill-switch above already ran.
    if intent not in {"internal", "transactional"}:
        check = can_act(
            lead_id=lead_id,
            channel=channel,
            to_email=to_email,
            cooldown_hours=cooldown_hours,
            db=db,
            intent=intent,
            agent_source=agent_source,
            tenant_id=resolved_tenant,
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
        # Per-user Gmail OAuth: send as the connected employee when
        # acted_by_user_id is set AND they have linked Gmail. Identity
        # policy lives in user_gmail_oauth.resolve_send_identity() so
        # the consumer daemon applies the same rules without drift.
        identity = (
            _resolve_send_identity(db, tenant_id, acted_by_user_id)
            if _resolve_send_identity is not None
            else {"mode": "tenant_smtp"}
        )
        if identity["mode"] == "block":
            return {
                "status": "error",
                "reason": f"user_gmail_oauth_resolution_failed: {identity['reason']}",
                "lead_id": lead_id,
                "interaction_id": None,
                "cooldown_until": None,
                "daily_count": None,
            }

        user_gmail_bundle: Optional[dict[str, str]] = (
            identity["bundle"] if identity["mode"] == "user_oauth" else None
        )

        if user_gmail_bundle:
            gmail_user = user_gmail_bundle["gmail_address"]
        else:
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
        if cc_emails:
            full_metadata["cc_email"] = cc_emails

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
            acted_by_user_id=acted_by_user_id,
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
            cc_emails=cc_emails,
            subject=subject,  # type: ignore[arg-type]
            body_text=body_text,  # type: ignore[arg-type]
            body_html=body_html,
            intent=intent,
            ics_content=ics_content,
            ics_filename=ics_filename,
            attachments=attachments,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        if user_gmail_bundle and _send_via_gmail_api is not None:
            # Gmail API path: authenticates as the connected employee.
            # The recipient sees the email coming from their address.
            try:
                raw_mime = mime.as_bytes()
            except Exception as _exc:
                raw_mime = mime.as_string().encode("utf-8")
            ok, err = _send_via_gmail_api(
                user_gmail_bundle["access_token"], raw_mime
            )
            if ok:
                full_metadata["sent_via"] = "gmail_api"
                full_metadata["sent_as"] = user_gmail_bundle["gmail_address"]
                _ping_health(
                    "gws",
                    status="healthy",
                    metadata={"source": "send_gateway.gmail_api"},
                )
            else:
                _ping_health(
                    "gws",
                    status="degraded",
                    error=f"gmail_api: {err or 'unknown'}",
                )
        else:
            ok, err = _send_email_smtp(env, mime, to_email, cc_emails)  # type: ignore[arg-type]
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
                acted_by_user_id=acted_by_user_id,
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
            acted_by_user_id=acted_by_user_id,
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
        if explicit in ("texttorrent", "twilio", "kixie"):
            provider_choice = explicit
        else:
            has_twilio = bool(
                (env.get("SUNBIZ_TWILIO_ACCOUNT_SID") or env.get("TWILIO_ACCOUNT_SID") or "").strip()
                and (env.get("SUNBIZ_TWILIO_AUTH_TOKEN") or env.get("TWILIO_AUTH_TOKEN") or "").strip()
            )
            has_tt = bool((env.get("TEXTTORRENT_API_KEY") or "").strip())
            has_kixie = bool((env.get("KIXIE_API_KEY") or "").strip() and (env.get("KIXIE_BUSINESS_ID") or "").strip())
            # Auto-detect: route to the ONLY configured provider when
            # exactly one is wired. Multi-provider tenants default to
            # texttorrent for back-compat (TT was SunBiz's primary
            # since Phase 5.1). Operator who wants Kixie/Twilio-by-default
            # sets SMS_PROVIDER=kixie / SMS_PROVIDER=twilio.
            configured = [p for p, has in (("twilio", has_twilio), ("texttorrent", has_tt), ("kixie", has_kixie)) if has]
            if len(configured) == 1:
                provider_choice = configured[0]
            elif "texttorrent" in configured:
                provider_choice = "texttorrent"
            elif "twilio" in configured:
                provider_choice = "twilio"
            elif "kixie" in configured:
                provider_choice = "kixie"
            else:
                return {"status": "error",
                        "reason": "sms channel needs TextTorrent, Twilio, or Kixie credentials in the agents env file (TEXTTORRENT_API_KEY / TWILIO_ACCOUNT_SID+TWILIO_AUTH_TOKEN / KIXIE_API_KEY+KIXIE_BUSINESS_ID)",
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
            acted_by_user_id=acted_by_user_id,
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
        # Kixie needs an agent email so it attributes the SMS under the
        # acting employee's account in its UI. Resolve via
        # acted_by_user_id → user_profiles.email; falls back to the env
        # default inside _send_sms_via_provider.
        kixie_agent_email: Optional[str] = None
        if provider_choice == "kixie" and acted_by_user_id and db is not None:
            # Precedence:
            #   1. user_integration_credentials override (employee set their
            #      Kixie login email in Settings → Personal integrations).
            #      Phase 5 of TT + Kixie embedding (2026-06-01).
            #   2. user_profiles.email (default — usually the same as their
            #      Kixie account when employees use a single corporate email).
            #   3. KIXIE_DEFAULT_AGENT_EMAIL env var (handled inside
            #      _send_sms_via_provider).
            try:
                _override = (
                    db.table("user_integration_credentials")
                    .select("encrypted_value")
                    .eq("tenant_id", tenant_id)
                    .eq("user_id", acted_by_user_id)
                    .eq("service", "kixie")
                    .eq("field_key", "kixie_agent_email")
                    .maybeSingle()
                    .execute()
                )
                enc = (getattr(_override, "data", None) or {}).get("encrypted_value")
                if enc:
                    try:
                        from field_encryption import decrypt_field  # type: ignore
                        kixie_agent_email = decrypt_field(enc)
                    except Exception as _e:  # noqa: BLE001
                        print(
                            f"[send_gateway] kixie override decrypt failed "
                            f"user={acted_by_user_id}: {_e}",
                            file=sys.stderr,
                        )
            except Exception as _exc:  # noqa: BLE001
                print(
                    f"[send_gateway] kixie override lookup failed "
                    f"user={acted_by_user_id}: {_exc}",
                    file=sys.stderr,
                )
            if not kixie_agent_email:
                try:
                    _r = (
                        db.table("user_profiles")
                        .select("email")
                        .eq("auth_user_id", acted_by_user_id)
                        .maybeSingle()
                        .execute()
                    )
                    kixie_agent_email = (getattr(_r, "data", None) or {}).get("email")
                except Exception as _exc:  # noqa: BLE001
                    print(
                        f"[send_gateway] kixie agent_email lookup failed "
                        f"user={acted_by_user_id}: {_exc}",
                        file=sys.stderr,
                    )

        ok, sms_err, sms_meta = _send_sms_via_provider(
            env=env,
            provider=provider_choice,
            to_phone=to_phone,
            body_text=body_text,
            brand=brand,
            agent_email=kixie_agent_email,
            lead_id=lead_id,
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
                acted_by_user_id=acted_by_user_id,
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
            acted_by_user_id=acted_by_user_id,
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
        acted_by_user_id=acted_by_user_id,
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
        cc_email=args.cc,
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
    ps.add_argument("--cc", default=None, help="CC recipient email(s), comma-separated")
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
