"""Tests for the 4-brain email category classifier (native n8n migration).

The n8n "OASIS Inbound Qualifier (Bravo Aware)" routed inbound email into
4 categories via a langchain textClassifier. This is the native, subscription-
CLI replacement: inbound_classifier.classify_category().

Run:
  python scripts/tests/test_inbound_category.py
  (or: pytest scripts/tests/test_inbound_category.py)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from inbound_classifier import (  # noqa: E402
    VALID_CATEGORIES,
    classify_category,
    normalize_category,
)


class TestNormalizeCategory(unittest.TestCase):
    def test_maps_the_four_n8n_labels(self):
        self.assertEqual(normalize_category("Client Technical Support"), "technical_support")
        self.assertEqual(normalize_category("Financial & Legal"), "financial_legal")
        self.assertEqual(normalize_category("Business Opportunities"), "business_opportunity")
        self.assertEqual(normalize_category("Low Priority & Archive"), "low_priority")

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(normalize_category("  FINANCIAL & legal \n"), "financial_legal")
        self.assertEqual(normalize_category("business opportunities"), "business_opportunity")

    def test_accepts_canonical_snake_case(self):
        for c in VALID_CATEGORIES:
            self.assertEqual(normalize_category(c), c)

    def test_partial_keyword_match(self):
        self.assertEqual(normalize_category("this is a financial matter"), "financial_legal")
        self.assertEqual(normalize_category("technical support ticket"), "technical_support")

    def test_unknown_defaults_low_priority(self):
        # Unknown → low_priority for the taxonomy; the AUTONOMY layer
        # (decide_action) is what fail-safes uncertain low-confidence
        # classifications to human review, so this default is safe.
        self.assertEqual(normalize_category("kjsdfkjsdf"), "low_priority")
        self.assertEqual(normalize_category(""), "low_priority")
        self.assertEqual(normalize_category(None), "low_priority")


class TestClassifyCategory(unittest.TestCase):
    def test_parses_json_runner_output(self):
        def runner(prompt, system=None, model="haiku", timeout=90):
            return '{"category": "Financial & Legal", "confidence": 0.91}'

        r = classify_category(
            content="Invoice #1042 attached, payment due net 30",
            subject="Your invoice",
            from_identity="billing@vendor.example",
            runner=runner,
        )
        self.assertEqual(r["category"], "financial_legal")
        self.assertAlmostEqual(r["confidence"], 0.91, places=2)
        self.assertFalse(r["fallback"])

    def test_parses_bare_label_runner_output(self):
        def runner(prompt, system=None, model="haiku", timeout=90):
            return "Business Opportunities"

        r = classify_category(
            content="Saw your post — would love a demo call next week",
            subject="Intro",
            from_identity="cto@prospect.example",
            runner=runner,
        )
        self.assertEqual(r["category"], "business_opportunity")
        self.assertFalse(r["fallback"])

    def test_runner_none_falls_back_to_keywords(self):
        def runner(prompt, system=None, model="haiku", timeout=90):
            return None  # CLI unavailable

        r = classify_category(
            content="Please find attached the receipt for your payment",
            subject="Receipt",
            from_identity="noreply@stripe.com",
            runner=runner,
        )
        self.assertTrue(r["fallback"])
        self.assertEqual(r["category"], "financial_legal")
        self.assertLessEqual(r["confidence"], 0.6)

    def test_runner_raises_falls_back(self):
        def runner(prompt, system=None, model="haiku", timeout=90):
            raise RuntimeError("boom")

        r = classify_category(
            content="unsubscribe from this newsletter",
            subject="Weekly digest",
            from_identity="news@marketing.example",
            runner=runner,
        )
        self.assertTrue(r["fallback"])
        self.assertEqual(r["category"], "low_priority")

    def test_fallback_detects_support_signal(self):
        def runner(prompt, system=None, model="haiku", timeout=90):
            return None

        r = classify_category(
            content="the automation you built is broken and throwing errors, please help",
            subject="urgent: workflow down",
            from_identity="ops@client.example",
            runner=runner,
        )
        self.assertTrue(r["fallback"])
        self.assertEqual(r["category"], "technical_support")

    def test_result_always_has_contract_keys(self):
        def runner(prompt, system=None, model="haiku", timeout=90):
            return '{"category":"garbage","confidence":"notanumber"}'

        r = classify_category(content="hi", subject="hi", from_identity="a@b.example", runner=runner)
        for k in ("category", "confidence", "fallback", "notes"):
            self.assertIn(k, r)
        self.assertIn(r["category"], VALID_CATEGORIES)
        self.assertIsInstance(r["confidence"], float)


if __name__ == "__main__":
    unittest.main(verbosity=2)
