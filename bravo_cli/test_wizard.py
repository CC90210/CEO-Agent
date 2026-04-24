"""Unit tests for the bravo setup wizard.

Covers the historically-fragile parts:
  - _ask_one choice matching (case-insensitive canon + partial + default)
  - prompt() EOF/Ctrl-C handling
  - print_banner uses the correct version string
  - PROFILES / AGENT_REPOS / PROFILE_QUESTIONS map consistency

Run:
  python bravo_cli/test_wizard.py
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bravo_cli import wizard as w  # noqa: E402


class _StdinCtx:
    """Replace stdin with an in-memory buffer for the duration of the block."""
    def __init__(self, text: str):
        self._text = text

    def __enter__(self):
        self._real = sys.stdin
        sys.stdin = io.StringIO(self._text)
        return self

    def __exit__(self, *a):
        sys.stdin = self._real


def _ask(choices, default, inputs):
    """Drive _ask_one with piped stdin; return (answer, prompt_call_count)."""
    q = {"prompt": "test", "type": "choice", "choices": choices, "default": default}
    count = [0]
    real_prompt = w.prompt

    def counting(*args, **kwargs):
        count[0] += 1
        if count[0] > 50:
            raise RuntimeError(f"loop guard hit — {count[0]} prompts")
        return real_prompt(*args, **kwargs)

    w.prompt = counting
    try:
        with _StdinCtx(inputs):
            ans = w._ask_one(q)
        return ans, count[0]
    finally:
        w.prompt = real_prompt


class TestAskOne(unittest.TestCase):
    """The 2026-04-24 Codex launch-blocker fix — never regress."""

    def test_empty_stdin_returns_default(self):
        ans, n = _ask(["real-estate", "saas", "services"], "services", "\n")
        self.assertEqual(ans, "services")
        self.assertEqual(n, 1)

    def test_uppercase_choices_lowercase_input(self):
        ans, _ = _ask(["MRR", "ARR", "Users"], "MRR", "mrr\n")
        self.assertEqual(ans, "MRR")

    def test_uppercase_choices_default_via_enter(self):
        # Previously dead-ended: default "MRR" was lowercased to "mrr" which
        # didn't match the original-case "MRR" in the choices list.
        ans, _ = _ask(["MRR", "ARR", "Users"], "MRR", "\n")
        self.assertEqual(ans, "MRR")

    def test_mixed_case_two_letter_country(self):
        ans, _ = _ask(["CA", "US", "UK", "EU", "AU"], "CA", "us\n")
        self.assertEqual(ans, "US")

    def test_partial_match_unique(self):
        ans, _ = _ask(["real-estate", "consulting", "services"], "services", "con\n")
        self.assertEqual(ans, "consulting")

    def test_partial_match_ambiguous_retries(self):
        # 'c' matches both CA and CAD. Re-prompt, then CA wins.
        ans, n = _ask(["CA", "CAD", "US"], "CA", "c\nCA\n")
        self.assertEqual(ans, "CA")
        self.assertEqual(n, 2)

    def test_invalid_recovers_to_valid(self):
        ans, n = _ask(["a", "b", "c"], "a", "xxx\nyyy\nb\n")
        self.assertEqual(ans, "b")
        self.assertEqual(n, 3)


class TestPromptEOF(unittest.TestCase):
    def test_prompt_exits_130_on_eof(self):
        with _StdinCtx(""):  # immediate EOF
            with self.assertRaises(SystemExit) as cm:
                w.prompt("x")
        self.assertEqual(cm.exception.code, 130)

    def test_prompt_returns_default_on_empty_line(self):
        with _StdinCtx("\n"):
            ans = w.prompt("x", default="yes")
        self.assertEqual(ans, "yes")


class TestProfileMapsConsistent(unittest.TestCase):
    """Every profile must exist in every map, or the wizard can crash mid-run."""

    def test_six_profiles_identical(self):
        expected = {"bravo", "atlas", "maven", "aura", "hermes", "custom"}
        self.assertEqual(set(w.PROFILES), expected)
        self.assertEqual(set(w.AGENT_REPOS), expected)
        self.assertEqual(set(w.PROFILE_QUESTIONS), expected)

    def test_each_profile_has_color_and_role(self):
        for slug, cfg in w.PROFILES.items():
            self.assertIn("color", cfg, f"{slug} missing color")
            self.assertIn("role", cfg, f"{slug} missing role")
            self.assertIn("required", cfg, f"{slug} missing required list")

    def test_every_choice_default_is_in_choices(self):
        # The Codex bug class: default not in choices => _ask_one loops forever.
        for profile, questions in w.PROFILE_QUESTIONS.items():
            for q in questions:
                if q.get("type") == "choice":
                    self.assertIn(
                        q.get("default"),
                        q["choices"],
                        f"{profile}/{q['key']}: default {q.get('default')!r} "
                        f"not in choices {q['choices']}",
                    )


class TestBannerVersion(unittest.TestCase):
    def test_banner_prints_current_version(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            w.print_banner()
        self.assertIn("V1.4", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
