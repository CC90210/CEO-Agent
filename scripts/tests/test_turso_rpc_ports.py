"""The five RPC ports, and the two silent-failure defects they exposed.

Every case here is a real production path that a 49-agent audit of the VPS
cutover found would fail SILENTLY under Turso -- succeed-shaped return values,
no exception, no log, work simply not done. That is worse than an outage,
because nothing surfaces it. So each test asserts the port does the work AND
that the failure mode is loud.

Runs against a real libSQL file database, not mocks: the defects being fixed are
in SQL semantics (RETURNING, json_patch, json_valid) and a mock would happily
agree with a wrong query.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db_turso import TursoDB  # noqa: E402
from lib.turso_supabase_compat import (  # noqa: E402
    RPC_REGISTRY,
    CompatError,
    TursoSupabaseCompat,
)

SCHEMA = """
CREATE TABLE sequence_state (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    status TEXT,
    scheduled_for TEXT,
    claimed_at TEXT,
    claimed_by TEXT,
    step_index INTEGER DEFAULT 0
);
CREATE TABLE tenant_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    data TEXT
);
CREATE TABLE agent_events (
    id TEXT PRIMARY KEY,
    status TEXT,
    target_agent TEXT,
    processed_by TEXT,
    processed_at TEXT,
    visibility_until TEXT,
    published_at TEXT,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    consumed_by TEXT
);
CREATE TABLE queue (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    payload TEXT
);
"""


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        path = str(Path(self._tmp.name) / "t.db")
        self.db = TursoDB(path, None, "local(test)")
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                self.db.execute(stmt, [], allow_unscoped=True, reason="test schema")
        self.db.commit()
        self.client = TursoSupabaseCompat(self.db)

    def tearDown(self):
        # Close before cleanup: on Windows an open libSQL handle keeps the file
        # locked and TemporaryDirectory.cleanup() raises WinError 32, turning
        # every passing test into a red one.
        try:
            conn = getattr(self.db, "_conn", None)
            if conn is not None and hasattr(conn, "close"):
                conn.close()
        except Exception:  # noqa: BLE001 - teardown must not mask a real failure
            pass
        self._tmp.cleanup()

    def _seq(self, rid, status="scheduled", claimed_at=None):
        self.db.execute(
            "INSERT INTO sequence_state (id, tenant_id, status, claimed_at) "
            "VALUES (?, 'sun', ?, ?)", [rid, status, claimed_at],
            allow_unscoped=True, reason="test fixture")
        self.db.commit()


class TestSequenceClaim(_Base):
    """Without this port the drip engine dispatches zero sends, forever."""

    def test_a_scheduled_row_is_claimed_and_returned(self):
        self._seq("r1")
        out = RPC_REGISTRY["claim_sequence_state_row"](
            self.db, {"row_id": "r1", "claimer": "worker-a"})
        self.assertEqual(len(out), 1, "the claim returned no row, so the caller "
                                      "would skip a row it actually won")
        self.assertEqual(out[0]["id"], "r1")
        self.assertEqual(out[0]["claimed_by"], "worker-a")

    def test_only_one_of_two_racing_workers_wins(self):
        """The entire reason this RPC exists: two dispatches of one message."""
        self._seq("r2")
        a = RPC_REGISTRY["claim_sequence_state_row"](
            self.db, {"row_id": "r2", "claimer": "worker-a"})
        b = RPC_REGISTRY["claim_sequence_state_row"](
            self.db, {"row_id": "r2", "claimer": "worker-b"})
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 0, "both workers claimed the same row -- the "
                                    "lead would receive the message twice")

    def test_a_row_that_is_not_scheduled_is_never_claimed(self):
        for status in ("sent", "failed", "cancelled", "suppressed"):
            with self.subTest(status=status):
                rid = f"r-{status}"
                self._seq(rid, status=status)
                out = RPC_REGISTRY["claim_sequence_state_row"](
                    self.db, {"row_id": rid, "claimer": "w"})
                self.assertEqual(out, [], f"claimed a {status} row")

    def test_release_makes_a_cooldowned_row_claimable_again(self):
        self._seq("r3")
        RPC_REGISTRY["claim_sequence_state_row"](self.db, {"row_id": "r3"})
        again = RPC_REGISTRY["claim_sequence_state_row"](self.db, {"row_id": "r3"})
        self.assertEqual(again, [], "precondition: still claimed")

        RPC_REGISTRY["release_sequence_state_claim"](self.db, {"row_id": "r3"})
        out = RPC_REGISTRY["claim_sequence_state_row"](self.db, {"row_id": "r3"})
        self.assertEqual(len(out), 1, "a released row stayed stuck -- every "
                                      "cooldowned row would be stranded forever")

    def test_the_default_claimer_matches_the_postgres_default(self):
        self._seq("r4")
        out = RPC_REGISTRY["claim_sequence_state_row"](self.db, {"row_id": "r4"})
        self.assertEqual(out[0]["claimed_by"], "sequence_runner")


class TestPatchTenantRecordData(_Base):
    """Without this port, resume_lead reports success and does nothing."""

    def _rec(self, rid, data):
        self.db.execute("INSERT INTO tenant_records (id, tenant_id, data) "
                        "VALUES (?, 'sun', ?)", [rid, data],
                        allow_unscoped=True, reason="test fixture")
        self.db.commit()

    def _data(self, rid):
        import json
        rows = self.db.query("SELECT data FROM tenant_records WHERE id = ?", [rid],
                             allow_unscoped=True, reason="test read")
        return json.loads(rows[0]["data"])

    def test_the_patch_merges_and_leaves_other_keys_alone(self):
        self._rec("t1", '{"paused": true, "owner": "cc", "score": 7}')
        RPC_REGISTRY["patch_tenant_record_data"](
            self.db, {"p_id": "t1", "p_tenant_id": "sun",
                      "p_patch": {"paused": False}})
        d = self._data("t1")
        self.assertIs(d["paused"], False, "the resume never landed")
        self.assertEqual(d["owner"], "cc", "an unrelated key was destroyed")
        self.assertEqual(d["score"], 7)

    def test_a_null_in_the_patch_does_not_delete_the_key(self):
        """jsonb || keeps a null; json_patch deletes. Semantics must match."""
        self._rec("t2", '{"a": 1, "b": 2}')
        RPC_REGISTRY["patch_tenant_record_data"](
            self.db, {"p_id": "t2", "p_tenant_id": "sun",
                      "p_patch": {"a": None, "c": 3}})
        d = self._data("t2")
        self.assertIn("a", d, "a null in the patch deleted an existing key")
        self.assertEqual(d["c"], 3)

    def test_a_patch_matching_no_row_RAISES_rather_than_reporting_success(self):
        with self.assertRaises(CompatError):
            RPC_REGISTRY["patch_tenant_record_data"](
                self.db, {"p_id": "nope", "p_tenant_id": "sun",
                          "p_patch": {"paused": False}})

    def test_the_wrong_tenant_cannot_patch_another_tenants_record(self):
        self._rec("t3", '{"paused": true}')
        with self.assertRaises(CompatError):
            RPC_REGISTRY["patch_tenant_record_data"](
                self.db, {"p_id": "t3", "p_tenant_id": "someone-else",
                          "p_patch": {"paused": False}})
        self.assertIs(self._data("t3")["paused"], True, "cross-tenant write landed")

    def test_a_null_data_column_is_patchable(self):
        self._rec("t4", None)
        RPC_REGISTRY["patch_tenant_record_data"](
            self.db, {"p_id": "t4", "p_tenant_id": "sun", "p_patch": {"x": 1}})
        self.assertEqual(self._data("t4")["x"], 1)


class TestRawSqlPorts(_Base):
    def test_query_sql_returns_rows(self):
        self._seq("q1")
        out = RPC_REGISTRY["query_sql"](
            self.db, {"sql_query": "SELECT id FROM sequence_state"})
        self.assertEqual([r["id"] for r in out], ["q1"])

    def test_query_sql_with_no_sql_raises(self):
        with self.assertRaises(CompatError):
            RPC_REGISTRY["query_sql"](self.db, {})

    def test_exec_sql_actually_executes(self):
        RPC_REGISTRY["exec_sql"](
            self.db, {"sql": "CREATE TABLE probe (id TEXT PRIMARY KEY)"})
        rows = self.db.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='probe'",
            [], allow_unscoped=True, reason="test read")
        self.assertEqual(len(rows), 1, "exec_sql did not run the DDL")

    def test_every_rpc_the_live_daemons_call_is_registered(self):
        """A missing name raises CompatError at runtime, inside a per-row
        try/except, on a daemon whose stderr PM2 discards."""
        for name in ("claim_sequence_state_row", "release_sequence_state_claim",
                     "query_sql", "exec_sql", "patch_tenant_record_data",
                     "reserve_send_slot", "claim_events", "ack_event"):
            with self.subTest(rpc=name):
                self.assertIn(name, RPC_REGISTRY)

    def test_an_unported_rpc_still_names_itself_in_the_error(self):
        with self.assertRaises(CompatError) as ctx:
            self.client.rpc("some_unported_function", {}).execute()
        self.assertIn("some_unported_function", str(ctx.exception))


class TestJsonPathGuard(_Base):
    """One malformed row must not blank the whole result set."""

    def _q(self, rid, payload):
        self.db.execute("INSERT INTO queue (id, tenant_id, payload) VALUES (?, 'sun', ?)",
                        [rid, payload], allow_unscoped=True, reason="test fixture")
        self.db.commit()

    def test_a_malformed_row_does_not_abort_the_query(self):
        self._q("good1", '{"state": "queued"}')
        self._q("bad", "this is not json at all")
        self._q("good2", '{"state": "queued"}')

        rows = (self.client.table("queue")
                .select("id")
                .eq("payload->>state", "queued")
                .execute()).data
        ids = sorted(r["id"] for r in rows)
        self.assertEqual(ids, ["good1", "good2"],
                         "a single non-JSON row suppressed the good rows -- the "
                         "email queue would silently stop draining")

    def test_the_malformed_row_itself_is_simply_not_matched(self):
        self._q("bad", "nonsense")
        rows = (self.client.table("queue").select("id")
                .eq("payload->>state", "queued").execute()).data
        self.assertEqual(rows, [])


class TestReturningNotRowcount(_Base):
    """claim/ack must not depend on cursor.rowcount."""

    def _ev(self, eid, status="pending"):
        self.db.execute(
            "INSERT INTO agent_events (id, status, target_agent, published_at) "
            "VALUES (?, ?, 'bravo', '2026-01-01')", [eid, status],
            allow_unscoped=True, reason="test fixture")
        self.db.commit()

    def test_claim_events_reports_what_it_actually_claimed(self):
        self._ev("e1")
        self._ev("e2")
        out = RPC_REGISTRY["claim_events"](
            self.db, {"p_agent": "bravo", "p_max": 5, "p_visibility_seconds": 30})
        self.assertEqual(len(out), 2, "claimed rows were not reported back; they "
                                      "would sit in 'processing' owned by nobody")

    def test_a_second_claim_gets_nothing(self):
        self._ev("e3")
        RPC_REGISTRY["claim_events"](self.db, {"p_agent": "bravo", "p_max": 5})
        second = RPC_REGISTRY["claim_events"](self.db, {"p_agent": "bravo", "p_max": 5})
        self.assertEqual(second, [], "the same event was claimed twice")

    def test_ack_reports_true_only_when_it_changed_a_row(self):
        self._ev("e4")
        self.assertTrue(RPC_REGISTRY["ack_event"](
            self.db, {"p_event_id": "e4", "p_agent": "bravo"}))
        self.assertFalse(RPC_REGISTRY["ack_event"](
            self.db, {"p_event_id": "e4", "p_agent": "bravo"}),
            "acking an already-done event reported success")

    def test_ack_of_a_nonexistent_event_is_false(self):
        self.assertFalse(RPC_REGISTRY["ack_event"](
            self.db, {"p_event_id": "ghost", "p_agent": "bravo"}))


if __name__ == "__main__":
    unittest.main()
