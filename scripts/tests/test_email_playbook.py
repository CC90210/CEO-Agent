"""Tests for the OASIS inbound-email playbook.

These encode the SAFETY rules the n8n qualifier enforced and the first native
port lost. Each test corresponds to a concrete way the automation could damage
the business: replying to an investor, arguing with a furious client,
auto-answering an outage, quoting a price, looping with a sibling agent, or
silently deleting a vendor receipt.
"""

from __future__ import annotations

import contextlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import booking_link  # noqa: E402
from email_playbook import (  # noqa: E402
    alert,
    classify_sender,
    detect_red_flags,
    extract_forwarded_sender,
    has_explicit_opt_out,
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

    def test_quoted_reply_stop_footer_is_not_an_opt_out(self):
        body = ("What do you run on your GPU instance?\n\n"
                "On Tue, Sep 22, 2026 at 10:30 AM CC wrote:\n"
                "> Reply STOP to unsubscribe from these emails.")
        self.assertFalse(has_explicit_opt_out("Re: GPU instance", body))
        self.assertNotIn("opt_out", detect_red_flags("Re: GPU instance", body))

    def test_bulk_unsubscribe_footer_is_not_an_opt_out(self):
        body = "You have one new LinkedIn message.\n\nUnsubscribe from these notifications"
        self.assertFalse(has_explicit_opt_out("You have 1 new message", body))
        self.assertNotIn("opt_out", detect_red_flags("You have 1 new message", body))

    def test_stop_subject_or_first_reply_line_is_an_opt_out(self):
        self.assertTrue(has_explicit_opt_out("Re: hello", "STOP emailing me"))
        self.assertTrue(has_explicit_opt_out("Re: Unsubscribe me", ""))

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


GOOD_LINK = "https://cal.example.com/oasis/30min"
RETIRED_LINK = "https://calendar.app.google/tpfvJYBGircnGu8G8"


def _booking_env(link: str | None) -> contextlib.ExitStack:
    """os.environ with BOOKING_LINK = `link` (or no booking key at all), and no
    env-file fallback, so the result never depends on this machine's env store."""
    env = {k: v for k, v in os.environ.items()
           if k not in booking_link.BOOKING_URL_ENV_KEYS}
    if link is not None:
        env["BOOKING_LINK"] = link
    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.dict(os.environ, env, clear=True))
    stack.enter_context(mock.patch.object(booking_link, "_env_file_values", return_value={}))
    return stack


class TestCopyRules(unittest.TestCase):
    def test_voice_rules_carry_link_and_signature(self):
        with _booking_env(GOOD_LINK):
            v = voice_rules()
        self.assertIn(GOOD_LINK, v)
        self.assertNotIn("no self-serve booking link", v)
        self.assertIn("OASIS AI Solutions", v)
        self.assertIn("NEVER quote a price", v)

    def test_voice_rules_refuse_the_retired_link(self):
        # 2026-09-24: the retired schedule reached a prospect through this prompt.
        # Configured or not, it must never be offered to the model again.
        for configured in (RETIRED_LINK, RETIRED_LINK.lower() + "/", None):
            with self.subTest(configured=configured), _booking_env(configured):
                v = voice_rules()
                self.assertNotIn("calendar.app.google", v.lower())
                self.assertIn("There is no self-serve booking link.", v)
                self.assertIn("Never paste a calendar or booking URL.", v)
                self.assertIn("NEVER quote a price", v)

    def test_voice_rules_resolve_at_call_time(self):
        # The dead value outlived its schedule because it was frozen at import.
        with _booking_env(None):
            self.assertNotIn(GOOD_LINK, voice_rules())
        with _booking_env(GOOD_LINK):
            self.assertIn(GOOD_LINK, voice_rules())

    def test_lint_catches_banned_phrases(self):
        issues = lint_draft("Thank you for reaching out. Best regards, CC")
        self.assertTrue(any("thank you for reaching out" in i for i in issues))
        self.assertTrue(any("best regards" in i for i in issues))

    def test_lint_catches_price_quote(self):
        self.assertTrue(any("dollar" in i for i in lint_draft("It'll be $2,000 flat.")))

    def test_lint_catches_duplicate_booking_link(self):
        body = f"grab a slot {GOOD_LINK} or here {GOOD_LINK}"
        with _booking_env(GOOD_LINK):
            self.assertTrue(any("more than once" in i for i in lint_draft(body)))

    def test_duplicate_check_needs_a_configured_link(self):
        body = "see https://oasisai.work or https://oasisai.work"
        with _booking_env(None):
            self.assertFalse(any("more than once" in i for i in lint_draft(body)))

    def test_lint_flags_a_retired_booking_url(self):
        drafts = (
            f"grab whatever slot fits you here: {RETIRED_LINK}",
            "book here calendar.app.google/TPFVJYBGIRCNGU8G8/ anytime",
        )
        for configured in (None, GOOD_LINK, RETIRED_LINK):
            for body in drafts:
                with self.subTest(configured=configured, body=body), _booking_env(configured):
                    self.assertIn("contains a retired booking link", lint_draft(body))

    def test_clean_draft_passes(self):
        body = ("Saw the HVAC scheduling mess you described - that's fixable.\n\n"
                f"15 min on Zoom is the fastest way to see if it fits: {GOOD_LINK}\n\n"
                "Conaugh McKenna\nOASIS AI Solutions\noasisai.work")
        with _booking_env(GOOD_LINK):
            self.assertEqual(lint_draft(body), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
