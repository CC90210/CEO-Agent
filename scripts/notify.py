"""
Bravo Notification System - Telegram alerts for CC.

V3 (2026-04-12): Human-readable format. No brackets. No JSON. No system status.
Every message must pass the "3-second glance test": CC should understand it
immediately on his phone without decoding anything.

Usage:
    from notify import notify
    notify("New lead: John from Acme HVAC just submitted the funnel form", category="lead")
    notify("Stripe: $800 payment received from a retainer client", category="revenue")

Categories: lead, email, booking, content, revenue, outreach, instagram, system, skool-escalation

FILTERING: Only high-signal categories reach CC's Telegram.
- ALWAYS SEND (with sound): lead, booking, revenue, skool-escalation
- SILENT (no sound): email, outreach
- BLOCKED (never send): content, instagram, system
Override via NOTIFY_BLOCKED_CATEGORIES in .env.agents (comma-separated).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Notification idempotency ──────────────────────────────────────────────────
# A dead-letter / error alert that fires on every cron sweep becomes a Telegram
# storm (a real incident: identical "financial hand-off dead-lettered" alerts
# every few seconds). Each cron tick is a FRESH process, so dedup must persist
# on disk, not in memory. Identical (category, message) pairs are suppressed for
# DEDUP_WINDOW_SEC. Distinct alerts (different sender/subject → different text)
# always pass, so this only ever collapses genuine repeats.
_DEDUP_PATH = Path(__file__).resolve().parent.parent / "tmp" / "notify_dedup.json"
DEDUP_WINDOW_SEC = int(os.environ.get("NOTIFY_DEDUP_WINDOW_SEC", "3600"))


def _notify_disabled() -> bool:
    """Hard off-switch. Set NOTIFY_DISABLED=1 (or run under pytest) to make
    notify() a no-op — so a test can exercise the dead-letter/alert code paths
    without firing real Telegram messages at CC. This closes the actual root
    cause of the 2026-07-24 alert storm: consumer tests called the real notify()."""
    if os.environ.get("NOTIFY_DISABLED", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return "PYTEST_CURRENT_TEST" in os.environ


# A stuck condition is ONE problem, not N problems. A flat window turns it into
# a metronome: the 2026-07-29 review-loop mismatch alerted at 10:30, 11:30,
# 12:30, 1:30 — once per window, all night, same sentence. Each repeat is worth
# strictly less than the one before, so the interval doubles: 1h, 2h, 4h, 8h,
# capped at 24h. First occurrence is always immediate.
DEDUP_BACKOFF = os.environ.get("NOTIFY_DEDUP_BACKOFF", "1").strip().lower() \
    not in ("0", "false", "no", "off")
DEDUP_MAX_WINDOW_SEC = int(os.environ.get("NOTIFY_DEDUP_MAX_WINDOW_SEC", str(24 * 3600)))
# Repeats older than this are a NEW incident, not a continuation — reset the
# escalation so a monthly recurrence is not silenced by last month's backoff.
DEDUP_FORGET_SEC = int(os.environ.get("NOTIFY_DEDUP_FORGET_SEC", str(72 * 3600)))

# notify() returns a bool, and SUPPRESSED and FAILED both come back False — but
# they mean opposite things. Suppressed = CC was told recently and the backoff
# window is open. Failed = CC was told nothing.
#
# 2026-08-03: cron_health_check read `not sent` as "alert delivery failed",
# exited 1, and thereby turned ITSELF into a failing cron — which the next tick
# then reported, as a new condition, with a new dedup identity. CC got
# "ERROR: cron failures detected but alert delivery failed (notify_failed)"
# from a watchdog whose alert had worked exactly as designed. Making the dedup
# key stable (same day) made suppression far more effective and so made this
# fire far more often.
#
# Implementation detail — callers use notify_result() instead of reading this.
# Set on every notify() entry. Single-threaded CLI/cron processes only.
LAST_SUPPRESSED = False

# Reasons that mean "CC is aware of this condition". `suppressed` counts because
# the alert landed recently and the backoff window is still open — but ONLY when
# that earlier attempt actually delivered, which _dedup_was_delivered enforces.
DELIVERED_REASONS = ("sent", "suppressed")


def _dedup_identity(category: str, message: str,
                    dedup_key: Optional[str] = None,
                    lane: str = "private") -> str:
    """The cache key. One definition so the writer and the readers cannot drift."""
    ident = dedup_key if dedup_key else message
    prefix = "" if lane == "private" else f"{lane}\x00"
    return hashlib.sha256(
        f"{prefix}{category}\x00{ident}".encode("utf-8")).hexdigest()[:32]


def _dedup_load() -> dict:
    if not _DEDUP_PATH.exists():
        return {}
    try:
        return json.loads(_DEDUP_PATH.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — a corrupt cache must never silence an alert
        return {}


def _dedup_mark_delivered(category: str, message: str,
                          dedup_key: Optional[str] = None,
                          lane: str = "private") -> None:
    """Flag the current window's record as actually delivered.

    `_dedup_should_send` writes its record BEFORE the send, because it has to
    decide first. That means a window can exist for a message that never landed
    — Telegram 403, bad token, retries exhausted. Without this flag the next
    tick sees "suppressed" and a health monitor reads it as "CC already knows",
    which buys silence for the whole backoff window during the exact alerting
    outage the monitor exists to surface.
    """
    key = _dedup_identity(category, message, dedup_key, lane)
    try:
        seen = _dedup_load()
        rec = seen.get(key)
        if not isinstance(rec, dict):
            return
        rec["d"] = True
        seen[key] = rec
        _DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _DEDUP_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(seen), encoding="utf-8")
        os.replace(tmp, _DEDUP_PATH)
    except Exception:  # noqa: BLE001 — bookkeeping must never break a send
        pass


def _dedup_was_delivered(category: str, message: str,
                         dedup_key: Optional[str] = None,
                         lane: str = "private") -> bool:
    """Did the attempt that opened the current window actually land?

    Legacy records (written before the `d` flag existed) have no `d` key. They
    are treated as DELIVERED: those windows were opened by the pre-fix code,
    where the overwhelmingly common case is a successful send, and assuming
    failure would re-page CC for every one of them on the next tick.
    """
    rec = _dedup_load().get(_dedup_identity(category, message, dedup_key, lane))
    if not isinstance(rec, dict):
        return False
    return bool(rec.get("d", True))


def _dedup_should_send(category: str, message: str,
                       dedup_key: Optional[str] = None,
                       lane: str = "private") -> bool:
    """True if this alert hasn't been sent within its current backoff window.

    `dedup_key` pins the identity to the CONDITION instead of the rendered text.
    Without it, an alert that embeds a changing detail (a count, a timestamp, a
    branch name) hashes differently every time and defeats dedup entirely —
    which is the other half of how an alert storm happens.

    `lane` scopes suppression to the DESTINATION (2026-08-02, Codex [P2]).
    Repeat-suppression answers "has CC already seen this?" — and an identical
    sentence sent to his private chat is not something the OASIS group has seen.
    Without the lane in the identity, `python scripts/notify.py "msg"` followed
    by `... --group "msg"` silently dropped the broadcast the operator explicitly
    asked for. Same failure family as the shared-credential lane bug: one
    identity serving two audiences.

    The private lane deliberately keeps the LEGACY key shape (no lane component)
    so an in-flight backoff ladder isn't reset by this change — a stuck alert
    mid-escalation must not get a free re-fire just because the hash moved.

    Best-effort: any error → allow the send. Dedup must never swallow a real
    alert, and a corrupt cache file is not a reason to go silent.
    """
    if DEDUP_WINDOW_SEC <= 0:
        return True
    try:
        key = _dedup_identity(category, message, dedup_key, lane)
        now = time.time()

        seen: dict = _dedup_load()

        rec = seen.get(key)
        # Legacy rows are a bare float timestamp; normalise so an in-flight
        # cache from the old format doesn't crash or lose its history.
        if isinstance(rec, (int, float)):
            rec = {"last": float(rec), "n": 1}
        elif not isinstance(rec, dict):
            rec = None

        if rec:
            last = float(rec.get("last", 0))
            n = int(rec.get("n", 1))
            if (now - last) >= DEDUP_FORGET_SEC:
                rec = None                      # stale → treat as a new incident
            else:
                window = DEDUP_WINDOW_SEC
                if DEDUP_BACKOFF:
                    window = min(DEDUP_WINDOW_SEC * (2 ** (n - 1)), DEDUP_MAX_WINDOW_SEC)
                if (now - last) < window:
                    return False
                rec = {"last": now, "n": n + 1, "d": False}

        if rec is None:
            rec = {"last": now, "n": 1, "d": False}

        seen = {k: v for k, v in seen.items()
                if now - float(v["last"] if isinstance(v, dict) else v) < DEDUP_FORGET_SEC}
        seen[key] = rec
        _DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _DEDUP_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(seen), encoding="utf-8")
        os.replace(tmp, _DEDUP_PATH)
        return True
    except Exception:  # noqa: BLE001
        return True

# Windows TLS setup (2026-07-21): python's bundled certifi store can't verify
# api.telegram.org on this box (SSLCertVerificationError during the go-live
# watch smoke test) — use the OS certificate store instead.
#
# 2026-07-29: promoted from a bare truststore.inject_into_ssl() to the canonical
# helper, which ALSO strips a poisoned SSLKEYLOGFILE. This file is the alerting
# chokepoint, and it was the second casualty of that outage: notify() ->
# requests.post -> urllib3 create_urllib3_context() -> ssl.create_default_context()
# raised PermissionError on AVG's stale keylog handle, the broad `except` at the
# bottom of _send() swallowed it, and notify() returned False. So the cron
# failures could not be alerted on by the very code meant to alert on them.
#
# Guarded import with the old block retained as fallback: notify.py does no
# sys.path manipulation of its own (it relies on callers having added scripts/)
# and is imported by nearly everything, so it must never fail to import.
try:
    _SCRIPTS_DIR = str(Path(__file__).resolve().parent)
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)
    from lib.tls_trust import ensure_os_trust

    ensure_os_trust()
except Exception:  # noqa: BLE001 — lib/ unreachable for this caller
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001 - certifi fallback
        pass
    # Minimum viable form of the keylog guard, inlined so it still applies when
    # the helper is unreachable. See lib/tls_trust.neutralize_keylog.
    try:
        _kl = os.environ.get("SSLKEYLOGFILE")
        if _kl and (os.environ.get("EMPIRE_ALLOW_SSLKEYLOG") or "").strip() != "1":
            if _kl.startswith(("\\\\.\\", "\\\\?\\", "//./", "//?/")):
                os.environ.pop("SSLKEYLOGFILE", None)
    except Exception:  # noqa: BLE001
        pass

# Load .env.agents
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env.agents"

_env_cache: dict[str, str] = {}

# ── Multi-agent bridge routing (2026-07-30) ─────────────────────────────────
#
# Each C-suite agent runs its OWN PM2 Telegram bridge with its OWN bot token in
# its OWN repo: bravo-telegram, maven-telegram, atlas-telegram. Until now
# notify() sent everything through Bravo's bridge regardless of subject, so CC's
# executive channel carried Maven's post failures and Atlas's Stripe syncs
# alongside actual OS health — which is how a channel stops being read.
#
# Routing is by CATEGORY, because the category is already threaded through every
# call site in the fleet. No caller has to change.
#
# THE RULE IS "WHO MUST ACT", NOT "WHOSE DOMAIN IS THE SUBJECT". A first draft
# routed `lead` to Maven on the reasoning that leads are marketing. Reading the
# two live call sites killed that: funnel_sync.py:302 is the "🔥 NEW FUNNEL LEAD"
# push carrying name/email/notes — the operator has to call them — and
# autonomous_agent.py:762 sits inside a function literally named
# `_notify_cc_escalation`. Both need CC, neither needs Maven. A lead and the
# booking that follows it are one operator motion; splitting them across two
# bots halves the funnel. Map from the call sites, not from the taxonomy.
#
# Categories with no live emit site in THIS repo are marked forward-looking:
# they cost nothing, and they pin the contract for when Bravo does emit them.
CATEGORY_OWNER: dict[str, str] = {
    # Maven (CMO) — content, brand, ads, social. Maven ACTS on these.
    "content": "maven",                 # forward-looking: no emit site here yet
    "instagram": "maven",               # forward-looking
    "outreach": "maven",                # live: send_gateway.py:605 daily-cap warning
    # Atlas (CFO) — money in all its forms. Bravo never reports MRR (CLAUDE.md).
    "revenue": "atlas",                 # forward-looking
    "invoice": "atlas",                 # forward-looking
    "stripe": "atlas",                  # forward-looking
    # Bravo (CEO/COO/CTO) — everything the OPERATOR must act on.
    "system": "bravo",
    "email": "bravo",
    "booking": "bravo",                 # live: booking_engine.py:1000,1161
    "lead": "bravo",                    # live: funnel_sync.py:302 (hot inbound
                                        # lead) + autonomous_agent.py:762
                                        # (_notify_cc_escalation). See above.
    "skool-escalation": "bravo",
}
DEFAULT_AGENT = "bravo"

# Operational vocabulary that must never reach the shared OASIS partner group.
# The group is CC + Adon + Bravo + APEX/Knut; Adon is a 50/50 partner on
# PropFlow ONLY and has no reason to see a blocked sending number, a scraper
# stack trace, or a cron failure from CC's internal stack.
#
# Matched against the message BODY, deliberately — the lane flag proves someone
# asked for the group, not that the content belongs there. A message hitting one
# of these terms is rerouted to CC's private DM, never dropped.
#
# Kept narrow and phrase-based rather than single words: "blocked" alone would
# swallow a legitimate partner update ("the PropFlow deal is blocked on
# signature"), and a guard that eats real partner traffic gets switched off.
_GROUP_BLOCKED_TERMS_RE = re.compile(
    r"\b(?:"
    r"getting\s+blocked|campaign\s+pool|failure\s+across|rotate\s+it\s+out"
    r"|tps\s+scrape|domain\s+ping|cron\s+failure|stack\s+trace"
    r"|traceback|scraper\s+log|daemon\s+crash|pm2\s+restart"
    r"|sending\s+number|number\s+blocked|dead[- ]letter"
    r")\b",
    re.IGNORECASE,
)

# Per-agent bot token env keys. Bravo's is the plain TELEGRAM_BOT_TOKEN it has
# always used. Maven's and Atlas's live in THEIR repos by design — separate
# credentials, separate blast radius — so they are usually absent here.
#
# Key names READ FROM THE SIBLINGS' OWN SOURCE, not invented. A first draft
# guessed MAVEN_TELEGRAM_CHAT_ID; Maven's notify.py actually resolves
# MAVEN_TELEGRAM_ALLOWED_USERS (~/CMO-Agent/scripts/notify.py:99-106) and Atlas
# uses ATLAS_TELEGRAM_TOKEN / ATLAS_TELEGRAM_CHAT_ID (cfo/setup_wizard.py).
# Had CC added the key his sibling expects, Bravo would have looked for a
# different one and silently fallen back forever.
AGENT_TOKEN_KEYS: dict[str, tuple[str, str]] = {
    "bravo": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"),
    "maven": ("MAVEN_TELEGRAM_BOT_TOKEN", "MAVEN_TELEGRAM_ALLOWED_USERS"),
    "atlas": ("ATLAS_TELEGRAM_TOKEN", "ATLAS_TELEGRAM_CHAT_ID"),
}


def resolve_agent(category: str, agent: Optional[str] = None) -> str:
    """Which agent's bridge owns this alert. Explicit `agent` always wins."""
    if agent:
        return agent.strip().lower()
    return CATEGORY_OWNER.get((category or "").strip().lower(), DEFAULT_AGENT)


