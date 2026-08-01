"""Regression tests for inbound email classification — the 2026-07-29
"vendor marketing booked as a business expense" incident.

WHAT WENT WRONG
A Lindy marketing blast ("Lindy is cutting prices by 4x on average") and a
Vercel account notice were filed into Gmail's Receipts/2026/Business Expenses.
Four independent defects lined up:

  1. _category_keyword_fallback matched unanchored substrings over the whole
     body: "tax" hit *syn*tax, "paid" hit *pre*paid, "billing" hits every SaaS
     pricing footer.
  2. That fallback returned confidence exactly 0.5; DEFAULT_FINANCIAL_THRESHOLD
     was exactly 0.5; the comparison was `>=`. So a guess cleared the guard.
  3. The `fallback: True` flag was returned and read by nobody, so a degraded
     keyword guess was treated as a confident model read.
  4. _platform_prefilter — added in May specifically to stop "Stripe/Vercel ->
     Atlas expense" — was wired to classify(), not to classify_category(), the
     function that actually drives the Atlas hand-off.

No network: the model runner is injected, so these run offline and fast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from email_brain import DEFAULT_FINANCIAL_THRESHOLD, decide_action  # noqa: E402
from inbound_classifier import (  # noqa: E402
    FALLBACK_CONFIDENCE,
    PLATFORM_SENDERS,
    _BILLING_TOPIC_RE,
    _INTEGRATION_FAILURE_RE,
    _category_keyword_fallback,
    _has_transaction_evidence,
    _platform_prefilter,
    classify_category,
)

# ── Real-world fixtures ──────────────────────────────────────────────────────

LINDY = dict(
    subject="Lindy is cutting prices by 4x on average",
    body=("Lindy is cutting prices by 4x on average. Some of your agents are "
          "currently powered by outdated and cost-inefficient models. Upgrade "
          "now to the new pricing and save 75% on every task. "
          "Unsubscribe | View in browser"),
    sender="hello@lindy.ai",
)

VERCEL_ACCOUNT = dict(
    subject="admin@breezeadvance.com joined CC",
    body=("Hi CC, admin-28301567 (admin@breezeadvance.com) has accepted their "
          "invitation to join CC as an Owner. You can view and manage your team."),
    sender="notifications@vercel.com",
)

STRIPE_WEBHOOK_FAIL = dict(
    subject="Action required: your webhook endpoint is failing",
    body=("We were unable to deliver events to your webhook endpoint. The "
          "endpoint returned an API error on 47 delivery attempts."),
    sender="notifications@stripe.com",
)

STRIPE_RECEIPT = dict(
    subject="Your receipt from OASIS AI Solutions",
    body=("Receipt for your payment. Amount paid $1,250.00 USD. "
          "Payment received on July 28, 2026. Invoice #INV-2026-0142."),
    sender="receipts@stripe.com",
)

CRA_NOTICE = dict(
    subject="Notice of assessment",
    body=("Your notice of assessment for the 2025 tax year is available. "
          "Balance due $3,410.55."),
    sender="noreply@cra-arc.gc.ca",
)

CODERABBIT = dict(
    subject="Re: [CC90210/CEO-Agent] native email pipeline (PR #42)",
    body=("coderabbitai[bot] left a comment. Actionable comments posted: 1. "
          "Potential issue: unguarded subprocess call in scripts/x.py."),
    sender="notifications@github.com",
)


# ── The transaction-evidence primitive ───────────────────────────────────────

@pytest.mark.parametrize("text,expected,why", [
    ("Invoice #INV-2026-0142 attached", True, "explicit invoice number"),
    ("Amount paid $1,250.00 USD", True, "amount + receipt vocabulary"),
    ("Payment received on July 28", True, "payment received phrase"),
    ("Your subscription has renewed", True, "renewal confirmation"),
    ("Notice of assessment. Balance due $3,410.55", True, "CRA/tax"),
    ("We are cutting prices by 4x on average", False, "pricing announcement"),
    ("Plans start at $49/mo — upgrade now", False, "price quote, no transaction"),
    ("Check the syntax of your billing config", False, "'tax' inside 'syntax'"),
    ("Prepaid credits are now available", False, "'paid' inside 'prepaid'"),
    ("Our billing docs have moved", False, "bare 'billing'"),
])
def test_transaction_evidence(text, expected, why):
    assert _has_transaction_evidence(text) is expected, why


# ── Degraded keyword fallback ────────────────────────────────────────────────

@pytest.mark.parametrize("fixture,expected,why", [
    (LINDY, "low_priority", "THE regression: vendor price-cut blast is marketing"),
    (VERCEL_ACCOUNT, "low_priority", "platform account notice, not a receipt"),
    (STRIPE_RECEIPT, "financial_legal", "a real receipt must still route financial"),
    (CRA_NOTICE, "financial_legal", "tax document with a balance due"),
    (STRIPE_WEBHOOK_FAIL, "technical_support", "webhook failure is technical"),
])
def test_keyword_fallback_category(fixture, expected, why):
    got = _category_keyword_fallback(fixture["subject"], fixture["body"],
                                     fixture["sender"])
    assert got["category"] == expected, f"{why} — got {got}"


def test_fallback_confidence_cannot_clear_the_handoff_gate():
    """The 0.5-vs-0.5 collision that let a guess book a ledger entry."""
    assert FALLBACK_CONFIDENCE < DEFAULT_FINANCIAL_THRESHOLD, (
        "degraded confidence must sit strictly below the Atlas hand-off "
        "threshold — this equality is what booked the Lindy email as an expense"
    )


def test_fallback_always_flags_itself():
    got = _category_keyword_fallback(LINDY["subject"], LINDY["body"], LINDY["sender"])
    assert got["fallback"] is True


# ── The Atlas hand-off gate ──────────────────────────────────────────────────

def test_degraded_classification_never_hands_off_to_atlas():
    """Even a confident-looking financial read must not book on degraded mode."""
    d = decide_action("financial_legal", confidence=0.99, may_reply=False,
                      degraded=True)
    assert d["action"] == "review", d
    assert d["hold_for_review"] is True


def test_degraded_classification_never_auto_sends_or_archives():
    for category in ("technical_support", "low_priority", "business_opportunity"):
        d = decide_action(category, confidence=0.99, is_known_client=True,
                          auto_send_enabled=True, degraded=True)
        assert d["action"] == "review", f"{category} -> {d}"
        assert d["should_send"] is False
        assert d["should_archive"] is False


def test_confident_financial_still_hands_off():
    """The guard must not break the case it exists to permit."""
    d = decide_action("financial_legal", confidence=0.9, may_reply=False,
                      degraded=False)
    assert d["action"] == "handoff_atlas", d


def test_threshold_boundary_is_strict():
    """confidence exactly == threshold must NOT hand off (was `>=`)."""
    d = decide_action("financial_legal", confidence=DEFAULT_FINANCIAL_THRESHOLD,
                      may_reply=False, degraded=False)
    assert d["action"] == "review", d


# ── Platform prefilter, now wired into classify_category ─────────────────────

def _boom_runner(*_a, **_kw):
    raise AssertionError("model must not be called — prefilter should short-circuit")


def test_stripe_webhook_failure_routes_technical_not_financial():
    """The 2026-05-11 incident, re-tested on the path that actually matters."""
    got = classify_category(
        content=STRIPE_WEBHOOK_FAIL["body"], subject=STRIPE_WEBHOOK_FAIL["subject"],
        from_identity=STRIPE_WEBHOOK_FAIL["sender"], runner=_boom_runner)
    assert got["category"] == "technical_support", got
    assert got["category"] != "financial_legal"


def test_vercel_notice_does_not_reach_the_model_as_financial():
    got = classify_category(
        content=VERCEL_ACCOUNT["body"], subject=VERCEL_ACCOUNT["subject"],
        from_identity=VERCEL_ACCOUNT["sender"], runner=_boom_runner)
    assert got["category"] in ("low_priority", "technical_support"), got


def test_coderabbit_is_technical():
    got = classify_category(
        content=CODERABBIT["body"], subject=CODERABBIT["subject"],
        from_identity=CODERABBIT["sender"], runner=_boom_runner)
    assert got["category"] in ("technical_support", "low_priority"), got
    assert got["category"] != "financial_legal"


# ── Model path ───────────────────────────────────────────────────────────────

def test_bulk_header_hint_reaches_the_model():
    """List-Unsubscribe is the strongest deterministic marketing signal we have;
    make sure it is actually surfaced in the prompt rather than silently dropped."""
    seen = {}

    def capture_runner(prompt, system=None, **_kw):
        seen["prompt"] = prompt
        seen["system"] = system
        return '{"category": "Low Priority & Archive", "confidence": 0.9}'

    classify_category(content=LINDY["body"], subject=LINDY["subject"],
                      from_identity=LINDY["sender"], runner=capture_runner,
                      is_bulk=True)
    assert "List-Unsubscribe" in seen["prompt"]
    # And the rewritten rubric must name the failure mode explicitly.
    assert "cutting prices" in seen["system"]


# ── Deterministic guards over the model's answer ─────────────────────────────
#
# Measured 2026-07-29: the SAME Lindy email returned "Low Priority & Archive"
# @0.95 on one call and "Financial & Legal" @0.6 on the next. Money routing
# cannot ride on that, so the model's answer is checked against evidence.

def _says(category, confidence=None):
    payload = {"category": category}
    if confidence is not None:
        payload["confidence"] = confidence

    def runner(*_a, **_kw):
        return json.dumps(payload)
    return runner


def test_marketing_veto_overrides_a_wrong_model_answer():
    """Bulk-sent + no transaction evidence => cannot be Financial, whatever the
    model says. This is the exact Lindy regression."""
    got = classify_category(
        content=LINDY["body"], subject=LINDY["subject"],
        from_identity=LINDY["sender"], is_bulk=True,
        runner=_says("Financial & Legal", 0.95))
    assert got["category"] == "low_priority", got
    assert "overridden" in got["notes"]


def test_marketing_veto_fires_on_language_even_without_the_header():
    got = classify_category(
        content=LINDY["body"], subject=LINDY["subject"],
        from_identity=LINDY["sender"], is_bulk=False,
        runner=_says("Financial & Legal", 0.95))
    assert got["category"] == "low_priority", got


def test_veto_does_NOT_touch_a_real_receipt():
    """A genuine receipt survives the veto even if it were sent in bulk —
    transaction evidence is present."""
    got = classify_category(
        content=STRIPE_RECEIPT["body"], subject=STRIPE_RECEIPT["subject"],
        from_identity="billing@acme.example", is_bulk=True,
        runner=_says("Financial & Legal", 0.95))
    assert got["category"] == "financial_legal", got


def test_missing_confidence_is_derived_from_evidence_not_invented():
    """The old flat 0.6 default meant a genuine receipt scored BELOW the
    hand-off threshold and silently never booked — a lost deductible."""
    got = classify_category(
        content=STRIPE_RECEIPT["body"], subject=STRIPE_RECEIPT["subject"],
        from_identity="billing@acme.example",
        runner=_says("Financial & Legal"))          # no confidence field
    assert got["confidence"] > DEFAULT_FINANCIAL_THRESHOLD, got
    d = decide_action("financial_legal", confidence=got["confidence"],
                      may_reply=False, degraded=False)
    assert d["action"] == "handoff_atlas", d


def test_missing_confidence_without_evidence_stays_below_threshold():
    """No marketing language (so the veto does not fire) and no transaction
    evidence either: the derived confidence must land BELOW the hand-off gate so
    it holds for review instead of booking on nothing."""
    got = classify_category(
        content="Your account details were updated by an administrator.",
        subject="Account notice",
        from_identity="hello@vendor.example",
        runner=_says("Financial & Legal"))
    assert got["category"] == "financial_legal", got   # veto did NOT fire
    assert got["confidence"] <= DEFAULT_FINANCIAL_THRESHOLD, got
    d = decide_action("financial_legal", confidence=got["confidence"],
                      may_reply=False, degraded=False)
    assert d["action"] == "review", d


def test_model_failure_degrades_to_fallback_not_a_crash():
    def dead_runner(*_a, **_kw):
        raise RuntimeError("claude CLI unavailable")

    got = classify_category(content=LINDY["body"], subject=LINDY["subject"],
                            from_identity=LINDY["sender"], runner=dead_runner)
    assert got["fallback"] is True
    assert got["category"] == "low_priority", got


# ── Platform prefilter: money topics outrank technical keywords ──────────────
#
# 2026-08-01. CC screenshotted three Google alerts in Telegram, all stamped
# "Route: ops_technical (NOT financial)". Two of them were an invoice and a
# past-due billing account. Cause: "billing" was listed as a tech_keyword for
# google.com, and a tech-keyword hit hard-returns technical_support from
# classify_category WITHOUT consulting the model — so a real bill could never
# reach Atlas. The subjects below are the verbatim ones from those alerts.

@pytest.mark.parametrize("sender,subject,body,expected,why", [
    ("payments-noreply@google.com",
     "Google Workspace: Your invoice is available for oasisai.work", "",
     "financial",
     "an invoice is money even though 'workspace' is a tech keyword"),
    ("cloudplatform-noreply@google.com",
     "Action required: your billing account 014050-B7D660-B0C981 is past due "
     "or has invalid payment info", "",
     "financial",
     "a past-due billing account is the single most financial mail Google sends"),
    ("cloudplatform-noreply@google.com",
     "Your Project: My First Project is at risk of suspension",
     "Your project uses the cloud api quota",
     "ops_technical",
     "suspension notice with no money words stays ops"),
    ("noreply@google.com", "Google Cloud API quota exceeded",
     "cloud api quota alert", "ops_technical",
     "pure tech alert must not be dragged into financial"),
    ("noreply@stripe.com", "Your webhook endpoint is failing",
     "delivery error api", "ops_technical",
     "Stripe webhook failure is ops — the 2026-05-11 incident this prefilter exists for"),
    ("noreply@stripe.com", "Your invoice #1234 is ready", "payment of $20.00",
     "financial", "Stripe invoice keeps its financial route"),
    ("noreply@vercel.com", "Deployment failed: build error", "ssl domain",
     "ops_technical", "deploy failure is ops"),
])
def test_billing_topic_outranks_tech_keywords(sender, subject, body, expected, why):
    got = _platform_prefilter(sender, subject, body)
    assert got is not None, f"prefilter did not match a known platform: {sender}"
    assert got["route_target"] == expected, f"{why} — got {got['route_target']}"


@pytest.mark.parametrize("text", [
    "your billing account is past due or has invalid payment info",
    "Google Workspace: Your invoice is available for oasisai.work",
])
def test_billing_topic_routes_to_finance_but_never_books(text):
    """Routing to finance and booking an expense are different questions.

    _BILLING_TOPIC_RE decides "should Atlas see this"; _has_transaction_evidence
    decides "did money move". A bill that has not been paid must reach Atlas
    WITHOUT creating a ledger row — widening the routing predicate must never
    widen the booking one. This is the guard on that separation.
    """
    assert _has_transaction_evidence(text) is False, (
        "an unpaid bill is not transaction evidence — booking it would invent "
        "a ledger row for money that never moved")


def test_real_receipts_still_count_as_transaction_evidence():
    """The other side of the same fence: don't fix routing by breaking booking."""
    assert _has_transaction_evidence("Your receipt for $20.00 USD") is True
    assert _has_transaction_evidence("invoice #1234 payment received $49.00") is True


