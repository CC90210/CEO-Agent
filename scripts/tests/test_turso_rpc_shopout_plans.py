"""The last three RPC ports: shop-out rounds, lender patches, daily plans.

These were found by a MULTILINE re-scan for `.rpc(` after a line-based
`git grep -o` reported 12 names and missed 5 — including the call behind every
health heartbeat in the fleet. Two of these three move money: a shop-out round
number that repeats, or a lender patch that lands on the wrong element, is a
lender receiving the wrong submission.

Runs against a real libSQL file database. The defects guarded against here are
SQL/JSON semantics, and a mock would agree with a wrong query.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db_turso import TursoDB  # noqa: E402
from lib.turso_supabase_compat import RPC_REGISTRY, CompatError  # noqa: E402

SCHEMA = """
CREATE TABLE shopping_threads (
    id TEXT PRIMARY KEY, tenant_id TEXT, lead_id TEXT,
    round_number INTEGER, lenders TEXT, updated_at TEXT);
CREATE TABLE user_profiles (id TEXT PRIMARY KEY, tenant_id TEXT);
CREATE TABLE plan_templates (
    id TEXT PRIMARY KEY, profile_id TEXT, kind TEXT, enabled INTEGER,
    mission TEXT, target_calls INTEGER, target_emails INTEGER,
    target_bookings INTEGER, schedule TEXT);
CREATE TABLE daily_plans (
    id TEXT PRIMARY KEY, tenant_id TEXT, profile_id TEXT, plan_date TEXT,
    mission TEXT, target_calls INTEGER, target_emails INTEGER,
    target_bookings INTEGER, schedule TEXT,
    UNIQUE (profile_id, plan_date));