# Categories that are blocked from Telegram by default.
# CC only wants: new leads, DMs needing attention, booked meetings, errors.
DEFAULT_BLOCKED = {"content", "instagram", "system"}
# Categories that send silently (no notification sound)
DEFAULT_SILENT = {"email", "outreach"}


def _load_env() -> dict[str, str]:
    global _env_cache
    if _env_cache:
        return _env_cache
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    _env_cache[key.strip()] = value.strip()
    return _env_cache


def _get_blocked_categories() -> set[str]:
    env = _load_env()
    override = env.get("NOTIFY_BLOCKED_CATEGORIES", "")
    if override:
        return {c.strip().lower() for c in override.split(",") if c.strip()}
    return DEFAULT_BLOCKED


# V3 2026-04-12: Human-readable category labels. No brackets, no all-caps.
# CC's feedback: "the format is gross, I don't know what [REVENUE] means,
# it goes over my head." New format: clean emoji + plain English label.
CATEGORY_PREFIX = {
    "lead": "New Lead",
    "email": "Email",
    "booking": "Booking",
    "content": "Content",
    "revenue": "Revenue",
    "outreach": "Outreach",
    "instagram": "Instagram",
    "system": "System",
    "skool-escalation": "Skool (needs you)",
}


def notify(message: str, category: str = "system", silent: bool = False,
           force: bool = False, dedup_key: Optional[str] = None,
           agent: Optional[str] = None, group: bool = False) -> bool:
    """
    Send a Telegram notification to CC.

    Args:
        message: The notification text
        category: One of lead/email/booking/content/revenue/outreach/instagram/system
        silent: If True, send without sound (disable_notification=True)
        force: If True, bypass category filtering (for critical alerts)
        dedup_key: Pin repeat-suppression to the CONDITION rather than the
            rendered text. Pass this whenever the message embeds something that
            varies between otherwise-identical alerts (a count, a timestamp, a
            branch name) — without it those hash differently every time and
            dedup silently stops working, which is how an alert storm starts.
        agent: Override the owning bridge ("bravo" | "maven" | "atlas").
            Normally leave unset — the category resolves the owner via
            CATEGORY_OWNER. Pass it when the category is generic (a cron
            failure is category="system" but may belong to Maven).
        group: CHANNEL ISOLATION (2026-08-02). False (default) = CC's private
            chat only — every system/harness/lead/agent ping lands on his
            personal channel, and a resolved group chat id is REFUSED (fail
            loud) so operational traffic can never spam the shared team group.
            True = an explicit team broadcast, routed to GROUP_TELEGRAM_CHAT_ID
            (the shared group with Adon/Knut). Nothing reaches the group
            unless a caller passes group=True on purpose.

    Returns:
        True if sent successfully, False otherwise
    """
    global LAST_SUPPRESSED
    LAST_SUPPRESSED = False

    # Hard off-switch for tests / CI — the real root cause of the alert storm
    # was test code reaching the live Telegram send.
    if _notify_disabled():
        return False

    # Block noisy categories unless forced
    if not force and category in _get_blocked_categories():
        return False

    # Idempotency: suppress an identical alert seen within the dedup window, so
    # a per-sweep dead-letter/error alert fires ONCE, not every cron tick.
    # `force` does NOT bypass this — a forced alert is still deduped by content
    # (force is about category muting, not repeat suppression).
    # Scoped BY LANE: the group broadcast and the private chat are different
    # audiences, so one having seen the text says nothing about the other.
    # CONTENT ISOLATION (2026-08-03). The lane check below proves a caller ASKED
    # for the group; it cannot tell whether the CONTENT belongs there. OASIS 🏝️💸
    # is a partner group — CC, Adon, Bravo and APEX/Knut — and a blocked sending
    # number or a scraper stack trace is internal operational noise that Adon
    # should never have to read.
    #
    # Reroute rather than drop. The alert still matters to CC; only its audience
    # was wrong. Dropping it would trade a noise problem for a silence problem,
    # which is the strictly worse failure (see the 34-day funnel-alert
    # misdelivery: alerts that "sent successfully" into the wrong chat).
    if group and _GROUP_BLOCKED_TERMS_RE.search(message or ""):
        matched = _GROUP_BLOCKED_TERMS_RE.search(message or "").group(0)
        print(f"[notify] Suppressed operational noise from shared OASIS group "
              f"chat; rerouting to CC private DM (matched: {matched!r})",
              file=sys.stderr)
        group = False

    lane = "group" if group else "private"
    if not _dedup_should_send(category, message, dedup_key=dedup_key, lane=lane):
        # Suppressed — but only call it "already delivered" if the attempt that
        # opened this window actually LANDED. _dedup_should_send writes its
        # record before the send, so a failed send would otherwise buy silence
        # for the whole backoff window and mask a real alerting outage from the
        # health monitors (Codex [P2], 2026-08-03).
        LAST_SUPPRESSED = _dedup_was_delivered(category, message,
                                               dedup_key=dedup_key, lane=lane)
        return False

    # Auto-silence low-priority categories
    if category in DEFAULT_SILENT:
        silent = True

    env = _load_env()

    if group:
        # Explicit team broadcast lane. Uses Bravo's bot (the bot already in
        # the OASIS group) but targets GROUP_TELEGRAM_CHAT_ID — never the
        # personal allowed-users list.
        token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip() \
            or (env.get("EZRA_TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (env.get("GROUP_TELEGRAM_CHAT_ID") or "").strip()
        if not token:
            print("[notify] TELEGRAM_BOT_TOKEN missing in .env.agents", file=sys.stderr)
            return False
        if not chat_id:
            print("[notify] GROUP_TELEGRAM_CHAT_ID missing — group=True send refused",
                  file=sys.stderr)
            return False
        routed_home = True
        target_agent = DEFAULT_AGENT
    else:
        # Route to the owning agent's bridge (2026-07-30). Maven's and Atlas's
        # tokens live in THEIR repos, so they are normally absent here — in that
        # case fall back to Bravo's bridge with a visible "[for maven]" marker
        # rather than dropping the alert. Degrade loudly, never silently: a
        # misrouted alert CC can see beats a correct one he never gets.
        target_agent = resolve_agent(category, agent)
        tok_key, chat_key = AGENT_TOKEN_KEYS.get(target_agent, AGENT_TOKEN_KEYS[DEFAULT_AGENT])
        token = (env.get(tok_key) or "").strip()
        raw_users = env.get(chat_key, "")
        routed_home = True

        if not token and target_agent != DEFAULT_AGENT:
            routed_home = False
            tok_key, chat_key = AGENT_TOKEN_KEYS[DEFAULT_AGENT]
            token = (env.get(tok_key) or "").strip()
            raw_users = env.get(chat_key, "")

        # 2026-07-10 (main a2a02910, carried through the 2026-07-31 merge): fall
        # back to the EZRA bot creds whenever Bravo's keys are the ones in use.
        # The SunBiz VPS .env.agents only carries EZRA_TELEGRAM_BOT_TOKEN /
        # EZRA_TELEGRAM_CHAT_ID (the pair ezra-telegram-bridge + scrubber use), so
        # every notify() call there — including notify_daemon_crash() from the pm2
        # daemons — was a silent no-op for months. Primary keys still win.
        if tok_key == AGENT_TOKEN_KEYS[DEFAULT_AGENT][0]:
            token = token or (env.get("EZRA_TELEGRAM_BOT_TOKEN") or "").strip()
            raw_users = raw_users or env.get("EZRA_TELEGRAM_CHAT_ID", "")
        # V2.1 2026-04-11: Guarded chat_id parsing. Old code used
        # `.split(",")[0].strip()` which returned "" on empty/whitespace env
        # and silently failed at Telegram send. Now we filter valid IDs and
        # log a visible error when none are found.
        chat_ids = [c.strip() for c in raw_users.split(",") if c.strip()]

        if not token:
            extra = " / EZRA_TELEGRAM_BOT_TOKEN" if tok_key == AGENT_TOKEN_KEYS[DEFAULT_AGENT][0] else ""
            print(f"[notify] {tok_key}{extra} missing in .env.agents", file=sys.stderr)
            return False
        if not chat_ids:
            extra = " / EZRA_TELEGRAM_CHAT_ID" if chat_key == AGENT_TOKEN_KEYS[DEFAULT_AGENT][1] else ""
            print(f"[notify] {chat_key}{extra} empty or malformed in .env.agents", file=sys.stderr)
            return False
        chat_id = chat_ids[0]

        # CHANNEL ISOLATION GUARD (2026-08-02). Telegram group/channel ids are
        # negative; a personal chat id is positive. If the personal lane ever
        # resolves to a group id — e.g. the group id got appended to
        # TELEGRAM_ALLOWED_USERS — every system alert, harness ping and lead
        # notification would spam the shared team group. Refuse loudly instead.
        # The ONLY way to reach a group is the explicit group=True lane above.
        if chat_id.startswith("-"):
            print(
                "[notify] resolved chat is a GROUP id on the personal lane — "
                "refusing send. Operational pings go to CC's private chat; "
                "pass group=True for an explicit team broadcast.",
                file=sys.stderr,
            )
            return False

    try:
        import requests
    except ImportError:
        return False

    # V3 2026-04-12: Clean human-readable format.
    # Old: "[REVENUE] Stripe Revenue Sync: Stripe sync complete.\n  Inserted: 0 new event(s)\n  Skipped: 4 duplicate(s)\n-- 17:34"
    # New: "Revenue\n$800 payment from a retainer client\n\n12:34 PM"
    prefix = CATEGORY_PREFIX.get(category, "Bravo")
    # When an alert belongs to Maven or Atlas but their bridge token is not
    # configured here, it lands on Bravo's channel — say so in the message.
    # An unmarked misroute is how CC ends up believing his executive channel is
    # the only channel, which is the state this routing exists to end.
    if not routed_home:
        prefix = f"{prefix}  ·  [for {target_agent} — bridge not configured in this repo]"
    timestamp = datetime.now().strftime("%#I:%M %p")  # 12-hour format, no leading zero
    full_message = f"{prefix}\n{message}\n\n{timestamp}"
    if len(full_message) > 4096:
        full_message = full_message[:4093] + "..."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": full_message,
        "parse_mode": "HTML",
        "disable_notification": silent,
    }

    # Bounded transport retry (2026-07-28). The AV TLS-scanning filter driver on
    # this box intermittently aborts the outbound socket mid-handshake, which
    # requests surfaces as ConnectionError("Connection aborted.", PermissionError(13)).
    # A single abort used to fail the whole cron job ("Daily Bravo Brief -> FAILED"),
    # which then retried the ENTIRE job 5 times — so one dropped packet cost five
    # brief re-computations. Retrying just the POST costs ~2s and absorbs it.
    #
    # Transport errors only. A well-formed HTTP response with ok=false (403 bot
    # blocked, 429 rate limit) is a semantic answer, not a transient fault —
    # retrying those would spam Telegram and worsen a 429.
    #
    # ReadTimeout is deliberately EXCLUDED: it means the request was delivered
    # and we simply never saw the reply, so Telegram may well have accepted and
    # posted the message. Retrying that is the one path that double-sends to CC
    # (there is no Telegram-side idempotency key). Connect-phase failures —
    # which is what the AV filter driver actually produces — never reached the
    # API, so replaying them is safe.
    transient = (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout)
    max_attempts = 3
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=5,  # V2 2026-04-11: 10s -> 5s to prevent scheduler loop stalls
            )
            ok = resp.json().get("ok", False)
            if not ok:
                # Log to stderr so scheduler's PM2 logs surface delivery failures
                # (e.g., 403 bot blocked, 429 rate limit). Fail-closed visibility.
                err_info = resp.json().get("description", f"HTTP {resp.status_code}")
                print(f"[notify] Telegram send failed: {err_info}", file=sys.stderr)
            else:
                # Only a LANDED message earns the suppression window. See
                # _dedup_mark_delivered.
                _dedup_mark_delivered(category, message, dedup_key=dedup_key, lane=lane)
            return ok
        except transient as exc:
            last_exc = exc
            if attempt < max_attempts:
                # SECURITY: redact before logging — see the handler below.
                msg = str(exc).replace(token, "[REDACTED:BOT_TOKEN]")
                print(
                    f"[notify] Telegram transport error (attempt {attempt}/{max_attempts}), "
                    f"retrying: {msg}",
                    file=sys.stderr,
                )
                time.sleep(0.5 * attempt)  # 0.5s, then 1.0s
                continue
            break
        except Exception as exc:
            last_exc = exc
            break

    # Visible failure beats silent failure. PM2 logs catch this.
    # SECURITY (2026-07-21): requests exceptions embed the request URL,
    # which contains the bot token — redact before printing so a transient
    # network error can't leak the credential into PM2 logs or operator
    # context (it did exactly that during the go-live watch smoke test).
    msg = str(last_exc).replace(token, "[REDACTED:BOT_TOKEN]")
    print(f"[notify] Telegram send exception: {msg}", file=sys.stderr)
    return False


