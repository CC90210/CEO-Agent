"""Upserts must find the real ON CONFLICT target, expression index or not.

Postgres `UNIQUE ... NULLS NOT DISTINCT` transpiles into a SQLite EXPRESSION
index -- UNIQUE (email, COALESCE(tenant_id,'...')). SQLite matches an
ON CONFLICT target against an index's columns AND expressions exactly, so a
bare column list matches nothing and the whole statement is rejected.

That is not hypothetical. It silently disabled the CASL unsubscribe endpoint:
nothing reached email_suppressions between the Turso cutover and the fix, and
two of the four write paths never read `.error`, so they reported success while
persisting nothing. bravo.cold_leads carries the same index shape, where a
failing upsert means duplicate cold outreach to the same lead.

These run against a real libSQL database. The defect is in SQL semantics; a mock
would agree with a wrong query.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db_turso import TursoDB  # noqa: E402
from lib.turso_supabase_compat import (  # noqa: E402
    _CONFLICT_TARGET_CACHE,
    TursoSupabaseCompat,
)

SENTINEL = "\\u001f__null__"   # literal text, exactly as the transpiler emits it


class TestConflictTargetResolution(unittest.TestCase):
    def setUp(self):
        _CONFLICT_TARGET_CACHE.clear()
        # ignore_cleanup_errors: on Windows a libSQL handle can outlive the
        # close() below -- the reconnect path opens a second one -- and an
        # undeletable temp file would fail an otherwise passing test.
        self._tmp = TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = TursoDB(str(Path(self._tmp.name) / "t.db"), None, "local(test)")

        # Mirrors the real transpiled shape of email_suppressions.
        self.db.execute(
            "CREATE TABLE email_suppressions ("
            " id TEXT PRIMARY KEY, email TEXT, tenant_id TEXT, brand TEXT,"
            " reason TEXT, source TEXT)",
            [], allow_unscoped=True, reason="schema")
        self.db.execute(
            f"CREATE UNIQUE INDEX email_suppressions_unique ON email_suppressions "
            f"(email, COALESCE (tenant_id, '{SENTINEL}'), "
            f"COALESCE (brand, '{SENTINEL}'))",
            [], allow_unscoped=True, reason="schema")

        # An ordinary plain-column unique index, to prove nothing changed there.
        self.db.execute(
            "CREATE TABLE plain_tbl (id TEXT PRIMARY KEY, k TEXT, v TEXT)",
            [], allow_unscoped=True, reason="schema")
        self.db.execute(
            "CREATE UNIQUE INDEX plain_tbl_k ON plain_tbl (k)",
            [], allow_unscoped=True, reason="schema")
        self.db.commit()
        self.client = TursoSupabaseCompat(self.db)

    def tearDown(self):
        try:
            conn = getattr(self.db, "_conn", None)
            if conn is not None and hasattr(conn, "close"):
                conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._tmp.cleanup()

    def test_upsert_against_an_expression_index_succeeds(self):
        """Before the fix this raised 'ON CONFLICT clause does not match'."""
        r = self.client.table("email_suppressions").upsert(
            {"id": "1", "email": "a@b.c", "tenant_id": None, "brand": None,
             "reason": "unsub", "source": "web_form"},
            on_conflict="email,tenant_id,brand").execute()
        self.assertTrue(r.data, "the upsert wrote nothing -- the opt-out is lost")

        rows = self.db.query("SELECT email, reason FROM email_suppressions",
                             [], allow_unscoped=True, reason="read")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["email"], "a@b.c")

    def test_the_same_key_updates_rather_than_duplicating(self):
        for reason in ("first", "second"):
            self.client.table("email_suppressions").upsert(
                {"id": "1", "email": "a@b.c", "tenant_id": None, "brand": None,
                 "reason": reason, "source": "web_form"},
                on_conflict="email,tenant_id,brand").execute()
        rows = self.db.query("SELECT reason FROM email_suppressions",
                             [], allow_unscoped=True, reason="read")
        self.assertEqual(len(rows), 1, "the upsert DUPLICATED instead of updating")
        self.assertEqual(rows[0]["reason"], "second")

    def test_nulls_are_not_distinct_two_nulls_are_the_same_row(self):
        """The whole point of the COALESCE index: NULL tenant collides."""
        self.client.table("email_suppressions").upsert(
            {"id": "1", "email": "x@y.z", "tenant_id": None, "brand": None,
             "reason": "a", "source": "s"}, on_conflict="email,tenant_id,brand").execute()
        self.client.table("email_suppressions").upsert(
            {"id": "2", "email": "x@y.z", "tenant_id": None, "brand": None,
             "reason": "b", "source": "s"}, on_conflict="email,tenant_id,brand").execute()
        rows = self.db.query("SELECT reason FROM email_suppressions",
                             [], allow_unscoped=True, reason="read")
        self.assertEqual(len(rows), 1,
                         "two NULL-tenant rows for one email -- NULLS NOT DISTINCT lost")

    def test_column_order_in_on_conflict_does_not_matter(self):
        """Callers write the order that reads well; the index has its own."""
        r = self.client.table("email_suppressions").upsert(
            {"id": "1", "email": "a@b.c", "tenant_id": None, "brand": None,
             "reason": "r", "source": "s"},
            on_conflict="brand,email,tenant_id").execute()
        self.assertTrue(r.data)

    def test_a_plain_column_index_is_left_alone(self):
        """Ordinary tables must generate exactly the SQL they did before."""
        from lib.turso_supabase_compat import CompatQuery

        q = CompatQuery(self.db, "plain_tbl")
        self.assertIsNone(q._resolve_conflict_target(["k"]),
                          "a plain index was rewritten; that risks changing "
                          "behaviour on every ordinary table")

        for v in ("one", "two"):
            self.client.table("plain_tbl").upsert(
                {"id": "1", "k": "K", "v": v}, on_conflict="k").execute()
        rows = self.db.query("SELECT v FROM plain_tbl", [], allow_unscoped=True,
                             reason="read")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["v"], "two")

    def test_the_sentinel_string_is_not_mistaken_for_a_column(self):
        """The bug that made the first fix a no-op.

        An identifier regex over the raw index expression also matches inside
        the literal '__null__', yielding a phantom column, so the set never
        matched and resolution silently returned None.
        """
        from lib.turso_supabase_compat import CompatQuery

        q = CompatQuery(self.db, "email_suppressions")
        target = q._resolve_conflict_target(["email", "tenant_id", "brand"])
        self.assertIsNotNone(
            target, "resolution returned None -- the sentinel was counted as a column")
        self.assertIn("COALESCE", target.upper())

    def test_an_unknown_column_set_falls_back_rather_than_guessing(self):
        from lib.turso_supabase_compat import CompatQuery

        q = CompatQuery(self.db, "email_suppressions")
        self.assertIsNone(q._resolve_conflict_target(["email"]),
                          "matched an index that does not cover these columns")


if __name__ == "__main__":
    unittest.main()