"""

TENANT = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
OTHER = "00000000-0000-4000-8000-0000000000ff"
PROFILE = "e356f515-de9b-411f-bd7d-8de8013c7f6d"


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.db = TursoDB(str(Path(self._tmp.name) / "t.db"), None, "local(test)")
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                self.db.execute(stmt, [], allow_unscoped=True, reason="schema")
        self.db.commit()

    def tearDown(self):
        try:
            conn = getattr(self.db, "_conn", None)
            if conn is not None and hasattr(conn, "close"):
                conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._tmp.cleanup()

    def _round(self, rid, lead="lead-1", num=1, lenders=None, tenant=TENANT):
        self.db.execute(
            "INSERT INTO shopping_threads (id, tenant_id, lead_id, round_number, lenders) "
            "VALUES (?,?,?,?,?)",
            [rid, tenant, lead, num, json.dumps(lenders if lenders is not None else [])],
            allow_unscoped=True, reason="fixture")
        self.db.commit()


class TestNextRoundNumber(_Base):
    def test_first_round_is_one(self):
        n = RPC_REGISTRY["shop_out_next_round_number"](
            self.db, {"p_tenant_id": TENANT, "p_lead_id": "lead-1"})
        self.assertEqual(n, 1)

    def test_it_increments_past_the_highest_existing_round(self):
        self._round("r1", num=1)
        self._round("r2", num=2)
        n = RPC_REGISTRY["shop_out_next_round_number"](
            self.db, {"p_tenant_id": TENANT, "p_lead_id": "lead-1"})
        self.assertEqual(n, 3, "a repeated round number means a lender gets the "
                               "same submission twice")

    def test_it_is_scoped_to_the_lead(self):
        self._round("r1", lead="lead-1", num=7)
        n = RPC_REGISTRY["shop_out_next_round_number"](
            self.db, {"p_tenant_id": TENANT, "p_lead_id": "lead-2"})
        self.assertEqual(n, 1, "another lead's rounds leaked into this count")

    def test_it_is_scoped_to_the_tenant(self):
        self._round("r1", num=9, tenant=OTHER)
        n = RPC_REGISTRY["shop_out_next_round_number"](
            self.db, {"p_tenant_id": TENANT, "p_lead_id": "lead-1"})
        self.assertEqual(n, 1, "another TENANT's rounds leaked into this count")


class TestPatchLender(_Base):
    LENDERS = [
        {"lender_id": "L1", "status": "sent", "notes": "first"},
        {"lender_id": "L2", "status": "sent"},
    ]

    def test_it_patches_only_the_named_lender(self):
        self._round("r1", lenders=self.LENDERS)
        row = RPC_REGISTRY["shop_out_patch_lender"](self.db, {
            "p_round_id": "r1", "p_lender_id": "L2",
            "p_patch": {"status": "declined", "reason": "credit"}})
        self.assertIsNotNone(row)
        lenders = json.loads(row["lenders"]) if isinstance(row["lenders"], str) else row["lenders"]
        self.assertEqual(lenders[0]["status"], "sent", "the WRONG lender was patched")
        self.assertEqual(lenders[1]["status"], "declined")
        self.assertEqual(lenders[1]["reason"], "credit")

    def test_it_merges_rather_than_replacing_the_element(self):
        self._round("r1", lenders=self.LENDERS)
        RPC_REGISTRY["shop_out_patch_lender"](self.db, {
            "p_round_id": "r1", "p_lender_id": "L1", "p_patch": {"status": "approved"}})
        rows = self.db.query("SELECT lenders FROM shopping_threads WHERE id='r1'",
                             [], allow_unscoped=True, reason="read")
        lenders = json.loads(rows[0]["lenders"])
        self.assertEqual(lenders[0]["notes"], "first",
                         "the merge REPLACED the element and dropped other fields")

    def test_a_null_in_the_patch_is_KEPT_not_deleted(self):
        # jsonb `||` keeps nulls; json_patch would delete the key. Clearing a
        # field by patching it to null is a real operation.
        self._round("r1", lenders=self.LENDERS)
        RPC_REGISTRY["shop_out_patch_lender"](self.db, {
            "p_round_id": "r1", "p_lender_id": "L1", "p_patch": {"notes": None}})
        rows = self.db.query("SELECT lenders FROM shopping_threads WHERE id='r1'",
                             [], allow_unscoped=True, reason="read")
        lenders = json.loads(rows[0]["lenders"])
        self.assertIn("notes", lenders[0], "the null-valued key was DELETED")
        self.assertIsNone(lenders[0]["notes"])

    def test_an_unknown_lender_returns_None_and_writes_nothing(self):
        self._round("r1", lenders=self.LENDERS)
        out = RPC_REGISTRY["shop_out_patch_lender"](self.db, {
            "p_round_id": "r1", "p_lender_id": "NOPE", "p_patch": {"status": "x"}})
        self.assertIsNone(out)
        rows = self.db.query("SELECT lenders FROM shopping_threads WHERE id='r1'",
                             [], allow_unscoped=True, reason="read")
        self.assertEqual(json.loads(rows[0]["lenders"]), self.LENDERS)

    def test_an_unknown_round_returns_None(self):
        self.assertIsNone(RPC_REGISTRY["shop_out_patch_lender"](self.db, {
            "p_round_id": "ghost", "p_lender_id": "L1", "p_patch": {"a": 1}}))


class TestMaterializeTodayPlan(_Base):
    def _profile(self):
        self.db.execute("INSERT INTO user_profiles (id, tenant_id) VALUES (?,?)",
                        [PROFILE, TENANT], allow_unscoped=True, reason="fixture")
        self.db.commit()

    def _template(self, kind, mission):
        self.db.execute(
            "INSERT INTO plan_templates (id, profile_id, kind, enabled, mission, "
            "target_calls, target_emails, target_bookings, schedule) "
            "VALUES (?,?,?,1,?,5,10,2,'[]')",
            [f"tpl-{kind}", PROFILE, kind, mission], allow_unscoped=True,
            reason="fixture")
        self.db.commit()

    def test_it_creates_a_plan_and_returns_its_id(self):
        self._profile()
        self._template("weekday", "Weekday ops")
        pid = RPC_REGISTRY["materialize_today_plan"](
            self.db, {"p_profile_id": PROFILE, "p_target_date": "2026-08-12"})  # Wed
        self.assertTrue(pid)
        rows = self.db.query("SELECT mission FROM daily_plans WHERE id = ?", [pid],
                             allow_unscoped=True, reason="read")
        self.assertEqual(rows[0]["mission"], "Weekday ops")

    def test_a_second_call_the_same_day_returns_the_SAME_id(self):
        """ON CONFLICT DO NOTHING returns no row; the source then SELECTs it.
        Returning None here would make the daily cron look broken every run
        after the first."""
        self._profile()
        self._template("weekday", "Weekday ops")
        a = RPC_REGISTRY["materialize_today_plan"](
            self.db, {"p_profile_id": PROFILE, "p_target_date": "2026-08-12"})
        b = RPC_REGISTRY["materialize_today_plan"](
            self.db, {"p_profile_id": PROFILE, "p_target_date": "2026-08-12"})
        self.assertEqual(a, b, "the second call did not return the existing plan")
        n = self.db.query("SELECT COUNT(*) AS n FROM daily_plans", [],
                          allow_unscoped=True, reason="read")[0]["n"]
        self.assertEqual(int(n), 1, "a duplicate plan row was created")

    def test_saturday_and_sunday_pick_the_WEEKEND_template(self):
        # EXTRACT(DOW) is 0=Sun..6=Sat; Python weekday() is 0=Mon. Getting the
        # conversion wrong silently applies the weekday plan at the weekend.
        self._profile()
        self._template("weekday", "Weekday ops")
        self._template("weekend", "Weekend ops")
        for date, expected in (("2026-08-15", "Weekend ops"),   # Saturday
                               ("2026-08-16", "Weekend ops"),   # Sunday
                               ("2026-08-17", "Weekday ops")):  # Monday
            with self.subTest(date=date):
                pid = RPC_REGISTRY["materialize_today_plan"](
                    self.db, {"p_profile_id": PROFILE, "p_target_date": date})
                rows = self.db.query("SELECT mission FROM daily_plans WHERE id = ?",
                                     [pid], allow_unscoped=True, reason="read")
                self.assertEqual(rows[0]["mission"], expected)

    def test_no_template_still_produces_a_plan_with_defaults(self):
        self._profile()
        pid = RPC_REGISTRY["materialize_today_plan"](
            self.db, {"p_profile_id": PROFILE, "p_target_date": "2026-08-12"})
        rows = self.db.query(
            "SELECT mission, target_bookings FROM daily_plans WHERE id = ?", [pid],
            allow_unscoped=True, reason="read")
        self.assertEqual(rows[0]["mission"], "Daily ops")
        self.assertEqual(int(rows[0]["target_bookings"]), 1)

    def test_a_profile_with_no_tenant_RAISES(self):
        with self.assertRaises(CompatError):
            RPC_REGISTRY["materialize_today_plan"](
                self.db, {"p_profile_id": "ghost", "p_target_date": "2026-08-12"})


if __name__ == "__main__":
    unittest.main()