def self_test_message(group: bool = False) -> str:
    """The text `notify.py --test` sends.

    A module-level function, not an f-string buried in __main__, so it can be
    asserted on without firing a real Telegram at CC — which is how the previous
    version shipped unverified.

    2026-08-03: it used to read "Routing check (private lane) — <timestamp>" and
    nothing else, so CC got unexplained pings from an agent checking its own
    plumbing with no way to tell them from a real alert. A diagnostic that looks
    like an incident is a bad diagnostic. The timestamp stays because unique text
    is what keeps the dedup window from swallowing the check.
    """
    lane = "group broadcast" if group else "private"
    return ("🧪 SELF-TEST — ignore.\n"
            f"Bravo verifying the {lane} Telegram lane still delivers. Nothing "
            f"is wrong; this is only sent by a human or an agent running "
            f"`notify.py --test`, never by an automation.\n"
            f"{datetime.now().isoformat(timespec='seconds')}")


def notify_result(message: str, **kwargs) -> tuple[bool, str]:
    """notify() with the REASON attached: (ok, "sent" | "suppressed" | "failed").

    notify() returns a bare bool, and False means two opposite things —
    suppressed (CC was told recently) and failed (CC was told nothing). Reading
    them as one is what turned cron_health_check into a failing cron that
    reported itself, on 2026-08-03.

    Callers asking "is CC aware of this condition?" should test
    `reason in DELIVERED_REASONS` rather than the bool. Matches the (ok, detail)
    shape the rest of the fleet already uses (cron_health_check.telegram_alert,
    send_gateway). notify() keeps its bool contract for the ~50 call sites that
    only care whether a message went out right now.
    """
    ok = notify(message, **kwargs)
    if ok:
        return True, "sent"
    return False, "suppressed" if LAST_SUPPRESSED else "failed"


