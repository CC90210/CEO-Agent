"""
Inbound Classifier — the second half of V5.6's chokepoint.

V5.6 made outbound coherent by forcing every send through send_gateway.
Inbound was still split across engines: IMAP in email_engine, Playwright
in instagram_engine, the N8N qualifier, skool_engine's crawler — each
with different logic and no shared sentiment or intent understanding.

This module is the single classification pipeline for every inbound
event. Given raw content + channel, it produces a structured record
that writes to lead_interactions AND publishes an event on the bus
so subscribers (the autonomous agent, Atlas, Maven) can react.

USAGE FROM PYTHON
-----------------
    from inbound_classifier import classify, record_inbound

    result = classify(
        content="yes definitely book me in for wednesday",
        channel="email",
        subject="Re: Your HVAC scheduling proposal",
        from_identity="jane@acme.example",
    )
    # result = {
    #   "sentiment": "positive",
    #   "intent": "booking",
    #   "priority": "hot",
    #   "stage_signal": "escalate_to_engaged",
    #   "confidence": 0.92,
    #   "suggested_action": "draft_booking_confirmation",
    #   "escalation_reason": None,
    # }

    record_inbound(
        classification=result,
        channel="email",
        from_identity="jane@acme.example",
        content="yes definitely book me in for wednesday",
        subject="Re: ...",
        thread_id=None,
        metadata={"message_id": "..."},
    )
    # writes to lead_interactions + publishes agent_events row + returns UUID

CLI
---
    python scripts/inbound_classifier.py classify --channel email \\
        --content "not interested" --from jane@acme.example --json
    python scripts/inbound_classifier.py backfill --since 2026-04-01
    python scripts/inbound_classifier.py stats --json

DESIGN
------
1. Claude Haiku as classifier — cheap (~$0.0001/call), fast (~300ms), and
   much more accurate than the keyword-based placeholder in context_builder.
2. Structured output. Haiku returns strict JSON with fixed enums; we never
   guess or free-text.
3. Fail-closed. If Haiku is unreachable or returns malformed JSON, we fall
   back to the keyword classifier from context_builder AND mark the record
   with confidence=0.3 so downstream code knows it's a degraded read.
4. Every classification writes to agent_events as inbound.classified —
   subscribers can act immediately (e.g., auto-draft a booking confirmation).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# TLS setup (added 2026-07-29). This module owns its own get_supabase() but had
# NO trust setup — it only ever worked because email_engine.py imports
# lib.tls_trust before importing this one. Its CLI entrypoint, and
# email_brain's store_draft_row / handoff_to_atlas (which import get_supabase
# from here), all reached SSL unprotected. That is the exact call that failed
# 40/40 under the poisoned scheduler environment.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# Notify import. Fixes a latent bug: _notify_platform_alert() called
# `_telegram_notify(...)` which was never imported/defined → NameError on
# every platform alert. Canonical pattern mirrors send_gateway.py:193.
try:
    from notify import notify as _telegram_notify  # noqa: F401
except Exception:  # pragma: no cover - notify import is best-effort
    def _telegram_notify(*_a: Any, **_kw: Any) -> bool:  # type: ignore[misc]
        return False


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
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def get_supabase(env: Optional[dict[str, str]] = None):
    e = env if env is not None else load_env()
    url = e.get("BRAVO_SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (e.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY"))
    from supabase import create_client
    return create_client(url, key)


# ---- Shared LLM-output helper -----------------------------------------------

def strip_code_fence(text: Any) -> str:
    """Strip a leading ```lang fence and trailing ``` from an LLM response and
    trim surrounding whitespace. One home for a pattern that otherwise gets
    copy-pasted into every JSON-parsing call site."""
    t = str(text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


# ---- Classification schema --------------------------------------------------

VALID_SENTIMENTS = {"positive", "neutral", "negative", "mixed"}
VALID_INTENTS = {
    "booking",       # they want to schedule a call / meeting
    "pricing",       # asking about cost / pricing
    "objection",     # pushing back on offer, price, or fit
    "info_request",  # asking for more information
    "out_of_office",
    "unsubscribe",   # explicit opt-out
    "spam_bounce",   # mailer-daemon / noise
    "noise",         # off-topic, auto-reply, confirmation email, etc.
    "reply_positive",  # confirming / agreeing but not a specific ask
    "reply_negative",  # declining / disengaging but not unsubscribing
    "referral",      # referring someone else
    "platform_alert", # notification from a platform (Stripe, Vercel, etc.)
    "tech_alert",     # technical issue: webhook failure, build error, etc.
    "other",
}
VALID_PRIORITY = {"hot", "warm", "cold", "low"}
VALID_STAGE_SIGNALS = {
    "escalate_to_engaged",
    "escalate_to_warm",
    "regress_to_dormant",
    "escalate_to_active_client",
    "mark_lost",
    "hold",
}
VALID_ACTIONS = {
    "draft_booking_confirmation",
    "draft_pricing_reply",
    "draft_objection_handler",
    "draft_info_reply",
    "escalate_to_cc",
    "add_to_nurture",
    "mark_unsubscribed",
    "ignore",
    "hold_for_review",
    "notify_cc_telegram",  # fire a Telegram alert to CC
}


# ---- Platform sender pre-routing --------------------------------------------
# 2026-05-11: Stripe webhook-failure email was misrouted to Atlas as a business
# expense because the classifier saw "Stripe" and didn't distinguish technical
# vs. financial. This table catches known platform senders BEFORE Haiku and
# routes them by content-aware subcategory.

# Money TOPICS, for ROUTING only — deliberately NOT the same question as
# _has_transaction_evidence(), which asks "did money actually move?" and gates
# expense BOOKING. An "invoice is available" or "billing account past due"
# notice must reach Atlas/CC as financial, but nothing has been charged yet, so
# booking it would invent a ledger row. Keep the two predicates separate:
# widening this one is safe, widening that one costs real money.
#
# DO NOT merge this with email_playbook.MONEY_SIGNALS. That tuple answers a
# third question — "is this thread commercially sensitive, so never auto-reply?"
# — and is over-broad on purpose ("price", "pricing", "cost", "monthly",
# "how much"), because its false positives cost nothing but a withheld
# auto-reply. Routing on it would send every pricing newsletter to finance:
# measured 2026-08-01, MONEY_SIGNALS matches the Lindy price-cut blast, a
# "$49/mo" pricing page, and a monthly usage report, none of which this regex
# matches. That blast being filed as a business expense IS the 2026-07-29
# incident this module's tests exist for.
_BILLING_TOPIC_RE = re.compile(
    r"\b(?:"
    r"invoice|billing\s+account|past\s+due|overdue|unpaid"
    r"|payment\s+(?:method|info(?:rmation)?|declined|failed|issue|problem)"
    r"|invalid\s+payment|update\s+your\s+payment|card\s+(?:declined|expired)"
    r"|subscription\s+(?:cancell?ed|expir|renew)|receipt|statement"
    r"|charged|refund|credit\s+card"
    r")",
    re.IGNORECASE,
)

# The integration itself is broken — outranks _BILLING_TOPIC_RE.
#
# Added 2026-08-01 after a Codex adversarial review caught a regression the
# billing override introduced: a real Stripe webhook-failure email NAMES the
# events it could not deliver, and those names are billing events
# ("invoice.payment_failed", "charge.refunded"). So an outage notification
# matched the billing regex and was routed to finance instead of paging ops —
# strictly worse than the misrouting it was meant to fix, and the exact class
# of failure _platform_prefilter was built for in 2026-05.
#
# Every term here names INFRASTRUCTURE, never a bare failure verb. "failed"
# alone would match "payment failed" and re-break the case above; the failure
# words are anchored to build/deploy/pipeline nouns for the same reason.
_INTEGRATION_FAILURE_RE = re.compile(
    r"\b(?:"
    r"webhook|endpoint|delivery\s+attempt|api\s+error|error\s+rate"
    r"|quota|rate\s*limit|throttl"
    r"|(?:build|deploy(?:ment)?|pipeline)\s+(?:has\s+)?fail"
    r"|outage|incident|degraded\s+performance|downtime|unreachable"
    r"|ssl|certificate\s+expir|dns\s+(?:record|config)"
    r")",
    re.IGNORECASE,
)

PLATFORM_SENDERS: dict[str, dict[str, Any]] = {
    # domain-suffix -> default routing metadata
    "stripe.com": {
        "platform": "stripe",
        "default_route": "financial",   # receipts, invoices, payouts
        # these subject keywords override to technical routing
        "tech_keywords": [
            "webhook", "endpoint", "delivery", "failed", "error",
            "api", "integration", "developer", "test mode",
            "ssl", "certificate", "deprecated", "migration",
        ],
    },
    "vercel.com": {
        "platform": "vercel",
        "default_route": "technical",
        "tech_keywords": ["deploy", "build", "error", "domain", "ssl"],
    },
    "github.com": {
        "platform": "github",
        "default_route": "technical",
        "tech_keywords": ["pull request", "issue", "security", "dependabot", "action"],
    },
    "supabase.io": {
        "platform": "supabase",
        "default_route": "technical",
        "tech_keywords": ["migration", "webhook", "edge", "function", "maintenance"],
    },
    "supabase.com": {
        "platform": "supabase",
        "default_route": "technical",
        "tech_keywords": ["migration", "webhook", "edge", "function", "maintenance"],
    },
    "google.com": {
        "platform": "google",
        "default_route": "technical",
        # "billing" was removed 2026-08-01: it is a MONEY word, and because a
        # tech-keyword hit hard-routes to ops_technical without ever consulting
        # the model, listing it here guaranteed that every Google invoice and
        # past-due notice was classified technical_support and withheld from
        # Atlas. "workspace" stays, but is now overridable by _BILLING_TOPIC_RE
        # (see _platform_prefilter) — "Google Workspace: your invoice is
        # available" matched on "workspace" and was misrouted the same way.
        "tech_keywords": ["cloud", "api", "quota", "alert", "workspace"],
    },
    "googlecloud.com": {
        "platform": "google_cloud",
        "default_route": "technical",
        "tech_keywords": [],
    },
    "cloudflare.com": {
        "platform": "cloudflare",
        "default_route": "technical",
        "tech_keywords": [],
    },
    "n8n.io": {
        "platform": "n8n",
        "default_route": "technical",
        "tech_keywords": ["workflow", "execution", "error", "credential"],
    },
}


def _platform_prefilter(
    from_identity: Optional[str],
    subject: Optional[str],
    content: Optional[str],
) -> Optional[dict]:
    """Check if the sender is a known platform. Returns a pre-built
    classification dict if matched, None otherwise.

    Logic:
    1. Match sender domain against PLATFORM_SENDERS.
    2. Check subject + content for tech_keywords.
    3. If any tech keyword hits -> route as tech_alert (ops/technical).
       Otherwise -> route with the platform's default_route.
    4. Always set suggested_action=notify_cc_telegram so CC gets pinged.
    """
    if not from_identity:
        return None
    sender_lower = from_identity.strip().lower()
    domain = sender_lower.rpartition("@")[2] if "@" in sender_lower else ""
    if not domain:
        return None

    matched_config: Optional[dict[str, Any]] = None
    for suffix, config in PLATFORM_SENDERS.items():
        if domain == suffix or domain.endswith("." + suffix):
            matched_config = config
            break
    if matched_config is None:
        return None

    # Check for technical keywords in subject + content
    haystack = ((subject or "") + " " + (content or "")[:2000]).lower()
    tech_kws = matched_config.get("tech_keywords", [])
    is_technical = any(kw in haystack for kw in tech_kws)

    # Precedence: a broken integration > a bill > platform tech keywords >
    # default_route. The first two are the ones that must not swap: an outage
    # held for finance review pages nobody, which is worse than a bill filed
    # as ops.
    is_failure = bool(_INTEGRATION_FAILURE_RE.search(haystack))
    is_billing = bool(_BILLING_TOPIC_RE.search(haystack)) and not is_failure
    # A detected failure routes to ops on its own authority, without needing a
    # hit in the platform's own tech_keywords list. Those lists are per-vendor
    # and incomplete — google's has no "webhook" — and stripe.com's
    # default_route is "financial", so a failure that fell through to the
    # default would land in finance. Belt and braces on the worse direction.
    is_technical = is_technical or is_failure

    platform = matched_config["platform"]
    if is_billing:
        # A money topic outranks BOTH the tech keywords and a "technical"
        # default_route. Platform mail routinely says "cloud"/"workspace"/"api"
        # in the boilerplate of a genuine invoice, and any tech-keyword hit
        # skips the model entirely (see classify_category), so without this
        # branch an unpaid bill is filed as a tech alert and never reaches
        # Atlas. Routing "financial" here does NOT assert this is a booked
        # transaction — that route is the one the prefilter deliberately hands
        # to the model, because WHO sent it can't tell you whether THIS message
        # is a receipt. Booking stays gated on _has_transaction_evidence().
        intent = "platform_alert"
        priority = "hot" if is_technical else "warm"
        route_target = "financial"
        notes = (f"Billing/invoice notification from {platform} — money topic "
                 f"overrides technical routing. Model decides if it is a "
                 f"transaction; Atlas may process.")
    elif is_technical:
        intent = "tech_alert"
        priority = "hot"
        route_target = "ops_technical"
        notes = (f"Technical alert from {platform}: matched tech keywords in subject/body. "
                 "Route to CC for ops attention, NOT to Atlas/financial.")
    else:
        default_route = matched_config["default_route"]
        if default_route == "financial":
            intent = "platform_alert"
            priority = "warm"
            route_target = "financial"
            notes = f"Financial notification from {platform} (receipt/invoice/payout). Atlas may process."
        else:
            intent = "platform_alert"
            priority = "warm"
            route_target = "ops_technical"
            notes = f"Platform notification from {platform}. Informational."

    return {
        "sentiment": "neutral",
        "intent": intent,
        "priority": priority,
        "stage_signal": "hold",
        "confidence": 0.95,
        "suggested_action": "notify_cc_telegram",
        "key_phrase": (subject or "")[:200],
        "notes": notes,
        "platform_prefilter": True,
        "platform": platform,
        "route_target": route_target,
    }


def _keyword_fallback(content: str) -> dict:
    """Cheap fallback when Haiku is unavailable. Degraded mode."""
    lower = (content or "").lower()
    positive = any(kw in lower for kw in ("yes", "interested", "book", "schedule", "sounds good", "let's do"))
    negative = any(kw in lower for kw in ("not interested", "unsubscribe", "no thanks", "stop", "remove me"))
    ooo = any(kw in lower for kw in ("out of office", "on vacation", "i'm away"))
    bounce = any(kw in lower for kw in ("mailer-daemon", "delivery status", "undeliverable"))

    if bounce:
        return {"sentiment": "neutral", "intent": "spam_bounce",
                "priority": "low", "stage_signal": "hold",
                "suggested_action": "ignore", "confidence": 0.4,
                "fallback": True}
    if ooo:
        return {"sentiment": "neutral", "intent": "out_of_office",
                "priority": "cold", "stage_signal": "hold",
                "suggested_action": "ignore", "confidence": 0.5,
                "fallback": True}
    if negative and ("unsubscribe" in lower or "stop" in lower):
        return {"sentiment": "negative", "intent": "unsubscribe",
                "priority": "low", "stage_signal": "mark_lost",
                "suggested_action": "mark_unsubscribed", "confidence": 0.7,
                "fallback": True}
    if negative:
        return {"sentiment": "negative", "intent": "reply_negative",
                "priority": "cold", "stage_signal": "regress_to_dormant",
                "suggested_action": "add_to_nurture", "confidence": 0.4,
                "fallback": True}
    if positive:
        return {"sentiment": "positive", "intent": "reply_positive",
                "priority": "hot", "stage_signal": "escalate_to_engaged",
                "suggested_action": "escalate_to_cc", "confidence": 0.5,
                "fallback": True}
    return {"sentiment": "neutral", "intent": "other",
            "priority": "cold", "stage_signal": "hold",
            "suggested_action": "hold_for_review", "confidence": 0.3,
            "fallback": True}


# ---- 4-brain category classifier (native n8n migration) ---------------------
# Replaces the langchain `textClassifier` node in the n8n "OASIS Inbound
# Qualifier (Bravo Aware)" workflow. Same 4-category taxonomy, but driven by
# the subscription Claude CLI (Haiku) instead of a metered OpenAI key. The
# category feeds email_brain.route(), which decides draft/send/label/hand-off.

VALID_CATEGORIES: frozenset[str] = frozenset({
    "technical_support",    # existing clients needing help with deliverables
    "business_opportunity",  # new leads, warm/cold replies, referrals, intros
    "financial_legal",      # invoices, receipts, payments, tax, contracts, legal
    "low_priority",         # newsletters, no-reply, platform tech-alerts → archive
})

# Ordered alias map: first hit wins. Financial/business/technical are checked
# before low_priority so a Stripe *payment* receipt lands in financial_legal
# even though it comes from a no-reply address (matches the n8n rubric).
_CATEGORY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("financial_legal", ("financial", "legal", "invoice", "receipt", "finance")),
    ("business_opportunity", ("business opportunit", "opportunit", "lead", "sales")),
    ("technical_support", ("technical support", "client technical", "tech support", "support")),
    ("low_priority", ("low priority", "archive", "spam", "newsletter", "trash")),
)


def normalize_category(raw: Any) -> str:
    """Clamp any LLM string / n8n label / loose text to one canonical category.
    Unknown → 'low_priority'; the autonomy layer (email_brain.decide_action)
    fail-safes uncertain low-confidence reads to human review, so archiving is
    never triggered on an unknown alone."""
    if not raw:
        return "low_priority"
    s = str(raw).strip().lower()
    if s in VALID_CATEGORIES:
        return s
    for canon, needles in _CATEGORY_ALIASES:
        if any(n in s for n in needles):
            return canon
    return "low_priority"


CATEGORY_SYSTEM_PROMPT = """You are an inbound email classifier for OASIS AI
Solutions (operator: Conaugh McKenna / "CC"). Read the email and pick exactly
ONE category. Judge by WHO is sending and WHAT action it requires.