# ── Mixed tech + billing: an outage must never be held as finance ────────────
#
# 2026-08-01, from a Codex adversarial review of the billing-override commit.
# A real webhook-failure email NAMES the events it could not deliver, and those
# names are billing events ("invoice.payment_failed", "charge.refunded"). The
# first cut of _BILLING_TOPIC_RE matched those names and routed a live outage
# to finance — strictly worse than the misrouting it fixed, and precisely the
# failure _platform_prefilter was built for in 2026-05. The original tests
# missed it because every fixture was cleanly one thing or the other.

@pytest.mark.parametrize("sender,subject,body,expected,why", [
    ("notifications@stripe.com",
     "Action required: your webhook endpoint is failing",
     "We were unable to deliver events to your webhook endpoint. The endpoint "
     "returned an API error on 47 delivery attempts. Failing event types: "
     "invoice.payment_failed, customer.subscription.renewed, charge.refunded.",
     "ops_technical",
     "THE regression: an outage quoting billing event names is still an outage"),
    ("cloudplatform-noreply@google.com", "Your Cloud API quota exceeded",
     "Your project exceeded its api quota. Update your payment method to raise limits.",
     "ops_technical",
     "quota exhaustion is ops even when the remedy is a payment method"),
    ("noreply@vercel.com", "Deployment failed",
     "build failed; your invoice is attached", "ops_technical",
     "a broken deploy outranks an attached invoice"),
    ("payments-noreply@google.com",
     "Google Workspace: Your invoice is available for oasisai.work", "",
     "financial", "a pure bill must still reach finance after the failure carve-out"),
    ("noreply@stripe.com", "Your invoice #1234 is ready", "payment of $20.00",
     "financial", "a pure bill must still reach finance after the failure carve-out"),
])
def test_integration_failure_outranks_billing_topic(sender, subject, body, expected, why):
    got = _platform_prefilter(sender, subject, body)
    assert got is not None, f"prefilter did not match a known platform: {sender}"
    assert got["route_target"] == expected, f"{why} — got {got['route_target']}"