def notify_error(engine: str, error: str, agent: Optional[str] = None,
                 stage: Optional[str] = None) -> bool:
    """Send an error alert — always with sound, always delivered.

    force=True added 2026-07-29. Without it this function was a no-op: it sends
    on category 'system', 'system' is in DEFAULT_BLOCKED, and notify() drops
    blocked categories unless forced. So EVERY cron failure alert since the
    category filter shipped was silently discarded — the scheduler dutifully
    called notify_error() on each failed job and nothing ever reached CC. He
    found the 25h inbound-email outage by noticing his own inbox was stale.

    Compare notify_daemon_crash() below, which has passed force=True since
    2026-05-16 for exactly this reason. Errors are operational-critical; the
    block list exists to mute routine chatter, not failures.

    Dedup still applies (notify.py DEDUP_WINDOW_SEC) — force bypasses the
    category filter, not the repeat suppression, so a stuck job pings hourly
    rather than every tick.

    `stage` (2026-07-30) separates DIFFERENT alerts about the same engine.
    Without it the scheduler's two call sites collided on one identity: the
    routine per-tick page and the "this job has failed twice / has given up"
    escalation shared `engine_error:{job}`, so the noisy first alert won the
    dedup slot and SUPPRESSED the one that actually says the job is broken.
    The anti-noise design was inverted in practice — CC got the noise and not
    the signal. Distinct stages are distinct incidents; keep them distinct.
    """
    key = f"engine_error:{engine}" + (f":{stage}" if stage else "")
    return notify(f"{engine} error: {error}", category="system",
                  silent=False, force=True, agent=agent,
                  # Pin to the failing engine, not the error text. A cron whose
                  # message carries a changing count or timestamp would
                  # otherwise hash differently each tick and defeat dedup
                  # entirely — the review-loop storm in miniature.
                  dedup_key=key)