Categories:
1. Client Technical Support — existing OASIS clients needing help with their
   deliverables, automations, access, outages, bugs, or how-to questions.
2. Business Opportunities — new leads, cold/warm-email replies, referrals,
   introductions, discovery-call requests, inbound interest, anyone CC has been
   emailing in outreach. Usually needs a reply toward booking a call.
3. Financial & Legal — a TRANSACTION that already happened or is formally due,
   or a binding legal document. Concretely: invoices, receipts, bank/card
   statements, Stripe payment notifications (payouts, charges, refunds,
   successful payments), subscription renewal CONFIRMATIONS, CRA / Revenu
   Québec / tax documents, signed contracts, legal notices.

   THE TEST: has money actually moved, or is a specific amount formally owed?
   If yes -> Financial & Legal. If the email merely TALKS about money -> not.

   NOT Financial & Legal:
     - a vendor announcing new or lower pricing ("Lindy is cutting prices by 4x
       on average") — that is marketing, no matter how much money it mentions;
     - plan/tier comparisons, upsells, upgrade nudges, discount promos;
     - product launches that quote a price;
     - webhook errors, API failures, deploy errors, or any developer/technical
       alert from Stripe / Vercel / GitHub / Supabase — those are technical.
   All of the above are Low Priority & Archive (or Client Technical Support if
   an OASIS client is actually blocked).

4. Low Priority & Archive — newsletters, marketing, promotions, pricing and
   product announcements, automated notifications, no-reply updates, platform
   TECHNICAL alerts (webhook failures, deploy errors, API deprecation),
   anything needing no response.

Getting #3 wrong is expensive in BOTH directions: a missed receipt loses a
deductible expense, and a marketing blast misfiled as Financial books a fake
expense in the operator's ledger. When money is discussed but no transaction
occurred, choose Low Priority & Archive.

Output ONLY a JSON object, no prose, no markdown:
{"category": "<one of: Client Technical Support | Business Opportunities | Financial & Legal | Low Priority & Archive>", "confidence": <0.0-1.0>}"""


def _default_category_runner(prompt: str, system: Optional[str] = None,
                             model: str = "haiku", timeout: int = 60) -> Optional[str]:
    """Subscription Claude CLI — never the metered ANTHROPIC_API_KEY."""
    from lib.claude_cli import run_claude_cli
    return run_claude_cli(prompt, system=system, model=model, timeout=timeout)


def _build_category_user_msg(content: str, subject: Optional[str],
                             from_identity: Optional[str],
                             is_bulk: bool = False) -> str:
    parts = []
    if from_identity:
        parts.append(f"From: {from_identity}")
    if subject:
        parts.append(f"Subject: {subject}")
    if is_bulk:
        # Hand the model the deterministic signal rather than hoping it infers
        # "marketing" from tone. Bulk senders must set List-Unsubscribe;
        # transactional mail (invoices, receipts, resets) essentially never does.
        parts.append(
            "Delivery: this message carries a List-Unsubscribe header, i.e. it "
            "was sent as BULK/MARKETING mail. Transactional mail (real invoices, "
            "receipts, payment confirmations) almost never carries this header. "
            "Weigh this heavily against Financial & Legal."
        )
    parts.append("")
    parts.append("Body:")
    parts.append((content or "")[:4000])
    return "\n".join(parts)


def _parse_category_response(raw: str, evidence_text: str = "",
                             is_bulk: bool = False) -> Optional[dict]:
    """Parse a runner response into {category, confidence, fallback, notes}.

    Tolerant: accepts a JSON object OR a bare category label. Returns None only
    when the input is empty/whitespace.

    Two DETERMINISTIC corrections are applied on top of the model's answer,
    because the model is not stable enough to be the only vote. Measured
    2026-07-29 on the exact Lindy price-cut email: identical input returned
    "Low Priority & Archive" @0.95 on one call and "Financial & Legal" @0.6 on
    the next. Money decisions cannot ride on that.

      1. MARKETING VETO. A bulk-sent message (List-Unsubscribe header) or one
         written in pricing-announcement language may NOT be Financial & Legal
         unless there is actual transaction evidence. A vendor telling CC what
         things cost is not a vendor charging CC.
      2. EVIDENCE-WEIGHTED CONFIDENCE. When the model omits a confidence, the
         old code invented a flat 0.6 — which sits below the hand-off threshold,
         so genuine receipts silently failed to book (a missed deductible), while
         still being high enough to look considered. Derive it from evidence
         instead: transaction evidence present -> confident; absent -> not.
    """
    text = strip_code_fence(raw)
    if not text:
        return None
    category_raw: Any = text
    confidence: Optional[float] = None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            category_raw = obj.get("category", "")
            if obj.get("confidence") is not None:
                try:
                    confidence = float(obj["confidence"])
                except (TypeError, ValueError):
                    confidence = None
    except (json.JSONDecodeError, ValueError):
        pass  # treat the whole string as a bare label

    category = normalize_category(category_raw)
    has_txn = _has_transaction_evidence(evidence_text)
    marketing = bool(_MARKETING_RE.search(evidence_text))
    note = ""

    if category == "financial_legal" and not has_txn and (is_bulk or marketing):
        why = "bulk/List-Unsubscribe" if is_bulk else "pricing-announcement language"
        category = "low_priority"
        note = (f"model said Financial & Legal, overridden: {why} and no "
                f"transaction evidence (no amount, invoice #, or payment phrase)")
        confidence = 0.8

    if confidence is None:
        # No number from the model — derive one rather than inventing 0.6.
        if category == "financial_legal":
            confidence = 0.85 if has_txn else 0.45
            note = note or ("confidence derived from transaction evidence"
                            if has_txn else
                            "no confidence from model and no transaction evidence "
                            "-> low, will hold for review rather than book")
        else:
            confidence = 0.7

    return {
        "category": category,
        "confidence": max(0.0, min(1.0, confidence)),
        "fallback": False,
        "notes": note,
    }


# ---- Degraded-mode keyword rubric -------------------------------------------
#
# 2026-07-29 rewrite. The previous version was unanchored substring matching
# over subject+body with `fin` checked first:
#
#     fin = ("invoice", "receipt", "payment", "statement", "tax", "refund",
#            "payout", "wire transfer", "paid", "billing", "subscription renew")
#     if any(k in text for k in fin): cat, conf = "financial_legal", 0.5
#
# Every one of those is a false-positive generator on ordinary vendor mail:
# "tax" matches syn**tax**, "paid" matches pre**paid**/un**paid**, and "billing"
# appears in literally any SaaS pricing page footer. Combined with confidence
# exactly 0.5 — the same value as email_brain's hand-off threshold, compared
# with >= — a keyword guess was enough to book a real entry in CC's expense
# ledger. That is how "Lindy is cutting prices by 4x on average" (a vendor
# marketing blast) ended up filed under Receipts/2026/Business Expenses.
#
# New rule: a money-adjacent WORD is not evidence. A TRANSACTION is. Financial
# requires either an explicit transaction phrase, or a currency amount sitting
# next to receipt vocabulary. Marketing language actively vetoes it.

_MONEY_AMOUNT_RE = re.compile(
    r"(?:[$£€]\s?\d[\d,]*(?:\.\d{2})?)"          # $1,234.56
    r"|(?:\b\d[\d,]*\.\d{2}\s?(?:usd|cad|eur|gbp)\b)",  # 1234.56 USD
    re.IGNORECASE,
)

# Phrases that only occur when money actually moved or is formally due.
_TXN_PHRASE_RE = re.compile(
    r"\b(?:"
    r"invoice\s*#|invoice\s+(?:no|number|attached|is\s+(?:due|ready))"
    r"|receipt\s+(?:for|from|of|is\s+ready)|your\s+receipt"
    r"|payment\s+(?:received|confirmation|failed|declined|due|of)"
    r"|payout\s+(?:of|sent|initiated)|wire\s+transfer"
    r"|(?:your\s+)?subscription\s+(?:has\s+)?renew(?:ed|s)"
    r"|(?:auto[- ]?)?renewal\s+(?:notice|confirmation)"
    r"|thanks?\s+for\s+your\s+(?:payment|purchase|order)"
    r"|charged\s+to\s+your|we(?:'ve| have)\s+charged"
    r"|statement\s+is\s+(?:ready|available)|account\s+statement"
    r"|refund\s+(?:of|issued|processed)"
    r"|amount\s+(?:due|paid)|balance\s+due|remittance"
    r"|t4a?\b|\bcra\b|revenu\s+qu[ée]bec|notice\s+of\s+assessment"
    r"|tax\s+(?:receipt|slip|return|invoice|document)"
    r")",
    re.IGNORECASE,
)

# Receipt vocabulary — weak alone, but promotes a bare currency amount.
_RECEIPT_WORD_RE = re.compile(
    r"\b(?:invoice|receipt|billed|charged|payment|payout|remittance|"
    r"transaction|order\s+confirmation)\b",
    re.IGNORECASE,
)

# Vendor marketing / pricing announcements. These VETO a financial read: a
# company telling you what things cost is not a company charging you.
_MARKETING_RE = re.compile(
    r"\b(?:"
    r"cutting\s+prices?|price\s+(?:cut|drop|change|increase|update)s?"
    r"|new\s+pricing|pricing\s+(?:update|change|announcement)s?"
    r"|now\s+(?:cheaper|free)|save\s+\d+%|\d+%\s+off|limited[- ]time"
    r"|upgrade\s+(?:now|today)|introducing\b|announcing\b|early\s+access"
    r"|webinar|newsletter|unsubscribe|view\s+in\s+browser|black\s+friday"
    r"|deal\s+of\s+the|promo\s*code|coupon"
    r")",
    re.IGNORECASE,
)

_SUPPORT_RE = re.compile(
    r"\b(?:broken|not\s+working|isn'?t\s+working|bug|outage|is\s+down|"
    r"can'?t\s+access|cannot\s+access|please\s+help|issue\s+with|"
    r"error\s+when|stopped\s+working|"
    # Platform failure vocabulary. Without these a Stripe webhook-delivery
    # failure fell through to _LOW_RE (which matches the bare word "webhook")
    # and was filed as low-priority noise — the 2026-05-11 misroute in its
    # degraded-mode form. "failed"/"failing" are safe here because the
    # transaction check runs FIRST, so "payment failed" is already financial.
    r"unable\s+to\s+deliver|failed\s+to\s+deliver|is\s+failing|"
    r"action\s+required|delivery\s+attempts|build\s+failed|run\s+failed|"
    r"returned\s+an?\s+(?:api\s+)?error)\b",
    re.IGNORECASE,
)

_BIZ_RE = re.compile(
    r"\b(?:demo|interested\s+in|proposal|partnership|introduc\w*|"
    r"book\s+a\s+call|discovery\s+call|referral|get\s+a\s+quote|"
    r"your\s+services|work\s+together)\b",
    re.IGNORECASE,
)

_LOW_RE = re.compile(
    r"\b(?:unsubscribe|newsletter|digest|promotion|webhook|deploy(?:ment)?\s+"
    r"(?:error|failed)|deprecat\w*|no[- ]?reply)\b",
    re.IGNORECASE,
)

# Degraded confidence. MUST stay below every threshold in email_brain
# (DEFAULT_FINANCIAL_THRESHOLD, reply_threshold, archive_threshold) so a guess
# can never trigger an irreversible action — a booked ledger entry, an
# auto-sent reply, or a silent archive. email_brain ALSO hard-blocks hand-off
# on fallback=True; this is the second lock on the same door.
FALLBACK_CONFIDENCE = 0.35


def _has_transaction_evidence(text: str) -> bool:
    """True only when the text shows money actually moved or is formally due."""
    if _TXN_PHRASE_RE.search(text):
        return True
    # A bare currency amount counts only alongside receipt vocabulary —
    # "$49/mo" in a pricing blast is not a charge.
    return bool(_MONEY_AMOUNT_RE.search(text) and _RECEIPT_WORD_RE.search(text))


def _category_keyword_fallback(subject: Optional[str], content: Optional[str],
                               from_identity: Optional[str]) -> dict:
    """Cheap degraded classifier for when the Claude CLI is unavailable.

    Financial is still checked first — a real payment receipt from a no-reply
    sender must route to financial_legal (the n8n rubric) — but it now demands
    transaction EVIDENCE rather than a money-adjacent word, and marketing
    language vetoes it outright.
    """
    text = ((subject or "") + "\n" + (content or ""))
    sender = (from_identity or "").lower()

    has_txn = _has_transaction_evidence(text)
    is_marketing = bool(_MARKETING_RE.search(text))

    if has_txn and not is_marketing:
        cat, note = "financial_legal", "transaction evidence"
    elif _SUPPORT_RE.search(text):
        cat, note = "technical_support", "support signal"
    elif is_marketing:
        # Explicit branch, above biz: a pricing announcement contains words the
        # business-opportunity rubric likes ("pricing", "upgrade"), and the old
        # ordering let those win.
        cat, note = "low_priority", "vendor marketing / announcement"
    elif _BIZ_RE.search(text):
        cat, note = "business_opportunity", "inbound interest signal"
    elif (_LOW_RE.search(text)
            or sender.startswith(("noreply", "no-reply", "notifications", "news"))):
        cat, note = "low_priority", "automated / bulk sender"
    else:
        cat, note = "low_priority", "no signal"

    if has_txn and is_marketing:
        note += " (money words present but overridden by marketing language)"

    return {"category": cat, "confidence": FALLBACK_CONFIDENCE, "fallback": True,
            "notes": f"keyword fallback (CLI unavailable): {note}"}


def classify_category(
    content: str,
    subject: Optional[str] = None,
    from_identity: Optional[str] = None,
    *,
    runner: Any = None,
    is_bulk: bool = False,
) -> dict:
    """Classify an inbound email into one of the 4 brain categories.

    Never raises. On CLI failure or malformed output, falls back to the keyword
    classifier and marks fallback=True. `runner` is injectable for tests
    (signature: runner(prompt, system=, model=, timeout=) -> str|None).

    Returns {"category", "confidence": float, "fallback": bool, "notes": str}.
    """
    # Deterministic platform pre-routing, BEFORE the model.
    #
    # PLATFORM_SENDERS + _platform_prefilter were added 2026-05-11 after a Stripe
    # webhook-failure email was routed to Atlas as a business expense. But the
    # prefilter was only ever called from classify() — never from here, the
    # function that actually drives the 4-brain router and the Atlas hand-off.
    # So the guard built to stop "platform mail -> expense" has never once run
    # on the path where that mistake happens. Wired up 2026-07-29.
    pf = _platform_prefilter(from_identity, subject, content)
    if pf is not None:
        route = pf.get("route_target") or ""
        platform = pf.get("platform") or "platform"
        if route == "ops_technical":
            return {"category": "technical_support", "confidence": 0.8,
                    "fallback": False,
                    "notes": f"platform prefilter: technical alert from {platform}"}
        if route == "financial":
            # Known billing sender, but still require the model to agree this is
            # a transaction — the prefilter only knows WHO sent it, not whether
            # this particular message is a receipt or a pricing newsletter.
            pass
        else:
            return {"category": "low_priority", "confidence": 0.75,
                    "fallback": False,
                    "notes": f"platform prefilter: routine {platform} notification"}

    _runner = runner if runner is not None else _default_category_runner
    user_msg = _build_category_user_msg(content, subject, from_identity,
                                        is_bulk=is_bulk)
    raw: Optional[str] = None
    try:
        raw = _runner(user_msg, system=CATEGORY_SYSTEM_PROMPT, model="haiku", timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"[classify_category] runner failed ({exc}); using keyword fallback.",
              file=sys.stderr)
        raw = None
    if raw:
        # The model's answer is checked against deterministic evidence drawn
        # from the SAME text it was shown.
        evidence_text = f"{subject or ''}\n{content or ''}"
        parsed = _parse_category_response(raw, evidence_text=evidence_text,
                                          is_bulk=is_bulk)
        if parsed is not None:
            return parsed
    return _category_keyword_fallback(subject, content, from_identity)


# ---- Haiku classifier -------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT = """You are an inbound message classifier for a B2B
sales/marketing pipeline. Your job is to read an incoming message (email,
DM, or similar) and output a single JSON object with no commentary, no
markdown, no prose.

Schema — every key required:
{
  "sentiment":        "positive" | "neutral" | "negative" | "mixed",
  "intent":           one of [booking, pricing, objection, info_request,
                              out_of_office, unsubscribe, spam_bounce,
                              noise, reply_positive, reply_negative,
                              referral, other],
  "priority":         "hot" | "warm" | "cold" | "low",
  "stage_signal":     one of [escalate_to_engaged, escalate_to_warm,
                              regress_to_dormant, escalate_to_active_client,
                              mark_lost, hold],
  "confidence":       number 0.0 .. 1.0,
  "suggested_action": one of [draft_booking_confirmation, draft_pricing_reply,
                              draft_objection_handler, draft_info_reply,
                              escalate_to_cc, add_to_nurture,
                              mark_unsubscribed, ignore, hold_for_review],
  "key_phrase":       short substring from the message that drove the classification,
  "notes":            at most one sentence of reasoning
}

Rules:
- Be conservative on "hot" priority. Reserve it for explicit booking asks,
  clear buying signals, or direct urgency.
- If the message is a mailer-daemon bounce, auto-reply, or obvious noise,
  mark intent=spam_bounce OR noise, priority=low, suggested_action=ignore.
- If the writer explicitly says stop/unsubscribe/remove me: intent=unsubscribe,
  suggested_action=mark_unsubscribed.
- Never hallucinate a key_phrase — it must be a direct substring.
- Output ONLY the JSON object. No code fences, no preamble."""


def _classify_via_haiku(content: str, channel: str,
                         subject: Optional[str], from_identity: Optional[str]) -> dict:
    """Call Claude Haiku via the subscription `claude` CLI (lib.claude_cli) —
    never the metered ANTHROPIC_API_KEY (out of credits + banned per CC's
    CLI-only rule). Returns the raw parsed dict or raises.

    2026-07-28: dropped a dead `_env` parameter. The caller passed `env=` while
    the signature declared `_env`, so EVERY call raised TypeError and was
    swallowed by the except below — the classifier had silently degraded to the
    keyword fallback on every inbound email. The CLI path needs no env (it
    shells out to the subscription `claude` binary), so the parameter is gone
    rather than renamed."""
    from lib.claude_cli import run_claude_cli

    user_parts = [f"Channel: {channel}"]
    if from_identity:
        user_parts.append(f"From: {from_identity}")
    if subject:
        user_parts.append(f"Subject: {subject}")
    user_parts.append("")
    user_parts.append("Message:")
    user_parts.append((content or "")[:4000])
    user_msg = "\n".join(user_parts)

    text = run_claude_cli(user_msg, system=CLASSIFY_SYSTEM_PROMPT, model="haiku", timeout=90)
    if text is None:
        raise RuntimeError("claude subscription CLI unavailable (run `claude setup-token`)")
    parsed = json.loads(strip_code_fence(text))
    return parsed


def _validate_and_normalize(raw: dict) -> dict:
    """Clamp values to the valid enum set; defaults where missing."""
    out = {
        "sentiment": raw.get("sentiment", "neutral"),
        "intent": raw.get("intent", "other"),
        "priority": raw.get("priority", "cold"),
        "stage_signal": raw.get("stage_signal", "hold"),
        "confidence": float(raw.get("confidence", 0.5) or 0.5),
        "suggested_action": raw.get("suggested_action", "hold_for_review"),
        "key_phrase": (raw.get("key_phrase") or "")[:200],
        "notes": (raw.get("notes") or "")[:300],
        "fallback": False,
    }
    if out["sentiment"] not in VALID_SENTIMENTS:
        out["sentiment"] = "neutral"
    if out["intent"] not in VALID_INTENTS:
        out["intent"] = "other"
    if out["priority"] not in VALID_PRIORITY:
        out["priority"] = "cold"
    if out["stage_signal"] not in VALID_STAGE_SIGNALS:
        out["stage_signal"] = "hold"
    if out["suggested_action"] not in VALID_ACTIONS:
        out["suggested_action"] = "hold_for_review"
    out["confidence"] = max(0.0, min(1.0, out["confidence"]))
    return out


# ---- Public API -------------------------------------------------------------

def classify(
    content: str,
    channel: str,
    subject: Optional[str] = None,
    from_identity: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Classify an inbound message. Never raises. On any error falls back
    to the keyword classifier with reduced confidence.

    Gate 0 (added 2026-05-11): platform sender pre-filter. Known platform
    senders (Stripe, Vercel, GitHub, etc.) are classified by domain +
    keyword match before Haiku is called. This prevents mis-routing where
    e.g. a Stripe webhook failure notification gets sent to Atlas as a
    business expense instead of being routed as a technical alert.
    """
    # `env` is retained on the signature for call-site compatibility but is no
    # longer resolved here: the Haiku path shells out to the subscription
    # `claude` CLI and needs no credentials, so the old eager load_env() was a
    # dead file read on every inbound message.

    # Gate 0: platform sender pre-filter
    pf = _platform_prefilter(from_identity, subject, content)
    if pf is not None:
        # Fire Telegram notification for platform alerts
        _notify_platform_alert(pf, subject, from_identity)
        return pf

    try:
        raw = _classify_via_haiku(
            content=content or "",
            channel=channel or "email",
            subject=subject,
            from_identity=from_identity,
        )
        return _validate_and_normalize(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[inbound_classifier] Haiku failed ({exc}); "
              "falling back to keyword classifier.",
              file=sys.stderr)
        return _keyword_fallback(content or "")


def _notify_platform_alert(
    classification: dict,
    subject: Optional[str],
    from_identity: Optional[str],
) -> None:
    """Best-effort Telegram notification for platform alerts. Never raises."""
    try:
        platform = classification.get("platform", "unknown")
        route = classification.get("route_target", "unknown")
        intent = classification.get("intent", "platform_alert")
        priority_emoji = "\U0001f534" if classification.get("priority") == "hot" else "\U0001f7e1"

        if intent == "tech_alert":
            msg = (
                f"{priority_emoji} TECH ALERT from {platform.upper()}\n"
                f"Subject: {(subject or 'no subject')[:100]}\n"
                f"From: {from_identity or 'unknown'}\n"
                f"Route: {route} (NOT financial)\n"
                f"Action needed -- check your {platform} dashboard."
            )
        else:
            msg = (
                f"\U0001f4e8 Platform notification from {platform.upper()}\n"
                f"Subject: {(subject or 'no subject')[:100]}\n"
                f"Route: {route}"
            )
        _telegram_notify(msg, category="ops")
    except Exception:  # noqa: BLE001
        pass  # Telegram is best-effort; never block classification


def record_inbound(
    classification: dict,
    channel: str,
    from_identity: str,
    content: str,
    subject: Optional[str] = None,
    thread_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Any = None,
) -> Optional[str]:
    """Persist the inbound record. Writes lead_interactions AND agent_events.
    Returns the lead_interactions id.
    """
    e = load_env()
    db = db if db is not None else get_supabase(e)
    now = datetime.now(timezone.utc)

    # Resolve lead by email if not provided. For IG/skool channels the
    # from_identity is a @username, so we store it in metadata but don't
    # auto-create a lead row without an email.
    if not lead_id and from_identity and "@" in from_identity and "." in from_identity:
        try:
            r = (db.table("leads").select("id")
                 .eq("email", from_identity.strip().lower())
                 .limit(1).execute().data)
            if r:
                lead_id = r[0]["id"]
            else:
                # Create a minimal inbound-only lead record. Source='inbound'
                # distinguishes from outbound gateway auto-creates.
                from lib.lead_contract import has_hard_required
                raw_lead = {
                    "name": from_identity.split("@")[0],
                    "email": from_identity.strip().lower(),
                    "source": "inbound_" + channel,
                }
                if not has_hard_required(raw_lead):
                    print(
                        f"[inbound_classifier] lead_contract rejected lead creation for {from_identity}",
                        file=sys.stderr,
                    )
                else:
                    ins = db.table("leads").insert({
                        **raw_lead,
                        "status": "new",
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    }).execute().data
                    if ins:
                        lead_id = ins[0]["id"]
        except Exception as exc:  # noqa: BLE001
            print(f"[inbound_classifier] lead resolve warning: {exc}", file=sys.stderr)

    full_metadata = dict(metadata or {})
    full_metadata.update({
        "from_identity": from_identity,
        "thread_id": thread_id,
        "sentiment": classification.get("sentiment"),
        "intent": classification.get("intent"),
        "priority": classification.get("priority"),
        "stage_signal": classification.get("stage_signal"),
        "confidence": classification.get("confidence"),
        "suggested_action": classification.get("suggested_action"),
        "key_phrase": classification.get("key_phrase"),
        "classifier_notes": classification.get("notes"),
        "fallback_classifier": classification.get("fallback", False),
    })

    row = {
        "lead_id": lead_id,
        "type": f"{channel}_received",
        "channel": channel,
        "subject": (subject or "")[:500] or None,
        "content": (content or "")[:2000],
        "agent_source": "inbound_classifier",
        "metadata": full_metadata,
        "created_at": now.isoformat(),
    }
    interaction_id: Optional[str] = None
    try:
        res = db.table("lead_interactions").insert(row).execute()
        interaction_id = res.data[0].get("id") if res.data else None
    except Exception as exc:  # noqa: BLE001
        print(f"[inbound_classifier] lead_interactions insert failed: {exc}",
              file=sys.stderr)

    # Publish on the event bus for downstream subscribers (autonomous_agent,
    # outcome_tracker, Atlas, Maven).
    try:
        event_payload = {
            "interaction_id": interaction_id,
            "lead_id": lead_id,
            "channel": channel,
            "from_identity": from_identity,
            "subject": subject,
            "classification": classification,
        }
        severity = "info"
        if classification.get("priority") == "hot":
            severity = "warn"  # surfaces in dashboards
        if classification.get("intent") == "unsubscribe":
            severity = "warn"
        db.table("agent_events").insert({
            "event_type": "inbound.classified",
            "publisher_agent": "bravo",
            "severity": severity,
            "payload": event_payload,
            "correlation_id": interaction_id,
            "published_at": now.isoformat(),
        }).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[inbound_classifier] agent_events publish warning: {exc}",
              file=sys.stderr)

    return interaction_id


