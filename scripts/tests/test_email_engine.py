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


if __name__ == "__main__":
    unittest.main(verbosity=2)
