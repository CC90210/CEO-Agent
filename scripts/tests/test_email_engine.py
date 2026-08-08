"""Regression tests for email_engine template rendering.

Run:
  python scripts/test_email_engine.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# email_engine moved to scripts/integrations/ during the 2026-05 reorg.
from integrations.email_engine import (  # noqa: E402
    TemplateRenderError,
    _extract_attachment_meta,
    missing_template_variables,
    normalize_template_vars,
    render_template,
    stop_signal_decision,
    unresolved_template_placeholders,
)


class TestTemplateRendering(unittest.TestCase):
    def test_company_name_alias_fills_company(self):
        rendered = render_template(
            "Quick thought for {{company}}",
            {"company_name": "Collingwood Charters"},
        )
        self.assertEqual(rendered, "Quick thought for Collingwood Charters")

    def test_missing_company_raises(self):
        with self.assertRaises(TemplateRenderError) as ctx:
            render_template("Quick thought for {{company}}", {"first_name": "Matt"})
        self.assertIn("company", str(ctx.exception))

    def test_blank_company_raises(self):
        with self.assertRaises(TemplateRenderError):
            render_template("Quick thought for {{company}}", {"company": "   "})

    def test_strict_false_preserves_legacy_placeholder_behavior(self):
        rendered = render_template(
            "Quick thought for {{company}}",
            {"first_name": "Matt"},
            strict=False,
        )
        self.assertEqual(rendered, "Quick thought for {{company}}")

    def test_missing_variable_list_is_deduped(self):
        missing = missing_template_variables(
            "{{company}} / {{ company }} / {{first_name}}",
            {"first_name": "Jason"},
        )
        self.assertEqual(missing, ["company"])

    def test_unresolved_template_placeholder_detector(self):
        self.assertEqual(
            unresolved_template_placeholders(
                "{{company}} lead follow-up",
                "<p>Hi {{first_name}}</p>",
            ),
            ["company", "first_name"],
        )

    def test_normalize_template_vars_does_not_overwrite_real_company(self):
        variables = normalize_template_vars({
            "company": "JN Roofing & Contracting",
            "company_name": "Wrong Alias",
        })
        self.assertEqual(variables["company"], "JN Roofing & Contracting")


class TestStopSignalDecision(unittest.TestCase):
    """CASL auto-suppress guard (2026-07-18): a keyword-fallback classification
    (model outage) must never trigger irreversible suppression on its own —
    only a literal STOP/UNSUBSCRIBE opener or a real model classification can.
    """

    def test_outage_hot_lead_containing_stop_is_not_suppressed(self):
        suppress, review = stop_signal_decision(
            {"intent": "unsubscribe", "fallback": True},
            "nothing will stop me from signing, send the contract",
            "Re: funding",
        )
        self.assertFalse(suppress)
        self.assertTrue(review)

    def test_outage_literal_stop_reply_still_suppresses(self):
        suppress, review = stop_signal_decision(
            {"intent": "unsubscribe", "fallback": True}, "STOP", "Re: OASIS intro",
        )
        self.assertTrue(suppress)
        self.assertFalse(review)

    def test_outage_unsubscribe_subject_still_suppresses(self):
        suppress, review = stop_signal_decision(
            {"intent": "unsubscribe", "fallback": True},
            "take me off this list", "UNSUBSCRIBE",
        )
        self.assertTrue(suppress)
        self.assertFalse(review)

    def test_model_classified_soft_optout_suppresses(self):
        suppress, review = stop_signal_decision(
            {"intent": "unsubscribe"},
            "please take me off your list, thanks", "Re: intro",
        )
        self.assertTrue(suppress)
        self.assertFalse(review)

    def test_model_classified_hot_lead_untouched(self):
        suppress, review = stop_signal_decision(
            {"intent": "booking"}, "nothing will stop me from signing", "Re: funding",
        )
        self.assertFalse(suppress)
        self.assertFalse(review)

    def test_outage_negative_but_not_optout_untouched(self):
        suppress, review = stop_signal_decision(
            {"intent": "reply_negative", "fallback": True},
            "not interested right now", "Re: intro",
        )
        self.assertFalse(suppress)
        self.assertFalse(review)

    def test_no_classification_at_all(self):
        suppress, review = stop_signal_decision(None, "hello", "hi")
        self.assertFalse(suppress)
        self.assertFalse(review)


class TestProcessedMsgidLedger(unittest.TestCase):
    """The idempotency guard that stops the UNSEEN reprocessing loop."""

    def _use_tmp(self):
        import tempfile
        from integrations import email_engine as ee
        d = tempfile.mkdtemp(prefix="msgid_")
        self._orig = ee.PROCESSED_MSGIDS_PATH
        ee.PROCESSED_MSGIDS_PATH = Path(d) / "processed.json"
        self.addCleanup(setattr, ee, "PROCESSED_MSGIDS_PATH", self._orig)
        return ee

    def test_roundtrip(self):
        ee = self._use_tmp()
        self.assertEqual(ee._load_processed_msgids(), {})
        ee._save_processed_msgids({"<a@x>": "2026-07-24T00:00:00", "<b@x>": "2026-07-24T00:01:00"})
        got = ee._load_processed_msgids()
        self.assertIn("<a@x>", got)
        self.assertIn("<b@x>", got)

    def test_ring_buffer_caps_growth(self):
        ee = self._use_tmp()
        big = {f"<{i}@x>": f"2026-07-24T00:{i:02d}:00" for i in range(60)}
        orig = ee.PROCESSED_MSGIDS_MAX
        ee.PROCESSED_MSGIDS_MAX = 10
        self.addCleanup(setattr, ee, "PROCESSED_MSGIDS_MAX", orig)
        ee._save_processed_msgids(big)
        got = ee._load_processed_msgids()
        self.assertLessEqual(len(got), 10)
        # keeps the most-recent by timestamp
        self.assertIn("<59@x>", got)
        self.assertNotIn("<00@x>", got)

    def test_corrupt_file_degrades_to_empty(self):
        ee = self._use_tmp()
        ee.PROCESSED_MSGIDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ee.PROCESSED_MSGIDS_PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(ee._load_processed_msgids(), {})


class TestRoutingContract(unittest.TestCase):
    """The native form of the n8n <oasis-routing> contract the dashboard renders."""

    def test_financial_is_labelled_to_atlas(self):
        from integrations.email_engine import _routing_contract
        r = _routing_contract(
            {"category": "financial_legal", "action": "handoff_atlas",
             "reason": "x", "handed_off": True},
            {"intent": "platform_alert", "priority": "warm"})
        self.assertEqual(r["agent_label"], "atlas")
        self.assertEqual(r["intent"], "financial_legal")
        self.assertTrue(r["handed_off"])
        self.assertTrue(r["routing_extracted"])

    def test_non_financial_stays_with_bravo(self):
        from integrations.email_engine import _routing_contract
        for cat in ("technical_support", "business_opportunity", "low_priority"):
            r = _routing_contract({"category": cat, "action": "draft_hold"}, {})
            self.assertEqual(r["agent_label"], "bravo", cat)

    def test_unknown_category_defaults_safely(self):
        from integrations.email_engine import _routing_contract
        r = _routing_contract({}, {})
        self.assertEqual(r["intent"], "low_priority")
        self.assertEqual(r["agent_label"], "bravo")
        self.assertEqual(r["priority"], "cold")

    def test_exposes_the_keys_the_dashboard_renders(self):
        # oasis-command-center app/page.tsx reads cls.intent / cls.agent_action /
        # cls.summary at the TOP level of metadata.classification. The contract is
        # merged FLAT for that reason — renaming any of these blanks the inbound
        # card on the dashboard without any error surfacing.
        from integrations.email_engine import _routing_contract
        r = _routing_contract({"category": "technical_support", "action": "auto_reply",
                               "reason": "known client"}, {"priority": "hot"})
        for key in ("intent", "agent_action", "summary"):
            self.assertIn(key, r)
        self.assertEqual(r["agent_action"], "auto_reply")
        self.assertEqual(r["summary"], "known client")

    def test_flat_merge_overrides_legacy_intent(self):
        # Simulates _write_inbound_ledger's merge: routing must win on `intent`
        # so the dashboard tags the brain's category, not the keyword guess.
        from integrations.email_engine import _routing_contract
        classification = {"intent": "platform_alert", "priority": "warm",
                          "sentiment": "neutral"}
        merged = dict(classification)
        merged.update(_routing_contract({"category": "financial_legal",
                                         "action": "handoff_atlas"}, classification))
        self.assertEqual(merged["intent"], "financial_legal")
        self.assertEqual(merged["legacy_intent"], "platform_alert")
        self.assertEqual(merged["sentiment"], "neutral")  # legacy fields survive


class TestAttachmentMeta(unittest.TestCase):
    def test_extracts_pdf_attachment(self):
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        m = MIMEMultipart()
        m.attach(MIMEText("here's the invoice", "plain"))
        pdf = MIMEApplication(b"%PDF-1.4 fake bytes", _subtype="pdf")
        pdf.add_header("Content-Disposition", "attachment", filename="invoice.pdf")
        m.attach(pdf)
        meta = _extract_attachment_meta(m)
        self.assertEqual(len(meta), 1)
        self.assertEqual(meta[0]["filename"], "invoice.pdf")
        self.assertEqual(meta[0]["content_type"], "application/pdf")
        self.assertGreater(meta[0]["size"], 0)

    def test_no_attachments_returns_empty(self):
        from email.mime.text import MIMEText

        self.assertEqual(_extract_attachment_meta(MIMEText("plain email")), [])


class TestReviewMailIsTerminal(unittest.TestCase):
    """The `if review_ping:` branch in cmd_check_inbox must END the iteration.

    Structural, not string-counting: this walks the AST of the real function
    and asserts the branch's last statement is a `continue`, and that it
    contains no notify/classifier call.

    Why a test at all — from 2026-07-29 to 2026-08-08 the code above that
    branch CLAIMED "no LLM spend on machine mail", while the branch only
    enqueued and fell through. Every CI-failure email still hit the classifier
    and email_brain, and the brain Telegrammed CC. Five repos went red at once
    and CC got 53 notifications in two days. The comment was not the bug; the
    missing `continue` was, and a comment cannot fail a build.
    """

    def _review_branch(self):
        import ast
        import pathlib

        src = (pathlib.Path(__file__).resolve().parent.parent
               / "integrations" / "email_engine.py").read_text(encoding="utf-8")
        for fn in ast.walk(ast.parse(src)):
            if isinstance(fn, ast.FunctionDef) and fn.name == "cmd_check_inbox":
                for node in ast.walk(fn):
                    if (isinstance(node, ast.If)
                            and isinstance(node.test, ast.Name)
                            and node.test.id == "review_ping"):
                        return node
        self.fail("no `if review_ping:` branch found in cmd_check_inbox")

    def test_branch_ends_in_continue(self):
        import ast

        branch = self._review_branch()
        self.assertIsInstance(
            branch.body[-1], ast.Continue,
            "review-notification mail must not fall through to the classifier "
            "and email_brain — that is the notification loop this prevents")

    def test_branch_never_notifies(self):
        import ast

        branch = self._review_branch()
        called = {
            node.func.id for node in ast.walk(branch)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for banned in ("notify", "notify_cc", "notify_error", "process_email"):
            self.assertNotIn(
                banned, called,
                f"{banned}() inside the review branch re-opens the spam loop")

    def test_branch_still_queues_and_marks_read(self):
        """Suppressed must mean 'absorbed', never 'silently dropped'."""
        import ast

        branch = self._review_branch()
        dumped = ast.dump(branch)
        self.assertIn("_enqueue_review_harvest", dumped,
                      "the queue entry is the durable record the harvest cron drains")
        self.assertIn("processed_msgids", dumped,
                      "without the ledger write the next UNSEEN sweep reprocesses it")


if __name__ == "__main__":
    unittest.main(verbosity=2)
