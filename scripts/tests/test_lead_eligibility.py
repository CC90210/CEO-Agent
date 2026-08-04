"""Who is allowed to become a CRM lead.

2026-08-04: 37 of 63 rows in `leads` (59%) were vendor mail — Google/Stripe/
Vercel/LinkedIn notifications, newsletters, and one send-path probe to an
RFC-2606 reserved domain. Two auto-create paths wrote them:
inbound_classifier.record_inbound (35) and send_gateway.resolve_lead_id (2).
Neither asked whether the sender should be in the CRM at all; the inbound one
had the classification sitting in scope as its first parameter and never
consulted it. Lead counts and pipeline metrics read 2.4x reality.

The bias is deliberate and asymmetric: a junk row costs a metric, a dropped
prospect costs revenue. So the deterministic veto is narrow, and a DEGRADED
classifier creates rather than drops.

Run: python -m pytest scripts/tests/test_lead_eligibility.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.lead_contract import should_create_lead  # noqa: E402


# ── Deterministic veto: always applies, no model involved ──────────────────

@pytest.mark.parametrize("email", [
    "probe-send@e2e.invalid",          # the actual row found in production
    "smoke@example.test",
    "harness@localhost",
    "fixture@example.example",
])
def test_reserved_tlds_never_become_leads(email):
    create, why = should_create_lead(email)
    assert create is False
    assert "reserved" in why


@pytest.mark.parametrize("email", [
    "noreply@email.openai.com",
    "no-reply@accounts.google.com",
    "payments-noreply@google.com",
    "cloudplatform-noreply@google.com",
    "notifications-noreply@linkedin.com",
    "mailer-daemon@googlemail.com",
    "postmaster@outlook.com",
    "bounces@sendgrid.net",
])
def test_machine_senders_never_become_leads(email):
    create, _ = should_create_lead(email)
    assert create is False, email


# ── The asymmetry: a human-shaped address is NOT blocked deterministically ──

@pytest.mark.parametrize("email", [
    "hello@ollama.com",       # vendor, but shaped exactly like a real prospect
    "info@e.atlassian.com",
    "team@info.hostinger.com",
    "charlotte@sdallaire.com",
    "kay.li@temu.com",
])
def test_human_shaped_vendor_mail_needs_the_classifier_not_a_regex(email):
    """These 5 are junk, but no safe regex separates them from a real inbound
    prospect writing from hello@ or info@. Blocking them by shape would drop
    revenue on an inbound-first funnel, so the classifier decides — and the
    deterministic tier deliberately lets them through."""
    create, why = should_create_lead(email)
    assert create is True and why == "eligible"
    # ...and the classifier catches them once it has looked:
    blocked, reason = should_create_lead(email, {"category": "low_priority"})
    assert blocked is False
    assert "low_priority" in reason


def test_a_real_prospect_is_never_blocked():
    """The control that makes the rest of this file meaningful."""
    for email in ("charlotte@realprospect.com", "cc@oasisai.work",
                  "founder@startup.io", "hello@genuinelead.com"):
        create, why = should_create_lead(
            email, {"category": "business_opportunity", "intent": "pricing"})
        assert create is True, f"{email} would have been dropped: {why}"


# ── Classifier tier ────────────────────────────────────────────────────────

@pytest.mark.parametrize("intent", ["spam_bounce", "noise", "out_of_office", "unsubscribe"])
def test_non_lead_intents_are_blocked(intent):
    create, _ = should_create_lead("someone@company.com", {"intent": intent})
    assert create is False


def test_a_degraded_classifier_creates_rather_than_drops():
    """[[pattern_degraded_classifier_must_not_book]] — the fallback flag is the
    gate. A keyword-mode read must not silently bin a real prospect during a
    model outage; failing toward keeping the lead is the only safe bias here."""
    create, why = should_create_lead(
        "prospect@company.com", {"category": "low_priority", "fallback": True})
    assert create is True
    assert "degraded" in why


def test_degraded_does_not_override_the_deterministic_veto():
    """Degraded means 'trust the model less', not 'trust everything more'."""
    create, _ = should_create_lead(
        "noreply@vendor.com", {"category": "business_opportunity", "fallback": True})
    assert create is False


def test_garbage_input_is_rejected_without_raising():
    for bad in ("", "   ", "not-an-email", None):
        create, _ = should_create_lead(bad)  # type: ignore[arg-type]
        assert create is False


# ── Replay against the real production rows ────────────────────────────────

# Verbatim from the 37 NULL-tenant rows found in `leads` on 2026-08-04.
PRODUCTION_JUNK = [
    "gemini-notes@google.com", "help@paddle.com", "team@info.hostinger.com",
    "verify3@sunbizfunding.com", "notify2@myheritage.com", "kay.li@temu.com",
    "newsletter@coderabbit.ai", "charlotte@sdallaire.com", "system@vercel.com",
    "news@alphasignal.ai", "messages@priority.facebookmail.com",
    "ship@info.vercel.com", "hello@mail.wispr.ai", "hello@ollama.com",
    "bennetts-newsletter-7529f4@mail.beehiiv.com", "info@e.atlassian.com",
    "marketing@lambda.ai", "probe-send@e2e.invalid", "workspace@google.com",
    "payments-noreply@google.com", "no-reply@t.higgsfield.ai",
    "noreply@po.atlassian.net", "cloudplatform-noreply@google.com",
    "notifications@stripe.com", "no-reply@accounts.google.com",
    "noreply@email.openai.com", "support@kraken.com",
    "notifications-noreply@linkedin.com", "notifications@vercel.com",
]


def test_every_production_junk_row_is_now_blocked():
    """With the classifier working (these all classify low_priority — the
    pipeline was already labelling them correctly, the write just never asked),
    all 29 sampled junk senders stay out of the CRM."""
    leaked = [e for e in PRODUCTION_JUNK
              if should_create_lead(e, {"category": "low_priority"})[0]]
    assert not leaked, f"still eligible: {leaked}"


def test_deterministic_tier_alone_catches_the_no_reply_bulk():
    """Measured, not claimed: with NO classifier the deterministic tier blocks
    8 of these 29 (28%) — the reserved-domain probe and the no-reply senders.
    The other 21 are human-shaped and NEED the classifier, which is exactly why
    the classifier tier exists and why the regex is not widened to cover them.

    (An earlier version of this test was called "two_thirds_are_caught" and
    asserted the same number. The assertion was right and the name was a lie.)
    """
    blocked = [e for e in PRODUCTION_JUNK if not should_create_lead(e)[0]]
    assert len(blocked) == 8, f"deterministic tier caught {len(blocked)}, expected 8"