def test_no_platform_lists_a_money_word_as_a_technical_keyword():
    """The original defect, as an invariant rather than one fixed case.

    google.com listed "billing" in tech_keywords, and a tech-keyword hit
    short-circuits classify_category without ever calling the model — so the
    word "billing" appearing in a bill guaranteed that bill was filed as a tech
    alert. Any money word in any of these lists recreates that bug for that
    vendor, so assert the whole registry, not just the one row that was wrong.
    """
    # An explicit stem list, NOT _BILLING_TOPIC_RE. That regex is tuned for
    # message bodies and requires context ("billing account", "payment
    # declined"), so it does not match the bare word "billing" — reusing it
    # here produced an assertion that passed while the original bug was
    # present. Caught by re-adding "billing" and watching the test stay green.
    money_stems = ("billing", "invoice", "payment", "receipt", "charge",
                   "refund", "past due", "overdue", "subscription", "card")
    offenders = {
        domain: [kw for kw in cfg.get("tech_keywords", [])
                 if any(stem in kw.lower() for stem in money_stems)]
        for domain, cfg in PLATFORM_SENDERS.items()
    }
    offenders = {d: kws for d, kws in offenders.items() if kws}
    assert not offenders, (
        f"money words used as technical keywords: {offenders} — a tech-keyword "
        f"hit skips the model, so these bills would never reach Atlas")