def notify_daemon_crash(daemon: str, error: str, tick_id: str | None = None) -> bool:
    """Daemon-level crash alert. Always bypasses the category block list.

    Round 3 R3-11 (2026-05-16): the long-running PM2 daemons
    (sequence_runner, lender_response_classifier, event_router) all
    had top-level except clauses that logged to stdout and swallowed
    the failure. PM2 would restart
    the process but CC wouldn't know anything had crashed. This
    helper closes that gap — wraps daemon tick errors with a Telegram
    push the operator sees in real time.

    Category 'system' is normally blocked, but daemon crashes are
    operational-critical so we pass force=True.

    DEDUP CORRECTED 2026-07-30. This docstring used to claim "the notify()
    rate-limiter still applies (no spam if a daemon restart-loops)". It did
    NOT: the message embeds `tick_id`, which changes every tick, so a
    crash-looping daemon produced a different hash every time and dedup never
    fired once. Same defect that produced the overnight review-loop storm —
    and here the comment actively asserted protection that did not exist,
    which is worse than no comment. dedup_key now pins suppression to the
    DAEMON, so a restart-loop alerts once and then backs off 1h/2h/4h/8h.

    Returns True on successful Telegram delivery, False on miss.
    Always best-effort — daemon crash handling must not depend on
    Telegram availability.
    """
    msg = f"Daemon crashed: {daemon}"
    if tick_id:
        msg += f" (tick {tick_id})"
    msg += f"\n\nError: {error[:500]}"
    try:
        return notify(msg, category="system", silent=False, force=True,
                      dedup_key=f"daemon_crash:{daemon}")
    except Exception:
        # Telegram itself can fail (network, token expiry); don't let
        # a notify failure cascade into the daemon's own error path.
        return False


