"""The lossy audit must FAIL when something is actually missing.

A gate that has only ever returned PASS is not evidence. This drives the audit
through the three states that matter, with the database faked so the assertions
are about the gate's logic rather than today's data:

  a lost view still absent  -> exit 1   (the merchant_summary case, reproduced)
  a lost view now present   -> exit 0
  a secret default NULL     -> exit 1
  database unreachable      -> exit 2   (never a silent pass)

The middle case matters as much as the failures: an audit that fails on
everything gets switched off within a week.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import turso_lossy_audit as audit  # noqa: E402


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    """Minimal stand-in: knows which objects exist and which columns are NULL."""

    def __init__(self, objects: dict[str, str], nulls: dict[str, int] | None = None):
        self._objects = objects
        self._nulls = nulls or {}

    def execute(self, sql, *args):
        if "sqlite_master" in sql:
            return FakeCursor([(name, kind) for name, kind in self._objects.items()])
        if "COUNT(*)" in sql and "IS NULL" in sql:
            # 'SELECT COUNT(*) FROM "t" WHERE "c" IS NULL'
            table = sql.split('FROM "')[1].split('"')[0]
            column = sql.split('WHERE "')[1].split('"')[0]
            return FakeCursor([(self._nulls.get(f"{table}.{column}", 0),)])
        raise AssertionError(f"unexpected sql: {sql}")


def write_report(dirpath: Path, project: str, lossy: dict) -> None:
    (dirpath / f"{project}__transpile_report.json").write_text(
        json.dumps({"project": project, "table_count": 1, "lossy": lossy}),
        encoding="utf-8")


class TestLossyAudit(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self._orig_migrations = audit.MIGRATIONS
        self._orig_connect = audit.connect
        audit.MIGRATIONS = self.dir

    def tearDown(self):
        audit.MIGRATIONS = self._orig_migrations
        audit.connect = self._orig_connect
        self._tmp.cleanup()

    def _run(self, argv=()):
        old = sys.argv
        sys.argv = ["turso_lossy_audit.py", *argv]
        try:
            return audit.main()
        finally:
            sys.argv = old

    def test_a_lost_view_that_is_still_missing_fails(self):
        """The exact defect this exists for: reported lost, never ported."""
        write_report(self.dir, "bravo", {
            "VIEWS_LOST": ["merchant_summary: needs manual port - WITH ranked_apps AS ("],
        })
        audit.connect = lambda project: (FakeConn({"tenant_records": "table"}), None)
        self.assertEqual(self._run(), 1,
                         "a view reported lost and still absent must FAIL the gate")

    def test_the_same_view_once_ported_passes(self):
        """Without this, the gate fails forever and gets disabled."""
        write_report(self.dir, "bravo", {
            "VIEWS_LOST": ["merchant_summary: needs manual port - WITH ranked_apps AS ("],
        })
        audit.connect = lambda project: (
            FakeConn({"tenant_records": "table", "merchant_summary": "view"}), None)
        self.assertEqual(self._run(), 0)

    def test_a_null_secret_column_fails(self):
        """A dropped gen_random_bytes default that is actually producing NULLs."""
        write_report(self.dir, "propflow", {
            "defaults_dropped": [
                "platform_invitations.token: encode(gen_random_bytes(32), 'hex'::text)"],
        })
        audit.connect = lambda project: (
            FakeConn({"platform_invitations": "table"},
                     {"platform_invitations.token": 3}), None)
        self.assertEqual(self._run(), 1,
                         "NULL invitation tokens must FAIL, not be reported quietly")

    def test_the_same_column_with_no_nulls_passes(self):
        write_report(self.dir, "propflow", {
            "defaults_dropped": [
                "platform_invitations.token: encode(gen_random_bytes(32), 'hex'::text)"],
        })
        audit.connect = lambda project: (
            FakeConn({"platform_invitations": "table"},
                     {"platform_invitations.token": 0}), None)
        self.assertEqual(self._run(), 0)

    def test_an_unreachable_database_is_not_a_pass(self):
        """The failure mode that would make this whole check theatre."""
        write_report(self.dir, "bravo", {"VIEWS_LOST": ["merchant_summary: needs manual port"]})
        audit.connect = lambda project: (None, "auth token rejected")
        self.assertEqual(self._run(), 2,
                         "an unverifiable database must not report success")

    def test_postgres_only_losses_do_not_fail_the_gate(self):
        """gin indexes and auth.users FKs have no SQLite equivalent by design."""
        write_report(self.dir, "bravo", {
            "indexes_skipped": [
                "idx_memories_tags: CREATE INDEX idx_memories_tags ON public.memories USING gin (tags)"],
            "cross_schema_fks_dropped": ["agents(created_by) -> auth.users"],
        })
        audit.connect = lambda project: (FakeConn({"memories": "table"}), None)
        self.assertEqual(self._run(), 0,
                         "expected, unavoidable losses must not cry wolf")

    def test_a_plain_index_is_separated_from_a_postgres_only_one(self):
        """A skipped btree may be a real dedup loss; a skipped gin never is."""
        write_report(self.dir, "bravo", {
            "indexes_skipped": [
                "idx_a: CREATE INDEX idx_a ON public.t USING gin (tags)",
                "idx_b: CREATE INDEX idx_b ON public.t USING btree (tenant_id, x)",
            ],
        })
        audit.connect = lambda project: (FakeConn({"t": "table"}), None)
        report = json.loads(
            json.dumps(audit.audit("bravo", {"lossy": {
                "indexes_skipped": [
                    "idx_a: CREATE INDEX idx_a ON public.t USING gin (tags)",
                    "idx_b: CREATE INDEX idx_b ON public.t USING btree (tenant_id, x)",
                ]}})))
        self.assertEqual(report["skipped_pg_only_indexes"], 1)
        self.assertEqual(report["skipped_btree_indexes"], ["idx_b"])


if __name__ == "__main__":
    unittest.main()
