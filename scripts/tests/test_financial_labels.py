"""Tests for financial-document filing: the recall gate, the label taxonomy,
the IMAP encoding, and the silent-archive trapdoor.

THE REGRESSION THIS FILE EXISTS FOR (2026-08-28)
------------------------------------------------
A forwarded Google Cloud Platform invoice
("Fwd: Google Cloud Platform & APIs: Your invoice is available for
018D76-BA5673-D713C1", amount inside the attached PDF) was:

  1. correctly recognised as billing mail by the platform prefilter, which
     fired a Telegram saying "Route: financial";
  2. then independently classified `low_priority` at 0.95 by the model, because
     the booking rubric asks "did money move?" and the body names no amount;
  3. then routed by decide_action() to "archive silently" — no hand-off event,
     so Atlas (healthy, running every 15 min) never saw it and never labelled it.

Net effect: a success-shaped Telegram message and an unlabelled deductible
expense. `test_gcp_invoice_*` below pins every step of that.

Run:
  python -m pytest scripts/tests/test_financial_labels.py -q
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from email_brain import decide_action, process_email  # noqa: E402
from lib.financial_labels import (  # noqa: E402
    assess,
    financial_subtype,
    is_financial_document,
    label_for,
)
from lib.gmail_labels import (  # noqa: E402
    LabelError,
    apply_label,
    encode_label,
    read_labels,
)

# The real message that failed, as it arrived.
GCP_SUBJECT = ("Fwd: Google Cloud Platform & APIs: Your invoice is available "
               "for 018D76-BA5673-D713C1")
GCP_BODY = """---------- Forwarded message ---------
From: Google Payments <payments-noreply@google.com>
Subject: Google Cloud Platform & APIs: Your invoice is available for 018D76-BA5673-D713C1
To: <goldstorm2003@gmail.com>