def notify_voice(audio_bytes: bytes, *, caption: str | None = None,
                 mime: str = "audio/ogg", filename: str = "voice.ogg") -> bool:
    """Ship a voice/audio blob to CC's Telegram via sendVoice.

    Phase 10.2 extracted from scripts/morning_powwow.py — every future
    voice-driven automation (Morning Pow Wow, future Daily Brief voice
    variant, etc.) should go through this helper so the multipart upload
    + chat-id resolution + auth handling lives in one place. Mirrors the
    notify() / notify_daemon_crash() pattern: best-effort, never raises.

    Args:
        audio_bytes: raw audio (Telegram accepts OGG-Opus for sendVoice).
        caption: optional text caption attached to the voice note.
        mime: MIME type sent in the multipart part. "audio/ogg" works for
            Telegram sendVoice with Opus codec.
        filename: name shown to Telegram for the upload. Cosmetic.

    Returns True if at least one chat received the voice note. False on
    any failure (missing env, network, Telegram rejection).
    """
    import urllib.request

    env = _load_env()
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    raw_users = env.get("TELEGRAM_ALLOWED_USERS") or ""
    chat_ids = [c.strip() for c in raw_users.split(",") if c.strip()]
    if not token:
        print("[notify_voice] TELEGRAM_BOT_TOKEN missing", file=sys.stderr)
        return False
    if not chat_ids:
        print("[notify_voice] TELEGRAM_ALLOWED_USERS empty", file=sys.stderr)
        return False

    boundary = "----notifyvoice"
    ok_count = 0
    for chat_id in chat_ids:
        try:
            parts: list[bytes] = [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode("utf-8"),
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="voice"; filename="{filename}"\r\n'
                    f"Content-Type: {mime}\r\n\r\n"
                ).encode("utf-8"),
                audio_bytes,
                b"\r\n",
            ]
            if caption:
                parts.extend([
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode("utf-8"),
                ])
            parts.append(f"--{boundary}--\r\n".encode("utf-8"))
            data = b"".join(parts)
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendVoice",
                data=data,
                headers={"content-type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                resp_body = json.loads(resp.read().decode("utf-8"))
            if resp_body.get("ok"):
                ok_count += 1
            else:
                print(f"[notify_voice] sendVoice rejected for {chat_id}: {resp_body}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[notify_voice] sendVoice exception for {chat_id}: {exc}", file=sys.stderr)
    return ok_count > 0


# Quick test
if __name__ == "__main__":
    # python scripts/notify.py "message"            → CC's private chat (forced)
    # python scripts/notify.py --test               → routing check ping, private lane
    # python scripts/notify.py --group "message"    → explicit team broadcast
    # python scripts/notify.py --test --group       → routing check ping, group lane
    _args = sys.argv[1:]
    _test = "--test" in _args
    _group = "--group" in _args
    _args = [a for a in _args if a not in ("--test", "--group")]
    if _test:
        _msg = self_test_message(_group)
    else:
        _msg = " ".join(_args) if _args else "Bravo notification system online."
    # CLI sends are explicit operator action: force past the category block
    # list (category "system" is blocked for automation, not for a human
    # typing a command — the old CLI always printed Sent: False).
    result = notify(_msg, category="system", force=True, group=_group)
    lane = "group (GROUP_TELEGRAM_CHAT_ID)" if _group else "private (TELEGRAM_ALLOWED_USERS)"
    print(f"Sent: {result}  ·  lane: {lane}")
