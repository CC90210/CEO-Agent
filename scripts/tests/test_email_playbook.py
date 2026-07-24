"""Tests for the OASIS inbound-email playbook.

These encode the SAFETY rules the n8n qualifier enforced and the first native
port lost. Each test corresponds to a concrete way the automation could damage
the business: replying to an investor, arguing with a furious client,
auto-answering an outage, quoting a price, looping with a sibling agent, or
silently deleting a vendor receipt.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from email_playbook import (  # noqa: E402
    BOOKING_LINK,
    alert,
    classify_sender,
    detect_red_flags,
    extract_forwarded_sender,
    is_forwarded,
    lint_draft,
    voice_rules,
)


class TestSenderTriage(unittest.TestCase):
    def test_noreply_is_classified_not_deleted(self):
        # THE regression that was losing money: no-reply vendor receipts were
        # dropped before classification, so Stripe/GCloud/Vercel expenses never
        # reached the ledger. They must be kept (and never replied to).
        r = classify_sender("Google Cloud <noreply@google.com>",
                            "Your invoice is available")
        self.assertEqual(r["kind"], "automated")
        self.assertFalse(r["may_reply"])
        self.assertTrue(r["is_automated"])

    def test_sibling_agent_never_replied_to(self):
        for addr in ("bravo@oasisai.work", "atlas-agent@oasisai.work",
                     "maven@oasisai.work", "sentinel@oasisai.work"):
            r = classify_sender(addr, "status")
            self.assertEqual(r["kind"], "sibling", addr)
            self.assertFalse(r["may_reply"], addr)

    def test_owner_forward_is_not_a_stranger(self):
        r = classify_sender("konamak@icloud.com", "Fwd: invoice")
        self.assertEqual(r["kind"], "owner")
        self.assertFalse(r["may_reply"])

    def test_security_scanner_flagged(self):
        r = classify_sender("noreply@gitguardian.com", "Secret detected in repo")
        self.assertEqual(r["kind"], "security")
        self.assertFalse(r["may_reply"])

    def test_mass_mail_platform_is_automated(self):
        r = classify_sender("sales@mail.apollo.io", "Quick question")
        self.assertEqual(r["kind"], "automated")

    def test_real_human_may_reply(self):
        r = classify_sender("jane@acmehvac.com", "Re: your proposal",
                            "hey, sounds good - can we chat?")
        self.assertEqual(r["kind"], "human")
        self.assertTrue(r["may_reply"])


class TestRedFlags(unittest.TestCase):
    def test_outage_blocks_autoreply(self):
        f = detect_red_flags("URGENT: site is down",
                             "our whole site is down and clients can't pay")
        self.assertIn("outage", f)

    def test_frustration_detected(self):
        self.assertIn("frustrated",
                      detect_red_flags("Re: still broken",
                                       "this is unacceptable, I'm considering canceling"))

    def test_all_caps_subject_reads_as_frustration(self):
        self.assertIn("frustrated", detect_red_flags("WHY IS THIS STILL BROKEN", "hello"))

    def test_money_in_a_support_thread_is_flagged(self):
        f = detect_red_flags("Re: bug in the form",
                             "also does this change the monthly retainer?")
        self.assertIn("money", f)

    def test_strategic_sender_flagged(self):
        self.assertIn("strategic",
                      detect_red_flags("intro", "we'd love to introduce you to a partner",
                                       "partner@a16z.com"))

    def test_opt_out_flagged(self):
        self.assertIn("opt_out", detect_red_flags("re", "please take me off your list"))

    def test_clean_email_has_no_flags(self):
        self.assertEqual(detect_red_flags("Re: scheduling",
                                          "thursday works for me", "jane@acme.com"), [])


class TestForwarding(unittest.TestCase):
    def test_detects_forward(self):
        self.assertTrue(is_forwarded("Fwd: Receipt", ""))
        self.assertTrue(is_forwarded("Receipt", "---------- Forwarded message ---------"))
        self.assertFalse(is_forwarded("Receipt", "hello there"))

    def test_extracts_original_sender(self):
        body = ("---------- Forwarded message ---------\n"
                "From: Billing <billing@vendor.com>\n"
                "Date: Mon, 1 Jul 2026\n"
                "Subject: Invoice 42\n")
        self.assertEqual(extract_forwarded_sender(body), "billing@vendor.com")

    def test_falls_back_to_header_from(self):
        # body has no quoted From: -> use the envelope header
        self.assertEqual(
            extract_forwarded_sender("no headers here",
                                     header_from='"CC" <konamak@icloud.com>'),
            "konamak@icloud.com")

    def test_unresolvable_returns_sentinel_never_none(self):
        from email_playbook import UNKNOWN_FORWARD_SENDER
        got = extract_forwarded_sender("no headers", header_from="")
        self.assertEqual(got, UNKNOWN_FORWARD_SENDER)
        self.assertIsNotNone(got)  # the '?' bug: must never be None


class TestAlerts(unittest.TestCase):
    def test_hot_lead_is_loud(self):
        line, loud = alert("hot_lead", "ceo@bigco.com", "budget approved")
        self.assertTrue(line.startswith("[HOT-LEAD]"))
        self.assertTrue(loud)  # must NOT be silently delivered

    def test_outage_and_strategic_are_loud(self):
        self.assertTrue(alert("outage", "a@b.com", "down")[1])
        self.assertTrue(alert("strategic", "a@a16z.com", "intro")[1])

    def test_tags_are_greppable_and_distinct(self):
        tags = {alert(k, "a@b.com", "s")[0].split()[0]
                for k in ("outage", "hot_lead", "strategic", "frustrated", "security")}
        self.assertEqual(len(tags), 5)


class TestCopyRules(unittest.TestCase):
    def test_voice_rules_carry_link_and_signature(self):
        v = voice_rules()
        self.assertIn(BOOKING_LINK, v)
        self.assertIn("OASIS AI Solutions", v)
        self.assertIn("NEVER quote a price", v)

    def test_lint_catches_banned_phrases(self):
        issues = lint_draft("Thank you for reaching out. Best regards, CC")
        self.assertTrue(any("thank you for reaching out" in i for i in issues))
        self.assertTrue(any("best regards" in i for i in issues))

    def test_lint_catches_price_quote(self):
        self.assertTrue(any("dollar" in i for i in lint_draft("It'll be $2,000 flat.")))

    def test_lint_catches_duplicate_booking_link(self):
        body = f"grab a slot {BOOKING_LINK} or here {BOOKING_LINK}"
        self.assertTrue(any("more than once" in i for i in lint_draft(body)))

    def test_clean_draft_passes(self):
        body = ("Saw the HVAC scheduling mess you described - that's fixable.\n\n"
                f"15 min on Zoom is the fastest way to see if it fits: {BOOKING_LINK}\n\n"
                "Conaugh McKenna\nOASIS AI Solutions\noasisai.work")
        self.assertEqual(lint_draft(body), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
