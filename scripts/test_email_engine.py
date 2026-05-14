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

from email_engine import (  # noqa: E402
    TemplateRenderError,
    missing_template_variables,
    normalize_template_vars,
    render_template,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
