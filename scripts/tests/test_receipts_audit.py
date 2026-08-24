"""Pin the receipts-audit candidate net against every failure class the
2026-08-23 adversarial verification found (workflow receipts-audit-verify):
misses (Kraken/IBKR statements, misspelled forwards, newline-wrapped GCP
subjects, Shopify "bill") and false-positive classes (own-app draw mail,
LinkedIn job alerts, AI newsletters, CI bots quoting money-shaped PR titles).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from receipts_audit import _cluster_key, is_financial_candidate  # noqa: E402


def _hit(from_addr, subject):
    ok, reason = is_financial_candidate(from_addr, subject)
    return ok, reason


# ── misses the first net had ─────────────────────────────────────────────────

def test_kraken_monthly_statement_is_a_candidate():
    ok, _ = _hit('"Kraken" <noreply@kraken.com>',
                 "Here's your March statement from Kraken")
    assert ok


def test_ibkr_ca_monthly_activity_statement_is_a_candidate():
    ok, _ = _hit("IB <donotreply@interactivebrokers.ca>",
                 "Monthly Activity Statement for March 2026")
    assert ok


def test_misspelled_personal_forward_is_a_candidate():
    # goldstorm inbound forwards are real receipts per CC's standing rule,
    # even hand-typed as "Recipt".
    ok, reason = _hit("CC <goldstorm2003@gmail.com>", "Claude Recipt")
    assert ok and reason.startswith("forward:")


def test_owner_icloud_forward_of_receipt_is_a_candidate():
    ok, reason = _hit("CC <konamak@icloud.com>", "Fwd: Your receipt from Vercel")
    assert ok and reason.startswith("forward:")


def test_newline_wrapped_gcp_dunning_subject_is_a_candidate():
    ok, _ = _hit("Google Cloud <payments-noreply@google.com>",
                 "Your Google Cloud payment is past\n due")
    assert ok


def test_shopify_bill_word_is_a_candidate():
    ok, _ = _hit("Shopify Billing <billing@shopify.com>",
                 "Jan 21, 2026 bill for Oasis")
    assert ok


def test_stripe_payout_is_a_candidate():
    ok, _ = _hit("Stripe <notifications@stripe.com>",
                 "Your CA$15.40 payout for nostalgic is on the way")
    assert ok


# ── false-positive classes the first net let through ─────────────────────────

def test_own_app_draw_notification_is_excluded():
    ok, reason = _hit("Breeze Advance <support@breezeadvance.credit>",
                      "We received your $50,000.00 draw request")
    assert not ok and reason == "own-app"


def test_own_app_billing_local_still_passes():
    # accounting@ on CC's own domain can carry a real inter-entity invoice.
    ok, _ = _hit("Breeze Accounting <accounting@breezeadvance.com>",
                 "Re: Invoice (oasisai)")
    assert ok


def test_linkedin_job_alert_with_salary_is_excluded():
    ok, reason = _hit("LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
                      "Software Engineer | $50-$150/hr and more")
    assert not ok and reason == "noise-sender"


def test_ai_newsletter_with_dollar_headline_is_excluded():
    ok, reason = _hit("AlphaSignal <news@alphasignal.ai>",
                      "OpenAI Astra solves 10 unsolved math proofs for $2,000 total")
    assert not ok and reason == "noise-sender"


def test_ci_bot_quoting_money_shaped_pr_title_is_excluded():
    ok, reason = _hit('"coderabbitai[bot]" <notifications@github.com>',
                      "Re: [CC90210/x] move paid calls onto the subscription (PR #126)")
    assert not ok and reason == "noise-sender"


def test_own_domain_outgoing_invoice_is_excluded():
    ok, reason = _hit("Oasis <conaugh@oasisai.work>", "Invoice")
    assert not ok and reason == "owner-sent"


# ── clustering: one transaction, one handoff ─────────────────────────────────

def test_invoice_and_receipt_sharing_a_reference_cluster_together():
    a = {"from": "Stripe <invoice@stripe.com>",
         "subject": "Invoice #2671-3082 from NOVASCENT"}
    b = {"from": "Stripe <receipts@stripe.com>",
         "subject": "Your receipt from NOVASCENT #2671-3082"}
    assert _cluster_key(a) == _cluster_key(b)


def test_different_references_do_not_cluster():
    a = {"from": "Stripe <invoice@stripe.com>", "subject": "Invoice #1111-1111"}
    b = {"from": "Stripe <invoice@stripe.com>", "subject": "Invoice #2222-2222"}
    assert _cluster_key(a) != _cluster_key(b)
