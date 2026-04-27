"""Tests for scripts/name_utils.py.

Run: python scripts/test_name_utils.py

These tests codify the "Hi Contact," disaster fix (2026-04-25). The
sanitizer is the render-path defense — even if upstream CRM data is
junk, what reaches a real recipient must be a sane salutation.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from name_utils import (
    PLACEHOLDER_FIRST_NAMES,
    safe_first_name,
    safe_full_name,
    sanitize_template_vars,
)


class TestSafeFirstName(unittest.TestCase):

    def test_real_name_passes_through(self):
        self.assertEqual(safe_first_name("Jonathan"), "Jonathan")
        self.assertEqual(safe_first_name("Emon"), "Emon")
        self.assertEqual(safe_first_name("Bev Drexler"), "Bev Drexler")

    def test_real_name_strips_whitespace(self):
        self.assertEqual(safe_first_name("  Jonathan  "), "Jonathan")
        self.assertEqual(safe_first_name("\tEmon\n"), "Emon")

    def test_real_name_preserves_casing(self):
        self.assertEqual(safe_first_name("jonathan"), "jonathan")
        self.assertEqual(safe_first_name("JONATHAN"), "JONATHAN")
        self.assertEqual(safe_first_name("McKenna"), "McKenna")

    def test_known_placeholders_blocked(self):
        # The exact failure mode from 2026-04-25.
        self.assertEqual(safe_first_name("Contact"), "team")
        self.assertEqual(safe_first_name("contact"), "team")
        self.assertEqual(safe_first_name("CONTACT"), "team")
        self.assertEqual(safe_first_name("  Contact  "), "team")
        self.assertEqual(safe_first_name("Owner"), "team")
        self.assertEqual(safe_first_name("Owner/Manager"), "team")
        self.assertEqual(safe_first_name("info"), "team")
        self.assertEqual(safe_first_name("there"), "team")

    def test_empty_and_none_blocked(self):
        self.assertEqual(safe_first_name(""), "team")
        self.assertEqual(safe_first_name("   "), "team")
        self.assertEqual(safe_first_name(None), "team")

    def test_non_string_blocked(self):
        self.assertEqual(safe_first_name(123), "team")
        self.assertEqual(safe_first_name([]), "team")
        self.assertEqual(safe_first_name({}), "team")

    def test_punctuation_only_blocked(self):
        self.assertEqual(safe_first_name("..."), "team")
        self.assertEqual(safe_first_name("---"), "team")
        self.assertEqual(safe_first_name("???"), "team")
        self.assertEqual(safe_first_name("123"), "team")

    def test_custom_fallback_respected(self):
        self.assertEqual(safe_first_name("Contact", fallback="friend"), "friend")
        self.assertEqual(safe_first_name(None, fallback="there"), "there")


class TestSafeFullName(unittest.TestCase):

    def test_default_fallback_is_there(self):
        self.assertEqual(safe_full_name("Contact"), "there")
        self.assertEqual(safe_full_name(""), "there")
        self.assertEqual(safe_full_name(None), "there")

    def test_real_full_name_passes_through(self):
        self.assertEqual(safe_full_name("Jonathan Hutton"), "Jonathan Hutton")

    def test_email_body_rendering_safe(self):
        # The exact line from outreach_engine.build_email_body.
        for placeholder in ("Contact", "Owner", "", None, "info", "  "):
            name = safe_full_name(placeholder)
            body = f"Hi {name},"
            self.assertEqual(body, "Hi there,")


class TestSanitizeTemplateVars(unittest.TestCase):

    def test_first_name_placeholder_replaced(self):
        result = sanitize_template_vars({"first_name": "Contact"})
        self.assertEqual(result["first_name"], "team")

    def test_first_name_real_preserved(self):
        result = sanitize_template_vars({"first_name": "Jonathan"})
        self.assertEqual(result["first_name"], "Jonathan")

    def test_other_keys_passed_through(self):
        # company is intentionally NOT sanitized.
        result = sanitize_template_vars({
            "first_name": "Contact",
            "company": "Basque Landscaping",
            "industry": "landscaping",
        })
        self.assertEqual(result["first_name"], "team")
        self.assertEqual(result["company"], "Basque Landscaping")
        self.assertEqual(result["industry"], "landscaping")

    def test_missing_first_name_filled_with_fallback(self):
        result = sanitize_template_vars({"company": "Acme Co"})
        self.assertEqual(result["first_name"], "team")
        self.assertEqual(result["company"], "Acme Co")

    def test_returns_copy_not_mutating_input(self):
        original = {"first_name": "Contact"}
        result = sanitize_template_vars(original)
        self.assertEqual(original["first_name"], "Contact")
        self.assertEqual(result["first_name"], "team")

    def test_non_dict_passes_through_untouched(self):
        # Defensive: a misuse should not crash the send path.
        self.assertEqual(sanitize_template_vars(None), None)
        self.assertEqual(sanitize_template_vars("not a dict"), "not a dict")

    def test_custom_key_and_fallback(self):
        result = sanitize_template_vars(
            {"recipient": "Contact"},
            key="recipient",
            fallback="friend",
        )
        self.assertEqual(result["recipient"], "friend")


class TestPlaceholderSet(unittest.TestCase):

    def test_csv_import_disaster_placeholders_covered(self):
        # The literal string from the 2026-04-25 sends.
        self.assertIn("contact", PLACEHOLDER_FIRST_NAMES)

    def test_generic_inbox_aliases_covered(self):
        for alias in ("info", "support", "sales", "admin", "office",
                      "reception", "hello", "team"):
            self.assertIn(alias, PLACEHOLDER_FIRST_NAMES,
                          f"{alias!r} should be in PLACEHOLDER_FIRST_NAMES")

    def test_lazy_dev_aliases_covered(self):
        for alias in ("none", "null", "n/a", "unknown", "first_name", "name"):
            self.assertIn(alias, PLACEHOLDER_FIRST_NAMES,
                          f"{alias!r} should be in PLACEHOLDER_FIRST_NAMES")


if __name__ == "__main__":
    unittest.main(verbosity=2)
