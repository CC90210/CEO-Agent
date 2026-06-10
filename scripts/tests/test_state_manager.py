"""state_manager round-trip tests (V7) — the V6 single-writer proxy / DB source-of-truth
was ZERO-tested (audit 2026-06-10). Exercises heartbeat / session-log / task against an
isolated in-memory DB with the best-effort Supabase + event-bus mirrors neutralized, so the
SQLite write path (the authoritative one) is verified offline + deterministically.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "state"))
import state_manager as sm  # noqa: E402


class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        sm._apply_migrations(self.conn)
        # Neutralize the best-effort cloud mirrors (network) — the local DB is the SoT.
        self._orig = (sm._mirror_supabase_heartbeat, sm._emit_cross_agent_event)
        sm._mirror_supabase_heartbeat = lambda *a, **k: None
        sm._emit_cross_agent_event = lambda *a, **k: None

    def tearDown(self):
        sm._mirror_supabase_heartbeat, sm._emit_cross_agent_event = self._orig
        self.conn.close()

    def test_heartbeat_writes_and_increments_tick(self):
        sm.heartbeat("bravo", status="working", focus="t1", conn=self.conn)
        r = self.conn.execute(
            "SELECT status, current_focus, tick_count FROM agent_state WHERE agent='bravo'").fetchone()
        self.assertEqual((r["status"], r["current_focus"], r["tick_count"]), ("working", "t1", 1))
        sm.heartbeat("bravo", focus="t2", conn=self.conn)
        r2 = self.conn.execute(
            "SELECT current_focus, tick_count FROM agent_state WHERE agent='bravo'").fetchone()
        self.assertEqual((r2["current_focus"], r2["tick_count"]), ("t2", 2))

    def test_unknown_agent_rejected(self):
        with self.assertRaises(ValueError):
            sm.heartbeat("nobody-agent", conn=self.conn)

    def test_session_log_insert_then_dedup(self):
        self.assertEqual(sm.append_session_log("note-A", agent="bravo", session_id="S1", conn=self.conn), "inserted")
        self.assertEqual(sm.append_session_log("note-A", agent="bravo", session_id="S1", conn=self.conn), "deduped")
        n = self.conn.execute("SELECT COUNT(*) AS c FROM session_log WHERE session_id='S1'").fetchone()["c"]
        self.assertEqual(n, 1)

    def test_task_upsert_then_close(self):
        tid = sm.upsert_task("TODAY", "test task", owner="bravo", conn=self.conn)
        self.assertIsInstance(tid, int)
        self.assertEqual(self.conn.execute(
            "SELECT status FROM active_task WHERE id=?", (tid,)).fetchone()["status"], "open")
        sm.close_task(tid, status="done", conn=self.conn)
        self.assertEqual(self.conn.execute(
            "SELECT status FROM active_task WHERE id=?", (tid,)).fetchone()["status"], "done")


if __name__ == "__main__":
    unittest.main(verbosity=2)
