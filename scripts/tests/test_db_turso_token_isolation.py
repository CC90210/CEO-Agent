"""A Turso URL must never authenticate with another product's token.

resolve_target() carefully excluded TURSO_DATA_BASE_URL (ig-setter-pro's
database URL) and then accepted TURSO_API_KEY — ig-setter-pro's database TOKEN —
as a fallback for TURSO_AUTH_TOKEN. One door guarded, the other left open.

The VPS is exactly that combination: TURSO_API_KEY present, TURSO_AUTH_TOKEN
absent. Setting TURSO_DATABASE_URL there would have authenticated the Bravo
harness with another product's credential and reported success.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db_turso import TursoConfigError, resolve_target  # noqa: E402

BRAVO_URL = "libsql://bravo-empire-cc90210.turso.io"
FOREIGN_TOKEN = "ig-setter-pro-token-value"


class TestTokenIsolation(unittest.TestCase):
    def test_api_key_is_not_accepted_as_the_auth_token(self):
        """The VPS's exact env shape must be refused, not silently used."""
        with self.assertRaises(TursoConfigError) as ctx:
            resolve_target({"TURSO_DATABASE_URL": BRAVO_URL,
                            "TURSO_API_KEY": FOREIGN_TOKEN})
        msg = str(ctx.exception)
        self.assertIn("TURSO_AUTH_TOKEN", msg)
        # The message has to name WHY, or the next person re-adds the fallback.
        self.assertIn("ig-setter-pro", msg)

    def test_the_foreign_token_never_leaks_into_the_result(self):
        """Belt and braces: even if it stopped raising, don't return that token."""
        try:
            _url, token, _mode = resolve_target({"TURSO_DATABASE_URL": BRAVO_URL,
                                                 "TURSO_API_KEY": FOREIGN_TOKEN})
        except TursoConfigError:
            return  # refusing is the correct behaviour
        self.assertNotEqual(token, FOREIGN_TOKEN,
                            "resolve_target handed back ig-setter-pro's token")

    def test_the_correct_pair_still_resolves(self):
        """The fix must not break the working configuration."""
        url, token, mode = resolve_target({"TURSO_DATABASE_URL": BRAVO_URL,
                                           "TURSO_AUTH_TOKEN": "real-bravo-token"})
        self.assertEqual(url, BRAVO_URL)
        self.assertEqual(token, "real-bravo-token")
        self.assertIn("remote", mode)

    def test_url_without_any_token_still_refuses(self):
        with self.assertRaises(TursoConfigError):
            resolve_target({"TURSO_DATABASE_URL": BRAVO_URL})

    def test_ig_setter_url_is_still_not_a_fallback(self):
        """The original guard must survive this change."""
        with self.assertRaises(TursoConfigError):
            resolve_target({"TURSO_DATA_BASE_URL": "libsql://ig-setter-pro.turso.io",
                            "TURSO_AUTH_TOKEN": "whatever"})


if __name__ == "__main__":
    unittest.main()