@pytest.mark.parametrize("domain", sorted(PLATFORM_SENDERS))
def test_every_platform_routes_a_bill_to_finance(domain):
    """Holds regardless of the vendor's default_route.

    cloudflare.com and googlecloud.com carry empty tech_keywords and a
    "technical" default_route, so before the billing branch existed every bill
    they sent went to ops by default — not via a keyword match, which is why
    fixing google's keyword list alone would not have covered them.
    """
    got = _platform_prefilter(f"noreply@{domain}",
                              "Your invoice is available — account past due", "")
    assert got is not None and got["route_target"] == "financial", (
        f"{domain} misroutes a plain bill: {got}")


def test_end_to_end_bill_reaches_the_model_and_outage_does_not():
    """The prefilter is a unit; classify_category is what drives the hand-off.

    Asserting on _platform_prefilter alone would pass even if classify_category
    still short-circuited, so pin the two behaviours that actually matter: a
    bill must reach the model (only the model can say whether THIS message is a
    transaction), and an outage must still skip it (paging ops must not wait on
    an LLM call).
    """
    def boom(*_a, **_kw):
        raise AssertionError("model must NOT be called — outage should short-circuit")

    bill = classify_category(
        content="", subject="Google Workspace: Your invoice is available for oasisai.work",
        from_identity="payments-noreply@google.com",
        runner=lambda *_a, **_kw: "Financial & Legal")
    assert bill["category"] == "financial_legal", bill
    assert bill["fallback"] is False, "a consulted model is not a degraded fallback"

    outage = classify_category(
        content="unable to deliver events to your webhook endpoint. api error on 47 "
                "delivery attempts. invoice.payment_failed, charge.refunded",
        subject="Action required: your webhook endpoint is failing",
        from_identity="notifications@stripe.com", runner=boom)
    assert outage["category"] == "technical_support", outage


def test_routing_regexes_are_not_redos_vulnerable():
    """Subjects and bodies are attacker-controlled — inbound mail is untrusted.

    Both routing regexes are flat alternations of literals with no nested
    quantifiers. This guards against someone later adding one.
    """
    import time

    evil = "invoice " * 4000 + "x" * 40000
    start = time.perf_counter()
    _BILLING_TOPIC_RE.search(evil)
    _INTEGRATION_FAILURE_RE.search(evil)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"routing regex took {elapsed:.2f}s on a 72KB input"