# ---- CLI --------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_classify(args) -> int:
    r = classify(
        content=args.content,
        channel=args.channel,
        subject=args.subject,
        from_identity=args.from_id,
    )
    if args.output_json:
        _print_json(r)
    else:
        print(f"sentiment:   {r['sentiment']}")
        print(f"intent:      {r['intent']}")
        print(f"priority:    {r['priority']}")
        print(f"stage:       {r['stage_signal']}")
        print(f"action:      {r['suggested_action']}")
        print(f"confidence:  {r['confidence']:.2f}")
        if r.get("fallback"):
            print(f"(fallback classifier used)")
    return 0


def _cmd_stats(args) -> int:
    """Aggregate last 7d of classifications for CC's morning brief."""
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    window_start = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat()
    # Query the last 7 days of classified inbound events.
    try:
        rows = (db.table("agent_events")
                .select("payload, severity, published_at")
                .eq("event_type", "inbound.classified")
                .order("published_at", desc=True)
                .limit(500)
                .execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    by_intent: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for row in rows:
        p = row.get("payload") or {}
        c = p.get("classification") or {}
        by_intent[c.get("intent", "other")] = by_intent.get(c.get("intent", "other"), 0) + 1
        by_priority[c.get("priority", "cold")] = by_priority.get(c.get("priority", "cold"), 0) + 1

    result = {
        "sample_size": len(rows),
        "by_intent": dict(sorted(by_intent.items(), key=lambda x: -x[1])),
        "by_priority": dict(sorted(by_priority.items(), key=lambda x: -x[1])),
    }
    if args.output_json:
        _print_json(result)
    else:
        print(f"Inbound stats ({len(rows)} events):")
        print("  Intent:")
        for k, v in result["by_intent"].items():
            print(f"    {k:25} {v}")
        print("  Priority:")
        for k, v in result["by_priority"].items():
            print(f"    {k:10} {v}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="inbound_classifier.py",
        description="Classify an inbound message (Haiku + keyword fallback).",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pc = sub.add_parser("classify", help="Classify a single inbound message")
    pc.add_argument("--channel", required=True,
                     choices=["email", "instagram", "linkedin", "skool", "telegram", "phone"])
    pc.add_argument("--content", required=True, help="The message body")
    pc.add_argument("--subject", default=None)
    pc.add_argument("--from", dest="from_id", default=None,
                     help="Sender identity (email or @handle)")

    ps = sub.add_parser("stats", help="Last 500 classifications by intent/priority")

    args = p.parse_args()

    if args.command == "classify":
        sys.exit(_cmd_classify(args))
    elif args.command == "stats":
        sys.exit(_cmd_stats(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
