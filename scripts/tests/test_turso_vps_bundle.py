"""The credential bundle must refuse to hand over a file that does not work.

Two transfer attempts to the VPS failed, both reporting a 401, and both looked
fine on inspection: the first was a truncated token, the second was two entirely
different keys (TURSO_OASIS_PLATFORM_URL and TURSO_API_KEY) sitting under the
canonical names. Line count and value length passed in both cases.

So the bundle tool verifies by CONNECTING. These tests prove that check bites,
using the real failure shapes rather than invented ones.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import secret_loader  # noqa: E402
from turso_vps_bundle import KEYS, verify_bundle  # noqa: E402


def _write(dirpath: Path, pairs: dict[str, str]) -> Path:
    p = dirpath / "bundle.env"
    p.write_text("".join(f"{k}={v}\n" for k, v in pairs.items()), encoding="utf-8")
    return p


class TestBundleVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        secret_loader.reset_cache()
        cls.env = secret_loader.load_env()
        if not all(cls.env.get(k) for k in KEYS):
            raise unittest.SkipTest("Turso credentials not in the agents env")

    def test_the_correct_pair_verifies(self):
        with TemporaryDirectory() as tmp:
            p = _write(Path(tmp), {k: self.env[k] for k in KEYS})
            ok, detail = verify_bundle(p)
            self.assertTrue(ok, f"the working pair was rejected: {detail}")
            self.assertIn("bravo confirmed", detail)

    def test_the_exact_wrong_pair_from_the_vps_is_refused(self):
        """TURSO_OASIS_PLATFORM_URL + TURSO_API_KEY — the real incident."""
        oasis = self.env.get("TURSO_OASIS_PLATFORM_URL")
        api_key = self.env.get("TURSO_API_KEY")
        if not (oasis and api_key):
            self.skipTest("the wrong-pair keys are not present to reproduce with")
        with TemporaryDirectory() as tmp:
            p = _write(Path(tmp), {"TURSO_DATABASE_URL": oasis,
                                   "TURSO_AUTH_TOKEN": api_key})
            ok, _detail = verify_bundle(p)
            self.assertFalse(ok, "the pair that 401'd on the VPS was accepted")

    def test_a_truncated_token_is_refused(self):
        """The first failure mode: a wrapped paste losing the signature."""
        with TemporaryDirectory() as tmp:
            p = _write(Path(tmp), {"TURSO_DATABASE_URL": self.env["TURSO_DATABASE_URL"],
                                   "TURSO_AUTH_TOKEN": self.env["TURSO_AUTH_TOKEN"][:194]})
            ok, _ = verify_bundle(p)
            self.assertFalse(ok, "a truncated token was accepted")

    def test_a_right_token_against_the_wrong_database_is_refused(self):
        """Auth succeeding is not the same as reaching the right database."""
        oasis = self.env.get("TURSO_OASIS_PLATFORM_URL")
        oasis_tok = self.env.get("OASIS_TURSO_AUTH_TOKEN")
        if not (oasis and oasis_tok):
            self.skipTest("oasis credentials not present")
        with TemporaryDirectory() as tmp:
            # A perfectly valid pair — for the WRONG database. tenant_records is
            # a bravo table, so this must still fail.
            p = _write(Path(tmp), {"TURSO_DATABASE_URL": oasis,
                                   "TURSO_AUTH_TOKEN": oasis_tok})
            ok, _ = verify_bundle(p)
            self.assertFalse(ok, "a valid pair for the WRONG database was accepted")

    def test_cosmetic_mangling_the_real_loader_normalises_still_verifies(self):
        """Match the far side exactly — no stricter, no looser.

        A first draft rejected these. But secret_loader's _parse_env strips
        whitespace and surrounding quotes, so such a file WOULD work on the VPS
        and refusing it is a false alarm that sends someone chasing a
        non-problem. CRLF is likewise invisible: splitlines() consumes it.
        """
        for label, mangle in (("quoted", lambda v: f'"{v}"'),
                              ("trailing space", lambda v: v + " "),
                              ("CRLF line ending", lambda v: v + "\r")):
            with self.subTest(mangling=label), TemporaryDirectory() as tmp:
                p = _write(Path(tmp), {
                    "TURSO_DATABASE_URL": self.env["TURSO_DATABASE_URL"],
                    "TURSO_AUTH_TOKEN": mangle(self.env["TURSO_AUTH_TOKEN"])})
                ok, detail = verify_bundle(p)
                self.assertTrue(ok, f"{label} was refused, but the loader "
                                    f"normalises it: {detail}")

    def test_the_verifier_parses_exactly_like_the_loader(self):
        """Pin the loader's actual semantics, including one sharp edge.

        _parse_env does `value.strip().strip('"').strip("'")` — strip runs
        BEFORE quote removal. So outer whitespace goes, surrounding quotes go,
        but whitespace INSIDE quotes survives. A value written as `" tok "`
        therefore reaches the client as ` tok ` and fails auth, while `"tok"`
        is fine. That is not obvious from reading the call, and it is exactly
        the class of thing that produced two opaque 401s on the VPS.
        """
        from lib.secret_loader import _parse_env

        cases = {
            'X=tok': "tok",
            'X="tok"': "tok",            # quotes stripped
            "X='tok'": "tok",            # single quotes too
            'X=  tok  ': "tok",          # outer whitespace stripped
            'X=" tok "': " tok ",        # NOT stripped — strip() ran first
        }
        for raw, expected in cases.items():
            with self.subTest(line=raw):
                self.assertEqual(_parse_env(raw + "\n").get("X"), expected)

        # CRLF is consumed by splitlines(), so it never reaches a value.
        self.assertEqual(_parse_env("X=tok\r\n").get("X"), "tok")

    def test_a_missing_key_is_refused(self):
        with TemporaryDirectory() as tmp:
            p = _write(Path(tmp), {"TURSO_DATABASE_URL": self.env["TURSO_DATABASE_URL"]})
            ok, detail = verify_bundle(p)
            self.assertFalse(ok)
            self.assertIn("missing", detail)


if __name__ == "__main__":
    unittest.main()