Your invoice is available for your Google Cloud Platform & APIs account.
Account ID: 018D76-BA5673-D713C1
You can view and download your invoice in the payments centre.
"""
GCP_EMAIL = {
    "from": "payments-noreply@google.com",
    "subject": GCP_SUBJECT,
    "body": GCP_BODY,
    "attachments": ["5655806289.pdf"],
    "date": "Thu, 28 Aug 2026 17:05:00 -0400",
    "rfc_message_id": "<CAFT4sntcWzRwVr0Bv6@mail.gmail.com>",
    # Vendor receipts arrive almost exclusively from no-reply addresses; the
    # live sweep sets this from email_playbook.classify_sender. Without it the
    # fixture would take a reply-eligible path the real email never takes.
    "may_reply": False,
}


class TestGcpInvoiceRegression(unittest.TestCase):
    """The exact email that was lost. Each assertion is one link in the chain."""

    def test_gcp_invoice_is_a_financial_document(self):
        self.assertTrue(is_financial_document(
            GCP_SUBJECT, GCP_BODY, "payments-noreply@google.com",
            attachments=["5655806289.pdf"]))

    def test_gcp_invoice_files_as_business_expense_not_statement(self):
        # "your invoice is available" is availability PHRASING but a vendor
        # charge in SUBSTANCE. Atlas's amount-based rule would call it a
        # statement notice because the amount is in the PDF; that is the wrong
        # bucket for a deductible expense.
        self.assertEqual(assess(GCP_EMAIL)["label"],
                         "Receipts/2026/Business Expenses")

    def test_gcp_invoice_is_never_silently_archived(self):
        # THE fix. Same inputs that produced action='archive' before:
        # low_priority @ 0.95 from a no-reply sender.
        d = decide_action("low_priority", confidence=0.95, may_reply=False,
                          financial_document=True)
        self.assertEqual(d["action"], "label_filed")
        self.assertFalse(d["should_archive"])

    def test_non_financial_low_priority_still_archives(self):
        # The guard must not disable inbox-zero for actual newsletters.
        d = decide_action("low_priority", confidence=0.95, may_reply=False,
                          financial_document=False)
        self.assertEqual(d["action"], "archive")
        self.assertTrue(d["should_archive"])

    def test_degraded_still_outranks_filing(self):
        # A keyword-fallback guess may never take an automated path, financial
        # or not. Filing happens in process_email regardless; the ROUTING must
        # still hold for review.
        d = decide_action("low_priority", confidence=0.95, may_reply=False,
                          financial_document=True, degraded=True)
        self.assertEqual(d["action"], "review")


class TestRecallGate(unittest.TestCase):
    """Filing is a recall problem: err toward labelling, but not into noise."""

    # Senders are realistic: vendors send receipts from automated addresses.
    FILE_THESE = [
        ("vendor invoice with amount", "Invoice #4471 from Anthropic",
         "Amount due: $120.00 USD.", "billing@anthropic.com"),
        ("stripe payout", "Your payout of $2,480.00 is on its way",
         "Your payout has been sent to your bank account.",
         "notifications@stripe.com"),
        ("bank statement", "Your monthly statement is ready",
         "Your account statement for July is available.", "noreply@rbc.com"),
        ("cra notice", "Notice of assessment", "CRA has issued your notice.",
         "noreply@cra-arc.gc.ca"),
        ("subscription renewal", "Your subscription was renewed",
         "We charged your card for the annual plan.", "billing@wispr.ai"),
    ]

    DO_NOT_FILE_THESE = [
        ("pricing blast", "Lindy is cutting prices by 4x on average",
         "New pricing! Save 40% when you upgrade now. Compare plans."),
        ("newsletter", "AlphaSignal: this week in AI",
         "Introducing our newsletter. Read more."),
        ("security alert", "Security alert",
         "A new sign-in on Apple iPhone 14 conaugh@oasisai.work"),
        ("deploy failure", "Vercel deployment failed",
         "Your build errored. Check the logs."),
        # All four below were proposed for filing by the 2026 dry run.
        ("renewal reminder", "Your Wispr Flow subscription will renew",
         "Your subscription will renew on 5 September."),
        ("add-a-card nudge", "Add payment details before Loom Business ends",
         "Add payment details to keep your subscription active."),
    ]

    BOT_SENDERS = [
        ("coderabbit PR comment", "coderabbitai[bot] <notifications@github.com>"),
        ("vercel bot PR comment", "vercel[bot] <notifications@github.com>"),
    ]

    def test_files_real_documents(self):
        for name, subj, body, sender in self.FILE_THESE:
            with self.subTest(name):
                self.assertTrue(is_financial_document(subj, body, sender))

    def test_colleague_prose_about_money_is_not_a_receipt(self):
        # The 2026 dry run proposed filing four of a colleague's SunBiz ops
        # emails as Business Expenses on loose vocabulary alone. A human needs
        # to name a document; a vendor's automated address does not.
        for subj, body in [
            ("Underwriting SOP", "Here is the SOP. Payment of the fee is due "
                                 "after the deal closes."),
            ("Fwd: Leads to get numbers", "Chasing the invoice numbers on these."),
            ("Application for 6993 Decarie, Apt 1406",
             "Attaching the rental application. First month payment due on "
             "signing."),
        ]:
            with self.subTest(subj):
                self.assertFalse(is_financial_document(
                    subj, body, "Jordan Colleson <jordan@sunbizfunding.com>"))

    def test_a_human_with_a_real_invoice_still_files(self):
        # The human rule must not lose a genuine invoice - it demands a strong
        # document signal, not an automated sender.
        self.assertTrue(is_financial_document(
            "Invoice HRM-2605052143 - Hermes Agent",
            "Please find the invoice attached.",
            "echelonx.aisolutions@gmail.com"))

    def test_does_not_file_marketing_or_alerts(self):
        for name, subj, body in self.DO_NOT_FILE_THESE:
            with self.subTest(name):
                self.assertFalse(is_financial_document(subj, body, "x@y.com"))

    def test_marketing_from_a_billing_sender_is_still_not_filed(self):
        # The prefilter says "financial" because of WHO sent it. A pricing
        # announcement from that same sender is still not a document.
        self.assertFalse(is_financial_document(
            "New pricing for Stripe Billing",
            "Announcing new pricing. Compare plans and upgrade now.",
            "billing@stripe.com", prefilter_route="financial"))

    def test_ci_bots_are_never_receipts(self):
        # Their mail quotes diffs full of billing code. The dry run proposed
        # filing three coderabbitai comments and a vercel[bot] comment as
        # Business Expenses.
        for name, sender in self.BOT_SENDERS:
            with self.subTest(name):
                self.assertFalse(is_financial_document(
                    "Re: [CC90210/oasis-command-center] fix(invoice): payment total",
                    "Review comment on the invoice payment handler. "
                    "Amount due calculation looks wrong.",
                    sender))

    def test_industry_news_about_money_is_not_a_receipt(self):
        # Caught by the first backfill dry run: a LinkedIn digest headlined
        # "The $175 Billion Question: What the Supreme Court..." was proposed as
        # a Business Expense. Its body discusses tax, and 'bill' matches inside
        # "Billion". Recall-biased must not mean signal-free.
        self.assertFalse(is_financial_document(
            "The $175 Billion Question: What the Supreme Court Ruling Means",
            "A deep dive into the tax implications for corporate America. "
            "Analysts expect billions in refund claims.",
            "news-noreply@linkedin.com"))

    def test_social_sender_veto_beats_document_words(self):
        # Even genuine-looking document vocabulary cannot make a LinkedIn
        # digest a receipt.
        self.assertFalse(is_financial_document(
            "Your invoice is available", "Payment received. Amount due: $99.00",
            "messages-noreply@linkedin.com"))

    def test_veto_does_not_catch_real_vendors(self):
        # The sender veto must not swallow legitimate billing senders whose
        # domains merely contain a vetoed substring pattern.
        for sender in ("billing@stripe.com", "invoice+statements@vercel.com",
                       "payments-noreply@google.com", "no-reply@rbc.com"):
            with self.subTest(sender):
                self.assertTrue(is_financial_document(
                    "Your invoice is available", "Invoice ready.", sender))

    def test_attachment_alone_is_enough(self):
        # The body may say nothing useful; a PDF named invoice_123 is a
        # document. This is the signal a text-only rubric structurally cannot see.
        self.assertTrue(is_financial_document(
            "FYI", "See attached.", "vendor@example.com",
            attachments=[{"filename": "invoice_20260828.pdf"}]))


class TestDirection(unittest.TestCase):
    """A direction-blind classifier once mis-booked 8 rows as INCOME."""

    def test_payout_is_income(self):
        self.assertEqual(
            financial_subtype("Your payout of $2,480.00 is on its way", ""),
            "income")

    def test_customer_paid_is_income(self):
        self.assertEqual(
            financial_subtype("Invoice 1042 has been paid",
                              "Your customer paid invoice 1042."), "income")

    def test_vendor_invoice_is_expense(self):
        self.assertEqual(
            financial_subtype("Your invoice is available", "Invoice ready."),
            "expense")

    def test_bank_statement_is_statement(self):
        self.assertEqual(
            financial_subtype("Your monthly statement is ready",
                              "Your account statement is available."), "statement")

    def test_vendor_confirming_your_payment_is_an_expense(self):
        # Caught by the 2026 dry run: "We've received your payment" filed two
        # Google Workspace CHARGES under Income & Invoices. The vendor received
        # it, so the money left CC.
        self.assertEqual(
            financial_subtype("Google Workspace: We've received your payment",
                              "Thank you. We've received your payment."),
            "expense")

    def test_payment_received_for_vendor_is_an_expense(self):
        self.assertEqual(
            financial_subtype("Fwd: Payment received for Supabase Pte. Ltd",
                              "Payment received for Supabase Pte. Ltd."),
            "expense")

    def test_invoice_issued_by_cc_is_income(self):
        self.assertEqual(
            financial_subtype("Software and AI Automation Invoice",
                              "Invoice for services rendered. Total due: $2,000.",
                              "Oasis <conaugh@oasisai.work>"),
            "income")

    def test_forwarded_vendor_receipt_from_goldstorm_stays_an_expense(self):
        # goldstorm2003 is where CC signs up to vendors and forwards the
        # receipts in. Treating it as one of his ISSUING identities would
        # invert the direction on every forwarded receipt - including the
        # Google Cloud invoice this whole repair started from.
        self.assertEqual(
            financial_subtype(
                "Fwd: Google Cloud Platform & APIs: Your invoice is available",
                "Your invoice is available for your account.",
                "GOLD STORM <goldstorm2003@gmail.com>"),
            "expense")

    def test_bare_invoice_word_does_not_imply_income(self):
        # "invoice" alone is direction-ambiguous and must never resolve to
        # income on its own — that is precisely how the 8 rows were mis-booked.
        self.assertNotEqual(
            financial_subtype("Invoice 88 from Vercel", "Invoice attached."),
            "income")


class TestCodexAuditFindings(unittest.TestCase):
    """Each of these was found by the independent Codex audit of this change,
    reproduced, and fixed. They are pinned so the fixes cannot silently regress."""

    def test_payment_received_for_an_invoice_is_income_not_expense(self):
        # The expense-direction rule was written for "Payment received for
        # Supabase Pte. Ltd" (a named vendor = money out). Stripe also sends
        # "Payment received for invoice 123", which is a CUSTOMER paying CC.
        # The object of "for" decides the direction.
        self.assertEqual(
            financial_subtype("Payment received for invoice 123",
                              "Payment received for invoice 123."),
            "income")

    def test_payment_received_for_a_named_vendor_is_still_an_expense(self):
        self.assertEqual(
            financial_subtype("Fwd: Payment received for Supabase Pte. Ltd",
                              "Payment received for Supabase Pte. Ltd."),
            "expense")

    def test_renewal_reminder_quoting_an_amount_is_still_not_a_document(self):
        # The veto used to switch off whenever any amount appeared, so a
        # future charge read as a completed one.
        self.assertFalse(is_financial_document(
            "Your subscription renews on Sep 1",
            "Your subscription renews on Sep 1 for $20.00.",
            "billing@vendor.com"))

    def test_card_expiry_nudge_quoting_an_amount_is_not_a_document(self):
        self.assertFalse(is_financial_document(
            "Your card is expiring",
            "Update payment method. Amount due $20.00.",
            "billing@vendor.com"))

    def test_receipt_mentioning_the_next_renewal_still_files(self):
        # The other half of that fix: tightening the veto must not start
        # dropping genuine receipts that mention a renewal date.
        self.assertTrue(is_financial_document(
            "Thanks for your payment",
            "Thank you for your payment of $20.00. Your subscription will "
            "renew on Sep 1.",
            "billing@vendor.com"))


class TestLabelYear(unittest.TestCase):
    def test_year_comes_from_the_email_not_today(self):
        self.assertEqual(label_for("expense", "Sat, 09 Jan 2027 09:00:00 -0500"),
                         "Receipts/2027/Business Expenses")

    def test_backfilling_old_mail_uses_the_old_year(self):
        self.assertEqual(label_for("income", "Mon, 02 Feb 2026 09:00:00 -0500"),
                         "Receipts/2026/Income & Invoices")

    def test_iso_dates_work_too(self):
        self.assertEqual(label_for("statement", "2026-03-04T10:00:00Z"),
                         "Receipts/2026/Statements & Notices")


class TestImapEncoding(unittest.TestCase):
    """RFC 3501 s5.1.3. Until 2026-08-24 labels went on the wire raw and every
    '&'-bearing label failed its STORE silently — 42 statement notices and every
    booked payout stayed unlabelled while '&'-free "Business Expenses" worked."""

    def test_ampersand_is_encoded(self):
        self.assertEqual(encode_label("Receipts/2026/Income & Invoices"),
                         "Receipts/2026/Income &- Invoices")

    def test_label_without_ampersand_is_untouched(self):
        self.assertEqual(encode_label("Receipts/2026/Business Expenses"),
                         "Receipts/2026/Business Expenses")

    def test_round_trip_through_read_labels(self):
        conn = _FakeImap()
        apply_label(conn, "42", "Receipts/2026/Income & Invoices")
        # The wire form must be encoded...
        self.assertIn("&-", conn.stored[-1][2])
        # ...and reading it back must yield the logical name again.
        self.assertIn("Receipts/2026/Income & Invoices", read_labels(conn, "42"))

    def test_non_ok_status_raises_instead_of_returning_false(self):
        # The CFO-Agent version returns a bare, unlogged False here, which its
        # caller discards. That is the silent-failure shape; ours must raise.
        conn = _FakeImap(status="NO")
        with self.assertRaises(LabelError):
            apply_label(conn, "42", "Receipts/2026/Business Expenses")

    def test_exception_becomes_label_error(self):
        conn = _FakeImap(raises=True)
        with self.assertRaises(LabelError):
            apply_label(conn, "42", "Receipts/2026/Business Expenses")

    def test_non_ascii_label_is_refused_not_mis_encoded(self):
        # encode_label only implements the ASCII + '&' subset. Silently
        # mis-encoding a future accented label would repeat the 42-message bug
        # in new clothes.
        with self.assertRaises(LabelError):
            apply_label(_FakeImap(), "42", "Receipts/2026/Dépenses")

    def test_uid_mode_uses_uid_store(self):
        conn = _FakeImap()
        apply_label(conn, "99", "Receipts/2026/Business Expenses", use_uid=True)
        self.assertEqual(conn.uid_calls[-1][0], "STORE")


CFO_GMAIL_RECEIPTS = Path("C:/Users/User/APPS/CFO-Agent/cfo/gmail_receipts.py")


class TestEncoderDoesNotDriftFromAtlas(unittest.TestCase):
    """Two repos now encode the same IMAP label rule, so pin them together.

    Bravo labels in-sweep (lib/gmail_labels.encode_label) and Atlas labels
    out-of-band (cfo/gmail_receipts.add_label_by_message_id). Extracting one
    into the other was considered and rejected: Atlas runs in CI where Bravo is
    not checked out (see its own skipif idiom), so a hard runtime import would
    break it. Duplication is the deliberate choice — but it must not DRIFT,
    because this exact rule silently lost 42 statement notices when only one
    side had it.

    Skipped where CFO-Agent is not on the machine; present locally as a canary.
    """

    @unittest.skipIf(not CFO_GMAIL_RECEIPTS.exists(),
                     "CFO-Agent not on this machine")
    def test_atlas_still_encodes_ampersand_the_same_way(self):
        src = CFO_GMAIL_RECEIPTS.read_text(encoding="utf-8")
        self.assertIn('replace("&", "&-")', src,
                      "Atlas's add_label_by_message_id no longer encodes '&' as "
                      "'&-'. Every '&'-bearing label ('Income & Invoices', "
                      "'Statements & Notices') will fail its IMAP STORE, and "
                      "the return value is a bare False. Restore it, or move "
                      "both sides onto one encoder.")

    @unittest.skipIf(not CFO_GMAIL_RECEIPTS.exists(),
                     "CFO-Agent not on this machine")
    def test_both_sides_produce_the_same_wire_form(self):
        # Bravo's encoder, applied to the labels Atlas actually emits.
        for leaf in ("Business Expenses", "Income & Invoices",
                     "Statements & Notices"):
            logical = f"Receipts/2026/{leaf}"
            with self.subTest(leaf):
                self.assertEqual(encode_label(logical),
                                 logical.replace("&", "&-"))


class TestProcessEmailFiling(unittest.TestCase):
    """End-to-end through the brain with injected deps."""

    def _run(self, category, confidence, apply_label_fn, email=None):
        calls = {"notify": [], "mark_read": 0, "archive": 0, "handoff": 0}

        def _cls(**kw):
            return {"category": category, "confidence": confidence,
                    "fallback": False}

        deps = {
            "apply_label": apply_label_fn,
            # Second positional arg is the optional Telegram reply_markup that
            # the draft-hold paths pass (2026-09-01). These cases do not reach
            # those paths today, so a 1-arg lambda still passes — which is
            # precisely why it must be widened now: the next test added here
            # that DOES hold a draft would fail on an unrelated TypeError.
            "notify": lambda t, reply_markup=None: calls["notify"].append(t),
            "mark_read": lambda e: calls.__setitem__("mark_read", calls["mark_read"] + 1),
            "archive": lambda e: calls.__setitem__("archive", calls["archive"] + 1),
            "handoff_atlas": lambda e: calls.__setitem__("handoff", calls["handoff"] + 1) or True,
        }
        out = process_email(dict(email or GCP_EMAIL), classifier=_cls, deps=deps)
        return out, calls

    def test_invoice_is_labelled_even_when_model_says_low_priority(self):
        applied = []
        out, calls = self._run("low_priority", 0.95,
                               lambda e, l: applied.append(l))
        self.assertEqual(applied, ["Receipts/2026/Business Expenses"])
        self.assertEqual(out["action"], "label_filed")
        self.assertEqual(out["label"], "Receipts/2026/Business Expenses")
        self.assertEqual(calls["archive"], 0, "must not hit the archive dep")

    def test_label_failure_keeps_mail_unread_and_shouts(self):
        def _boom(_e, _l):
            raise LabelError("IMAP STORE returned 'NO'")

        out, calls = self._run("low_priority", 0.95, _boom)
        self.assertIsNone(out["label"])
        self.assertEqual(out["action"], "review",
                         "an unfiled receipt must not be reported as filed")
        self.assertEqual(calls["mark_read"], 0,
                         "unlabelled mail must stay unread and visible")
        self.assertTrue(any("LABEL FAILED" in t for t in calls["notify"]))

    def test_assessment_failure_holds_instead_of_archiving(self):
        # Codex audit, HIGH: if assess() raises, the old code left `fin` as
        # non-financial and the email fell straight back into
        # "low_priority + automated sender -> archive silently" — the exact
        # loss this module exists to prevent, re-created by an import error.
        import lib.financial_labels as fl
        real = fl.assess
        fl.assess = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            out, calls = self._run("low_priority", 0.95, lambda e, l: None)
        finally:
            fl.assess = real
        self.assertEqual(out["action"], "review")
        self.assertEqual(calls["archive"], 0)
        self.assertEqual(calls["mark_read"], 0,
                         "an email we could not assess must stay visible")

    def test_notifier_failure_does_not_abort_the_review_path(self):
        # Codex audit: the label-failure alert was unguarded, so a Telegram
        # outage on top of a label failure could skip the very path that keeps
        # the email visible.
        def _boom_label(_e, _l):
            raise LabelError("IMAP STORE returned 'NO'")

        def _boom_notify(_t, _reply_markup=None):
            raise RuntimeError("telegram down")

        def _cls(**kw):
            return {"category": "low_priority", "confidence": 0.95,
                    "fallback": False}

        marked = []
        out = process_email(dict(GCP_EMAIL), classifier=_cls, deps={
            "apply_label": _boom_label,
            "notify": _boom_notify,
            "mark_read": lambda e: marked.append(1),
        })
        self.assertIsNone(out["label"])
        self.assertEqual(marked, [], "must not mark an unfiled receipt read")
        self.assertNotEqual(out.get("action"), "archive")

    def test_unwired_labeller_fails_loudly_rather_than_no_op(self):
        # build_default_deps() must not hand back a silent no-op: that would
        # report a receipt as filed with no label anywhere — the original bug.
        from email_brain import build_default_deps
        deps = build_default_deps()
        with self.assertRaises(RuntimeError):
            deps["apply_label"]({}, "Receipts/2026/Business Expenses")

    def test_newsletter_is_not_labelled(self):
        applied = []
        news = {"from": "news@alphasignal.ai", "subject": "This week in AI",
                "body": "Introducing our newsletter.", "attachments": [],
                "date": "Thu, 28 Aug 2026 10:00:00 -0400"}
        out, calls = self._run("low_priority", 0.95,
                               lambda e, l: applied.append(l), email=news)
        self.assertEqual(applied, [])
        self.assertEqual(out["action"], "archive")

    def test_handoff_notification_names_the_label(self):
        # The old alert reported the prefilter's routing INTENT before the real
        # decision, so it read as success on mail that was about to be dropped.
        out, calls = self._run("financial_legal", 0.9,
                               lambda e, l: None)
        self.assertTrue(any("Filed" in t for t in calls["notify"]),
                        f"notifications were: {calls['notify']}")


class _FakeImap:
    """Records what actually went on the wire."""

    def __init__(self, status="OK", raises=False):
        self.status = status
        self.raises = raises
        self.stored = []
        self.uid_calls = []
        self._labels = []

    def store(self, num, flag, value):
        if self.raises:
            raise OSError("connection reset")
        self.stored.append((num, flag, value))
        if self.status == "OK":
            self._labels.append(value.strip('"'))
        return self.status, [b""]

    def uid(self, cmd, *args):
        self.uid_calls.append((cmd,) + args)
        if cmd == "STORE":
            return self.store(args[0], args[1], args[2])
        return "OK", [b""]

    def fetch(self, num, spec):
        inner = " ".join(f'"{lbl}"' for lbl in self._labels)
        return "OK", [(b"1 (X-GM-LABELS (" + inner.encode() + b"))")]


if __name__ == "__main__":
    unittest.main(verbosity=2)
