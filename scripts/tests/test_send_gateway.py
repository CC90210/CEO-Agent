"""
Tests for the V5.6 + reasoning-loop stack.

REPAIR STATUS (2026-05-21, V6.8.3 production hardening):
  - 69/69 tests pass.
  - Original 36 failures were ALL caused by two stale module paths after
    the scripts/ reorg: `import send_gateway` (now `integrations.send_gateway`)
    and `import context_builder` (now `core.context_builder`). Fix is in
    `_import_gateway_fresh` and `TestContextBuilder.setUp`. No production
    code was touched — the tests just hadn't been re-pointed after the
    May reorg.

Uses a lightweight fake Supabase client + fake smtplib so every test runs
offline with zero side effects. No real emails sent, no real DB hits.

Covers: send_gateway (12) + context_builder (5) + inbound_classifier (6) +
draft_critic (5) + autonomous_agent policy gates (8) + register_skill (3).

Run:
  python scripts/test_send_gateway.py
  python scripts/test_send_gateway.py --verbose

All tests must pass. The gateway is the only outbound chokepoint in the
codebase — regressions here fan out to every business engine.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT  # scripts/ — needed for `import integrations.send_gateway` on direct runs
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---- Fake Supabase client ---------------------------------------------------

class _FakeSelect:
    def __init__(self, table: "_FakeTable", cols: str = "*", count: str | None = None):
        self.table = table
        self.cols = cols
        self.count = count
        self.filters: list = []
        self.ordering: tuple | None = None
        self.limit_val: int | None = None

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self.filters.append(("lte", col, val))
        return self

    def contains(self, col, subobj):
        """Mirror Supabase Python client's jsonb `.contains()` — matches
        rows whose `col` (a dict) contains all key/value pairs in `subobj`.
        Used by resolve_lead_id to query tenant_records by data.email."""
        self.filters.append(("contains", col, subobj))
        return self

    def order(self, col, desc=False):
        self.ordering = (col, desc)
        return self

    def limit(self, n):
        self.limit_val = n
        return self

    def execute(self):
        rows = list(self.table.rows)
        for op, col, val in self.filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "gte":
                rows = [r for r in rows if (r.get(col) or "") >= val]
            elif op == "lte":
                rows = [r for r in rows if (r.get(col) or "") <= val]
            elif op == "contains":
                def _has(r):
                    blob = r.get(col)
                    if not isinstance(blob, dict):
                        return False
                    return all(blob.get(k) == v for k, v in (val or {}).items())
                rows = [r for r in rows if _has(r)]
        if self.ordering:
            col, desc = self.ordering
            rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=desc)
        if self.limit_val is not None:
            rows = rows[: self.limit_val]

        class R:
            pass
        r = R()
        r.data = rows
        r.count = len(rows) if self.count else None
        return r


class _FakeInsert:
    def __init__(self, table: "_FakeTable", payload):
        self.table = table
        self.payload = payload

    def execute(self):
        payload = self.payload if isinstance(self.payload, list) else [self.payload]
        inserted = []
        for p in payload:
            row = dict(p)
            row.setdefault("id", f"fake-{len(self.table.rows)+1}")
            self.table.rows.append(row)
            inserted.append(row)

        class R:
            pass
        r = R()
        r.data = inserted
        r.count = len(inserted)
        return r


class _FakeUpdate:
    def __init__(self, table, payload):
        self.table = table
        self.payload = payload
        self.filters: list = []

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def execute(self):
        updated = []
        for r in self.table.rows:
            match = all(r.get(c) == v for _, c, v in self.filters)
            if match:
                r.update(self.payload)
                updated.append(r)

        class R:
            pass
        res = R()
        res.data = updated
        res.count = len(updated)
        return res


class _FakeRPC:
    def __init__(self, db: "FakeSupabase", function_name: str, params: dict[str, Any]):
        self.db = db
        self.function_name = function_name
        self.params = params

    def execute(self):
        # The gateway's primary reservation path is the reserve_send_slot RPC
        # (migration 079). Simulate advisory-lock contention here so that test
        # exercises the real RPC path; non-contention callers still fall through
        # to the exec_sql fallback unchanged (minimal blast radius).
        if self.function_name == "reserve_send_slot" and self.db.force_lock_contention:
            class _R:
                pass
            res = _R()
            res.data = {"lock_acquired": False}
            return res
        if self.function_name != "exec_sql":
            raise RuntimeError(f"unsupported RPC: {self.function_name}")
        sql_query = self.params.get("sql_query", "")
        return self.db._handle_exec_sql(sql_query)


class _FakeTable:
    def __init__(self, name, rows=None):
        self.name = name
        self.rows = list(rows or [])

    def select(self, cols="*", count=None):
        return _FakeSelect(self, cols, count)

    def insert(self, payload):
        return _FakeInsert(self, payload)

    def update(self, payload):
        return _FakeUpdate(self, payload)


class FakeSupabase:
    """Stand-in for supabase.Client. Supports the subset of operations the
    gateway uses. Rows persist per-instance so tests can mutate state."""

    def __init__(self):
        self.tables: dict[str, _FakeTable] = {
            "leads": _FakeTable("leads"),
            "lead_interactions": _FakeTable("lead_interactions"),
            "email_log": _FakeTable("email_log"),
        }
        self.force_lock_contention = False
        self.disable_rpc = False

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = _FakeTable(name)
        return self.tables[name]

    def rpc(self, function_name, params):
        if self.disable_rpc:
            raise RuntimeError("RPC unavailable")
        return _FakeRPC(self, function_name, params)

    def _handle_exec_sql(self, sql_query: str):
        marker_match = re.search(r"/\*\s*send_gateway_reserve:(.*?)\s*\*/", sql_query, re.DOTALL)
        if not marker_match:
            raise RuntimeError("unsupported exec_sql payload")
        marker = json.loads(marker_match.group(1))
        existing = next(
            (
                row for row in self.tables["lead_interactions"].rows
                if row.get("lead_id") == marker.get("lead_id")
                and row.get("channel") == marker.get("channel")
                and row.get("type") == "reserving"
            ),
            None,
        )

        class R:
            pass

        res = R()
        if self.force_lock_contention:
            res.data = {"status": "ok", "rows": [{"lock_acquired": False}]}
            return res
        if existing:
            res.data = {
                "status": "ok",
                "rows": [{
                    "lock_acquired": True,
                    "existing_reservation_id": existing.get("id"),
                    "reservation_id": None,
                }],
            }
            return res

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": f"fake-{len(self.tables['lead_interactions'].rows) + 1}",
            "lead_id": marker.get("lead_id"),
            "channel": marker.get("channel"),
            "type": "reserving",
            "created_at": now,
            "subject": marker.get("subject"),
            "content": marker.get("content_preview"),
            "agent_source": marker.get("agent_source"),
            "cooldown_until": marker.get("cooldown_until"),
            "metadata": marker.get("metadata") or {},
        }
        self.tables["lead_interactions"].rows.append(row)
        res.data = {
            "status": "ok",
            "rows": [{
                "lock_acquired": True,
                "existing_reservation_id": None,
                "reservation_id": row["id"],
                "reservation_created_at": now,
            }],
        }
        return res


class _FailingSelect(_FakeSelect):
    def execute(self):
        raise RuntimeError("ledger unavailable")


class _FailingTable(_FakeTable):
    def select(self, cols="*", count=None):
        return _FailingSelect(self, cols, count)


class FailingLedgerSupabase(FakeSupabase):
    def __init__(self):
        super().__init__()
        self.tables["lead_interactions"] = _FailingTable("lead_interactions")


# ---- Shared fixtures --------------------------------------------------------

def _fresh_env(monkeypatch_env: dict):
    """Patch send_gateway env-loading + smtplib so tests don't hit network."""
    monkeypatch_env.update({
        "BRAVO_SUPABASE_URL": "https://test.supabase.co",
        "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "fake-service-key",
        "GMAIL_USER": "test@oasisai.work",
        "GMAIL_APP_PASSWORD": "fake-password",
    })
    return monkeypatch_env


def _import_gateway_fresh():
    """Force a fresh import of send_gateway so each test starts clean.

    send_gateway moved to scripts/integrations/ during the 2026-05 reorg.
    We purge BOTH the legacy `send_gateway` and the new
    `integrations.send_gateway` from sys.modules, then do a fresh
    `import_module` (NOT reload — reload misbehaves when the prior
    module reference has been detached by addCleanup).
    """
    import importlib
    mods = [m for m in list(sys.modules)
            if m == "send_gateway"
            or m.startswith("send_gateway.")
            or m == "integrations.send_gateway"
            or m.startswith("integrations.send_gateway.")]
    for m in mods:
        del sys.modules[m]
    return importlib.import_module("integrations.send_gateway")


# ---- Tests ------------------------------------------------------------------

class TestSendGateway(unittest.TestCase):

    def setUp(self):
        self._env_patcher = mock.patch.dict(os.environ, _fresh_env({}), clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        self.sg = _import_gateway_fresh()
        self.db = FakeSupabase()
        self.sg._DAILY_CAP_ALERTS_SENT.clear()
        self._critic_patcher = mock.patch.object(
            self.sg,
            "critique_draft",
            return_value={"verdict": "ship", "reasons": [], "notes": ""},
        )
        self._critic_patcher.start()
        self.addCleanup(self._critic_patcher.stop)
        # 2026-04-27: Gate 1b requires body_html for OASIS commercial sends.
        # Most legacy tests passed body_text only — wrap sg.send so any test
        # call missing body_html on a default oasis/commercial send gets a
        # placeholder injected. Tests that intentionally exercise the missing-
        # html path can pass body_html=None explicitly via the wrapper.
        _orig_send = self.sg.send
        def _send_with_default_html(**kwargs):
            no_html_override = kwargs.pop("_no_html_for_test", False)
            brand = kwargs.get("brand", "oasis")
            intent = kwargs.get("intent", "commercial")
            html = kwargs.get("body_html")
            if (kwargs.get("channel") == "email" and brand == "oasis"
                    and intent == "commercial" and not html
                    and not no_html_override):
                kwargs["body_html"] = "<p>" + (kwargs.get("body_text") or "") + "</p>"
            return _orig_send(**kwargs)
        self.sg.send = _send_with_default_html
        # Seed one lead so resolve_lead_id has something to find.
        # tenant_id is REQUIRED for the kill-switch gate (Codex audit
        # 2026-06-08 finding #1) — without it every commercial-intent test
        # case fail-closes at the gate. Production leads all carry tenant_id;
        # the test fixture should match that shape.
        self.db.tables["leads"].rows.append({
            "id": "lead-001",
            "name": "Jane Test",
            "email": "jane@acme.example",
            "status": "new",
            "tenant_id": "00000000-0000-0000-0000-000000000fix",
        })

    def _patch_smtp_ok(self):
        return mock.patch.object(self.sg, "_send_email_smtp",
                                 return_value=(True, None))

    def _patch_smtp_fail(self, err: str = "rejected"):
        return mock.patch.object(self.sg, "_send_email_smtp",
                                 return_value=(False, err))

    def _patch_suppress(self, value: bool):
        return mock.patch.object(self.sg, "should_suppress",
                                 return_value=value)

    def _patch_critic(self, verdict: str, reasons: list[str] | None = None):
        return mock.patch.object(
            self.sg,
            "critique_draft",
            return_value={"verdict": verdict, "reasons": reasons or [], "notes": ""},
        )

    # 1. Golden path: commercial email, fresh recipient
    def test_01_golden_path_sent(self):
        with self._patch_smtp_ok(), self._patch_suppress(False), mock.patch.object(self.sg, "_telegram_notify", return_value=False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hello",
                db=self.db,
            )
        self.assertEqual(r["status"], "sent", r)
        self.assertIsNotNone(r["interaction_id"])
        # Ledger row created
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 1)
        # Email log mirror created
        self.assertEqual(len(self.db.tables["email_log"].rows), 1)

    def test_01b_email_cc_header_and_envelope(self):
        captured = {}

        def fake_smtp(_env, mime, to_email, cc_emails=None):
            captured["to_email"] = to_email
            captured["cc_emails"] = cc_emails
            captured["cc_header"] = mime["Cc"]
            return True, None

        with mock.patch.object(self.sg, "_send_email_smtp", side_effect=fake_smtp), self._patch_suppress(False), mock.patch.object(self.sg, "_telegram_notify", return_value=False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                cc_email="ops@acme.example, owner@acme.example",
                subject="hi",
                body_text="hello",
                db=self.db,
            )

        self.assertEqual(r["status"], "sent", r)
        self.assertEqual(captured["to_email"], "jane@acme.example")
        self.assertEqual(captured["cc_emails"], ["ops@acme.example", "owner@acme.example"])
        self.assertEqual(captured["cc_header"], "ops@acme.example, owner@acme.example")

    # 2. CASL suppression blocks commercial send
    def test_02_suppressed_commercial_blocked(self):
        with self._patch_smtp_ok(), self._patch_suppress(True):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="blocked@example.invalid",
                subject="hi",
                body_text="hi",
                db=self.db,
            )
        self.assertEqual(r["status"], "suppressed")
        self.assertIn("suppression", r["reason"])
        # No send attempted, no ledger write
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    # 3. Transactional intent bypasses suppression
    def test_03_transactional_bypasses_suppression(self):
        with self._patch_smtp_ok(), self._patch_suppress(True):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="Booking confirmation",
                body_text="Your call is confirmed.",
                intent="transactional",
                db=self.db,
            )
        self.assertEqual(r["status"], "sent")

    # 4. Cooldown blocks a second commercial send within window
    def test_04_cooldown_blocks_retry(self):
        now = datetime.now(timezone.utc)
        self.db.tables["lead_interactions"].rows.append({
            "id": "ix-001",
            "lead_id": "lead-001",
            "channel": "email",
            "type": "email_sent",
            "created_at": now.isoformat(),
            "cooldown_until": (now + timedelta(hours=48)).isoformat(),
        })
        with self._patch_smtp_ok(), self._patch_suppress(False), mock.patch.object(self.sg, "_telegram_notify", return_value=False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="retry",
                body_text="retry",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("cooldown", r["reason"])

    # 5. Daily cap enforced
    def test_05_daily_cap_blocks(self):
        # Patch the gateway's now() to a fixed time well into the day so:
        #   1. seeded rows are inside today's day-start window (daily count fires)
        #   2. seeded rows are outside the last 1h window (hourly cap doesn't fire first)
        # Without this patch the test is flaky in the 0-1am UTC window where
        # no valid time slot satisfies both conditions.
        fixed_now = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        seeded_at = fixed_now - timedelta(hours=2)  # inside day, outside last 1h
        cap = self.sg.DAILY_CAPS["email"]
        for i in range(cap):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"cap-{i}",
                "lead_id": f"other-{i}",
                "channel": "email",
                "type": "email_sent",
                "created_at": seeded_at.isoformat(),
            })

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now if tz else fixed_now.replace(tzinfo=None)
        self._datetime_patcher = mock.patch.object(
            self.sg, "datetime", _FakeDatetime
        )
        self._datetime_patcher.start()
        self.addCleanup(self._datetime_patcher.stop)
        with self._patch_smtp_ok(), self._patch_suppress(False), mock.patch.object(self.sg, "_telegram_notify", return_value=False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="over cap",
                body_text="over",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("daily cap", r["reason"])

    def test_05b_cooldown_ledger_failure_blocks(self):
        r = self.sg.can_act(
            lead_id="lead-001",
            channel="email",
            db=FailingLedgerSupabase(),
        )
        self.assertFalse(r["allowed"])
        # FailingLedgerSupabase fails every ledger read, so the first ledger
        # check (reply-since-outbound) trips before the cooldown one — either
        # way the gateway must FAIL CLOSED. Assert the fail-closed block, not the
        # exact check that fired first.
        self.assertIn("ledger unavailable", r["reason"])

    def test_05c_daily_cap_ledger_failure_blocks_without_lead(self):
        r = self.sg.can_act(
            lead_id=None,
            channel="email",
            db=FailingLedgerSupabase(),
        )
        self.assertFalse(r["allowed"])
        self.assertIn("hourly cap ledger unavailable", r["reason"])

    # 6. Dry-run produces no side effects
    def test_06_dry_run_no_side_effects(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="dry",
                body_text="dry",
                dry_run=True,
                db=self.db,
            )
        self.assertEqual(r["status"], "dry_run")
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)
        self.assertEqual(len(self.db.tables["email_log"].rows), 0)

    # 6b. Gate 1b: OASIS commercial sends require body_html
    def test_06b_oasis_commercial_requires_html(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="plain text only",
                body_html=None,
                _no_html_for_test=True,
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("body_html", r["reason"])
        # Nothing logged because gate fired before SMTP
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    # 6c. Transactional intent is exempt — booking confirmations may be plain text
    def test_06c_transactional_text_only_passes_gate(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="Your call is confirmed",
                body_text="See you Thursday.",
                body_html=None,
                intent="transactional",
                _no_html_for_test=True,
                db=self.db,
            )
        self.assertEqual(r["status"], "sent", r)

    # 6d. Non-OASIS brand is exempt — conaugh_mckenna / nostalgic may be plain text
    def test_06d_non_oasis_text_only_passes_gate(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="from kona",
                body_html=None,
                brand="conaugh_mckenna",
                _no_html_for_test=True,
                db=self.db,
            )
        self.assertEqual(r["status"], "sent", r)

    # 6e. Gate 1a: reserved/placeholder domain blocked at the gateway
    def test_06e_reserved_domain_blocked(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="info@example.com",
                subject="hi",
                body_text="hello",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("reserved", r["reason"].lower())
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    def test_06f_test_domain_blocked(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="contact@test.com",
                subject="hi",
                body_text="hello",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")

    # 7. Missing required email fields rejected
    def test_07_missing_email_fields_error(self):
        r = self.sg.send(
            channel="email",
            agent_source="test_harness",
            to_email="jane@acme.example",
            # subject + body_text missing
            db=self.db,
        )
        self.assertEqual(r["status"], "error")

    # 8. Unknown channel rejected
    def test_08_unknown_channel_error(self):
        r = self.sg.send(
            channel="fax",  # not in KNOWN_CHANNELS
            agent_source="test_harness",
            to_email="jane@acme.example",
            subject="hi",
            body_text="hi",
            db=self.db,
        )
        self.assertEqual(r["status"], "error")
        self.assertIn("unknown channel", r["reason"])

    # 9. Invalid intent rejected
    def test_09_invalid_intent_error(self):
        r = self.sg.send(
            channel="email",
            agent_source="test_harness",
            to_email="jane@acme.example",
            subject="hi",
            body_text="hi",
            intent="marketing",  # invalid
            db=self.db,
        )
        self.assertEqual(r["status"], "error")

    # 10. SMTP failure surfaces as error status
    def test_10_smtp_fail_surfaces(self):
        with self._patch_smtp_fail("SMTP rejected"), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                db=self.db,
            )
        self.assertEqual(r["status"], "error")
        self.assertIn("SMTP", r["reason"])
        # email_log should record the failure for forensics
        failed = [r for r in self.db.tables["email_log"].rows if r.get("status") == "failed"]
        self.assertEqual(len(failed), 1)

    # 11. Brand identity selects the right CASL sender block
    def test_11_brand_identity(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            # Conaugh McKenna brand should flow a different sender name
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="personal brand",
                body_text="hi",
                brand="conaugh_mckenna",
                db=self.db,
            )
        self.assertEqual(r["status"], "sent")
        # Verify metadata carried the brand
        ix = self.db.tables["lead_interactions"].rows[-1]
        meta = ix.get("metadata") or {}
        self.assertEqual(meta.get("brand"), "conaugh_mckenna")

    # 12. Lead auto-creation when email is new
    def test_12_auto_create_lead(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="brand-new@acme.example",
                subject="new",
                body_text="new",
                db=self.db,
            )
        self.assertEqual(r["status"], "sent")
        # Two leads now: the seeded one + the auto-created one
        self.assertEqual(len(self.db.tables["leads"].rows), 2)
        auto = [l for l in self.db.tables["leads"].rows
                if l.get("email") == "brand-new@acme.example"]
        self.assertEqual(len(auto), 1)
        self.assertEqual(auto[0].get("source"), "gateway_autocreate")

    def test_13_bounce_rate_over_threshold_blocks(self):
        now = datetime.now(timezone.utc).isoformat()
        self.db.tables["email_log"].rows.extend(
            [{"status": "sent", "sent_at": now} for _ in range(19)]
            + [{"status": "failed", "sent_at": now}]
        )
        self.db.tables["email_log"].rows.append({"status": "failed", "sent_at": now})
        r = self.sg.can_act(
            lead_id="lead-001",
            channel="email",
            to_email="jane@acme.example",
            db=self.db,
        )
        self.assertFalse(r["allowed"])
        self.assertIn("bounce-rate circuit breaker", r["reason"])

    def test_14_hourly_cap_blocks(self):
        now = datetime.now(timezone.utc).isoformat()
        cap = self.sg.HOURLY_CAPS["email"]
        for i in range(cap):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"h-{i}",
                "lead_id": f"other-{i}",
                "channel": "email",
                "type": "email_sent",
                "created_at": now,
            })
        r = self.sg.can_act(
            lead_id="lead-001",
            channel="email",
            to_email="jane@acme.example",
            db=self.db,
        )
        self.assertFalse(r["allowed"])
        self.assertIn("hourly cap", r["reason"])

    def test_15_domain_cap_blocks(self):
        now = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.db.tables["leads"].rows.extend([
            {"id": "lead-002", "email": "ops@acme.example"},
            {"id": "lead-003", "email": "sales@acme.example"},
            {"id": "lead-004", "email": "team@acme.example"},
        ])
        for idx, lead_id in enumerate(["lead-002", "lead-003", "lead-004"], start=1):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"d-{idx}",
                "lead_id": lead_id,
                "channel": "email",
                "type": "email_sent",
                "created_at": now,
            })
        r = self.sg.can_act(
            lead_id="lead-001",
            channel="email",
            to_email="jane@acme.example",
            db=self.db,
        )
        self.assertFalse(r["allowed"])
        self.assertIn("domain cap", r["reason"])

    def test_16_draft_critic_rejection_blocks_send(self):
        with self._patch_smtp_ok(), self._patch_suppress(False), self._patch_critic("reject", ["spammy opening"]):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("draft_critic rejected", r["reason"])
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    def test_16b_draft_critic_non_ship_verdict_blocks_send(self):
        with self._patch_smtp_ok(), self._patch_suppress(False), self._patch_critic("escalate", ["manual review"]):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("draft_critic rejected", r["reason"])
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    def test_16c_draft_critic_exception_blocks_send(self):
        with (
            self._patch_smtp_ok(),
            self._patch_suppress(False),
            mock.patch.object(self.sg, "critique_draft", side_effect=RuntimeError("critic down")),
        ):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("draft_critic unavailable", r["reason"])
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    def test_16d_unresolved_template_placeholders_block_before_critic(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="{{company}} lead follow-up",
                body_text="Hi Jane,\n\nI was just on {{company}}'s site.",
                body_html="<p>I was just on {{company}}'s site.</p>",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("unresolved template placeholder", r["reason"])
        self.assertIn("company", r["reason"])
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)
        self.sg.critique_draft.assert_not_called()

    def test_16e_fail_open_env_does_not_bypass_real_critic_rejection(self):
        original_load_env = self.sg.load_env

        def fail_open_env():
            base = original_load_env() or {}
            base["DRAFT_CRITIC_FAIL_OPEN"] = "true"
            return base

        with (
            mock.patch.object(self.sg, "load_env", side_effect=fail_open_env),
            self._patch_smtp_ok(),
            self._patch_suppress(False),
            self._patch_critic("reject", ["spammy opening"]),
        ):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("draft_critic rejected", r["reason"])
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), 0)

    def test_17_advisory_lock_contention_blocks(self):
        self.db.force_lock_contention = True
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hello",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked")
        self.assertIn("concurrent send detected", r["reason"])

    def test_18_get_daily_stats_includes_bounce_rate_and_hourly_counts(self):
        now = datetime.now(timezone.utc).isoformat()
        self.db.tables["lead_interactions"].rows.append({
            "id": "stats-1",
            "lead_id": "lead-001",
            "channel": "email",
            "type": "email_sent",
            "created_at": now,
        })
        self.db.tables["email_log"].rows.extend([
            {"status": "sent", "sent_at": now},
            {"status": "failed", "sent_at": now},
        ] + [{"status": "sent", "sent_at": now} for _ in range(18)])
        stats = self.sg.get_daily_stats(self.db)
        self.assertIn("bounce_rate", stats)
        self.assertIn("hourly_counts", stats)
        self.assertIn("email", stats["hourly_counts"])

    def test_18b_force_dry_run_killswitch_short_circuits_all_gates(self):
        """BRAVO_FORCE_DRY_RUN=1 must return status=dry_run BEFORE any gate
        runs — even if the suppression list, cooldown ledger, daily cap,
        and Supabase itself are unreachable. This is the multi-AI safety
        contract: any environment where the killswitch is set cannot leak
        a real send no matter which AI invokes which script.
        """
        # Pre-populate the cap so without the killswitch this would block.
        # If the killswitch fires correctly, this data is never read.
        cap = self.sg.DAILY_CAPS["email"]
        now_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        for i in range(cap):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"killsw-{i}", "lead_id": f"x-{i}", "channel": "email",
                "type": "email_sent", "created_at": now_iso,
            })

        # Patch load_env() to inject the killswitch flag — mirrors a real
        # operator setting BRAVO_FORCE_DRY_RUN=1 in their shell.
        original_load_env = self.sg.load_env
        def killswitch_env():
            base = original_load_env() or {}
            base["BRAVO_FORCE_DRY_RUN"] = "1"
            return base

        with mock.patch.object(self.sg, "load_env", side_effect=killswitch_env):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="should never send",
                body_text="should never send",
                # Intentionally pass dry_run=False — the killswitch must
                # override the caller.
                db=self.db,
            )

        self.assertEqual(r["status"], "dry_run",
                         f"killswitch failed; got {r}")
        self.assertIn("BRAVO_FORCE_DRY_RUN", r["reason"])
        # No interaction should be logged because no gate ran.
        self.assertEqual(len(self.db.tables["lead_interactions"].rows), cap,
                         "killswitch must not write to the ledger")

    def test_19_daily_cap_threshold_triggers_telegram_alert(self):
        # Same fix as test_05 — patch gateway's now() to a fixed mid-day
        # time so seeded rows fall inside today's day window but outside
        # the last 1h hourly window.
        fixed_now = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        seeded_at = (fixed_now - timedelta(hours=2)).isoformat()
        threshold = int(self.sg.DAILY_CAPS["email"] * 0.8)
        for i in range(threshold):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"a-{i}",
                "lead_id": f"lead-{i}",
                "channel": "email",
                "type": "email_sent",
                "created_at": seeded_at,
            })

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now if tz else fixed_now.replace(tzinfo=None)
        patcher = mock.patch.object(self.sg, "datetime", _FakeDatetime)
        patcher.start()
        self.addCleanup(patcher.stop)
        with mock.patch.object(self.sg, "_telegram_notify", return_value=True) as notify_mock:
            self.sg.can_act(
                lead_id="lead-001",
                channel="email",
                to_email="jane@acme.example",
                db=self.db,
            )
        self.assertTrue(notify_mock.called)

    def test_19b_daily_cap_threshold_alert_is_deduped_across_processes(self):
        fixed_now = datetime.now(timezone.utc).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        seeded_at = (fixed_now - timedelta(hours=2)).isoformat()
        threshold = int(self.sg.DAILY_CAPS["email"] * 0.8)
        for i in range(threshold):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"dedupe-{i}", "lead_id": f"lead-{i}",
                "channel": "email", "type": "email_sent", "created_at": seeded_at,
            })

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now if tz else fixed_now.replace(tzinfo=None)

        with mock.patch.object(self.sg, "datetime", _FakeDatetime), \
                mock.patch.object(self.sg, "_telegram_notify", return_value=True) as notify_mock:
            self.sg.can_act(lead_id="lead-001", channel="email", db=self.db)
            # Simulate a fresh gateway process: memory is empty, DB marker remains.
            self.sg._DAILY_CAP_ALERTS_SENT.clear()
            self.sg.can_act(lead_id="lead-002", channel="email", db=self.db)

        self.assertEqual(notify_mock.call_count, 1)
        message = notify_mock.call_args.args[0]
        self.assertIn("remaining", message)
        self.assertIn("one-time 80% warning", message)

    # ---- Kill-switch gate regression tests --------------------------------
    # These three tests anchor the behavior of the lead_id -> tenant_id
    # resolution gate that lives in send() right before can_act(). The gate
    # was added per Codex audit 2026-06-08 finding #1 (fail-closed on
    # unresolvable tenant so per-tenant kill-switches can't be silently
    # bypassed). Two distinct bugs since then:
    #   - First production hit: _resolve_tenant_for_lead originally only
    #     looked at the legacy `leads` table, so every SunBiz drip blocked.
    #     Fixed by adding tenant_records lookup.
    #   - Second production hit: the tenant_records lookup filtered by
    #     entity_type='lead', so shop-out (which fans out per-lender and
    #     passes application_id as the lead_id when app_data.lead_id is
    #     missing) ALSO blocked. Fixed by dropping the entity_type filter
    #     AND by accepting an explicit caller-supplied tenant_id kwarg
    #     that short-circuits the lookup entirely (CEO-Agent 1a0283a).
    # These tests pin all three cases so a future "tighten the gate" pass
    # can't re-break them silently.

    def test_20_kill_switch_blocks_when_neither_caller_nor_lookup_yields(self):
        """Safety property — must STILL fail-closed when nothing resolves."""
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="never-existed-anywhere",
                brand="conaugh_mckenna",
                intent="commercial",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked", r)
        self.assertIn("kill-switch enforcement unavailable", r["reason"])

    def test_21_kill_switch_passes_when_caller_supplies_tenant_id(self):
        """shop_out_sender / sequence_runner pattern: caller knows the tenant
        from the row it's processing and supplies it. The gate must trust
        that and skip the DB lookup. Without this, every shop-out blocked
        on 2026-06-08.

        Assertion is scoped to "this specific gate doesn't fire" — a later
        gate (send window, cap, etc.) may still block depending on test
        clock + fixtures, but it MUST NOT be the kill-switch gate."""
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="some-application-uuid-not-a-lead-row",
                tenant_id="aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110",
                brand="conaugh_mckenna",
                intent="commercial",
                db=self.db,
            )
        self.assertNotIn(
            "kill-switch enforcement unavailable",
            r.get("reason") or "",
            f"caller-supplied tenant_id should have skipped the lookup gate: {r}",
        )

    def test_22l_send_blocks_when_resolve_lead_id_refuses(self):
        """Codex audit 2026-06-09 round-8 [critical]: resolve_lead_id
        returning None from a refusal (cross-tenant ambiguity / tenant_records
        owns email) is NOT enough. send() previously let that None fall
        through — caller_supplied_tenant_scope was false AND lead_id was
        None, so enforce_tenant_gates collapsed to false and the send
        proceeded UNSCOPED. The fix: when send() did an email-based
        resolution attempt and got None back, block the send hard."""
        # tenant_records owns merchant@example.com under SunBiz
        self.db.table("tenant_records").rows.append({
            "id": "sunbiz-tr-lead-22l",
            "entity_type": "lead",
            "tenant_id": "SUNBIZ-TENANT",
            "data": {"email": "merchant22l@example.com"},
        })
        # Unscoped caller: no lead_id, no tenant_id, but to_email present.
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="merchant22l@example.com",
                subject="hi",
                body_text="hi",
                brand="conaugh_mckenna",
                intent="commercial",
                db=self.db,
            )
        # MUST be blocked at send() level, not silently proceed unscoped.
        self.assertEqual(r["status"], "blocked", r)
        self.assertIn("lead resolution refused", r["reason"])

    def test_22m_resolve_lead_id_scoped_reuses_tenant_records_id(self):
        """Codex audit 2026-06-09 round-8 [high]: the scoped path
        previously checked only legacy `leads` and would auto-create a
        DUPLICATE row when tenant_records already had the lead.
        Round-8: the scoped path checks tenant_records FIRST and reuses
        the existing id."""
        self.db.table("tenant_records").rows.append({
            "id": "sunbiz-tr-lead-22m",
            "entity_type": "lead",
            "tenant_id": "SUNBIZ-TENANT",
            "data": {"email": "merchant22m@example.com"},
        })
        from integrations.send_gateway import resolve_lead_id
        # Scoped caller asks for the same email under the same tenant.
        resolved = resolve_lead_id(
            self.db,
            "merchant22m@example.com",
            None,
            tenant_id="SUNBIZ-TENANT",
        )
        self.assertEqual(
            resolved,
            "sunbiz-tr-lead-22m",
            "scoped resolve_lead_id MUST reuse the existing tenant_records id, not auto-create a duplicate in legacy leads",
        )

    def test_22n_tenant_records_lookup_failure_blocks_unscoped(self):
        """Codex audit 2026-06-09 round-8 [high]: previously the
        tenant_records cross-check used a try/except that set tr_rows=[]
        on failure, falling through to legacy leads auto-create. In a
        multi-tenant context that's the exact bypass we're closing.
        Round-8: lookup failure returns None so send() blocks."""
        # Inject a failure mode by monkeypatching the contains() filter
        # via a subclass that raises.
        from integrations.send_gateway import resolve_lead_id
        original_table = self.db.table

        def patched_table(name):
            t = original_table(name)
            if name == "tenant_records":
                original_select = t.select

                def boom_select(*a, **kw):
                    s = original_select(*a, **kw)
                    orig_contains = s.contains

                    def boom(*ca, **ckw):
                        raise RuntimeError("simulated jsonb-contains unavailable")
                    s.contains = boom
                    return s
                t.select = boom_select
            return t

        self.db.table = patched_table  # type: ignore[method-assign]
        try:
            # Unscoped, an email that does NOT exist anywhere.
            resolved = resolve_lead_id(self.db, "fresh22n@example.com", None)
        finally:
            self.db.table = original_table  # type: ignore[method-assign]
        self.assertIsNone(
            resolved,
            "tenant_records cross-check failure MUST fail closed (return None) "
            "to prevent bypass via degraded jsonb-contains support",
        )

    def test_22k_resolve_lead_id_blocks_when_tenant_records_owns_email(self):
        """Codex audit 2026-06-09 round-7 [high] follow-up: round-7's
        ambiguity guard checked only the legacy `leads` table. SunBiz and
        modern multi-tenant clients write leads to `tenant_records`
        (entity_type='lead') with the email in `data.email`. A caller
        that FORGOT to pass tenant_id (daemon misconfiguration) could
        auto-create a tenantless legacy leads row for an email that
        tenant_records already owns — bypassing the kill-switch on every
        send keyed by that auto-created lead_id.

        After the cross-check: when tenant_records has ANY entity_type='lead'
        row matching the email, an unscoped caller is refused (returns
        None). The caller must supply tenant_id explicitly to proceed."""
        # Seed a SunBiz lead in tenant_records — no legacy leads row.
        self.db.table("tenant_records").rows.append({
            "id": "sunbiz-tr-lead",
            "entity_type": "lead",
            "tenant_id": "SUNBIZ-TENANT",
            "data": {"email": "merchant@example.com"},
        })
        from integrations.send_gateway import resolve_lead_id
        # Unscoped caller (no tenant_id, no lead_id) — must refuse.
        resolved = resolve_lead_id(self.db, "merchant@example.com", None)
        self.assertIsNone(
            resolved,
            "unscoped lookup MUST refuse when tenant_records owns the email "
            "(prevents auto-create that bypasses tenant kill-switch)",
        )
        # Sanity: a SCOPED caller (passes the correct tenant_id) still works.
        # The scoped path doesn't even reach the tenant_records cross-check.
        resolved_scoped = resolve_lead_id(self.db, "merchant@example.com", None, tenant_id="SUNBIZ-TENANT")
        self.assertIsNotNone(resolved_scoped, "scoped resolve must still auto-create when scoped")

    def test_22j_resolve_lead_id_blocks_tenantless_plus_tenant_collision(self):
        """Codex audit 2026-06-09 round-7 [high]: the round-6 ambiguity
        guard counted only NON-NULL tenant_ids. If the email matched a
        legacy tenantless row PLUS a tenant-bound row, the guard saw
        distinct_tenants={TENANT-A} (size 1) and committed to rows[0] —
        which could be the tenantless row. post_resolve_tenant would
        then return None and the kill-switch gate would skip enforcement.

        After round-7: tenantless + tenant-bound mix is ambiguous, refuse
        to commit, return None. The kill-switch gate's safety property
        (fail-closed when neither caller-supplied nor lookup yields a
        tenant) is what then catches the send."""
        # Seed a tenantless legacy row + a tenant-bound row for the same email.
        self.db.table("leads").rows.append({
            "id": "legacy-tenantless-lead",
            "email": "collision@example.com",
            "tenant_id": None,
        })
        self.db.table("leads").rows.append({
            "id": "tenant-bound-lead",
            "email": "collision@example.com",
            "tenant_id": "TENANT-A",
        })
        from integrations.send_gateway import resolve_lead_id
        resolved = resolve_lead_id(self.db, "collision@example.com", None)
        self.assertIsNone(resolved, "tenantless + tenant-bound collision must refuse to commit")

    def test_22h_resolve_lead_id_tenant_scoped_when_supplied(self):
        """Codex audit 2026-06-09 round-6 [high]: resolve_lead_id's unscoped
        email lookup is a multi-tenant correctness bug. With tenant A and
        tenant B both having a lead for 'shared@example.com', the original
        impl returned whichever DB ordered first — potentially applying
        the WRONG tenant's kill switch.

        Round-6 fix: when caller supplies tenant_id, the lookup is
        constrained to that tenant. Auto-create also stamps tenant_id."""
        self.db.table("leads").rows.append({
            "id": "tenant-a-lead",
            "email": "shared@example.com",
            "tenant_id": "TENANT-A",
        })
        self.db.table("leads").rows.append({
            "id": "tenant-b-lead",
            "email": "shared@example.com",
            "tenant_id": "TENANT-B",
        })
        # Caller specifies tenant A — must get tenant-a-lead, not tenant-b-lead.
        from integrations.send_gateway import resolve_lead_id
        resolved = resolve_lead_id(self.db, "shared@example.com", None, tenant_id="TENANT-A")
        self.assertEqual(resolved, "tenant-a-lead", "tenant-scoped lookup must return matching tenant's row")
        # Caller specifies tenant B — must get tenant-b-lead.
        resolved_b = resolve_lead_id(self.db, "shared@example.com", None, tenant_id="TENANT-B")
        self.assertEqual(resolved_b, "tenant-b-lead")

    def test_22i_resolve_lead_id_refuses_ambiguous_cross_tenant_without_scope(self):
        """When the caller passes NO tenant_id and the same email exists
        under multiple tenants, the legacy unscoped lookup would silently
        return a random row. Round-6 fails closed (returns None) so the
        downstream kill-switch gate's safety property triggers."""
        self.db.table("leads").rows.append({
            "id": "tenant-x-lead",
            "email": "ambiguous@example.com",
            "tenant_id": "TENANT-X",
        })
        self.db.table("leads").rows.append({
            "id": "tenant-y-lead",
            "email": "ambiguous@example.com",
            "tenant_id": "TENANT-Y",
        })
        from integrations.send_gateway import resolve_lead_id
        resolved = resolve_lead_id(self.db, "ambiguous@example.com", None)
        self.assertIsNone(resolved, "ambiguous cross-tenant lookup must refuse to commit to a single row")

    def test_22g_email_resolution_enforces_kill_switch_for_existing_tenant_lead(self):
        """Codex audit 2026-06-09 round-5 [high]: round-4's
        caller_supplied_tenant_scope snapshot blocked the auto-create
        false positive, but introduced a real bypass — a caller passing
        only to_email (no lead_id, no tenant_id) for an EXISTING
        paused-tenant lead would skip kill-switch entirely while
        downstream still stamped the resolved tenant on the interaction
        ledger.

        After round-5: even when the caller supplies no scope, if
        resolve_lead_id returns a lead that LIVES IN A TENANT, the
        kill-switch + mismatch gates fire. Only genuinely unscoped sends
        (caller passed nothing AND the resolved lead has no tenant)
        are exempt.

        This test: seed a leads row for jane@acme.example with
        tenant_id="TENANT-G". Caller passes only to_email. With a
        mismatched tenant_id NO — wait, the caller passes no tenant_id.
        So the assertion is: lookup_tenant resolves; without a caller
        tenant_id there's no mismatch; the send proceeds past tenant
        gates with resolved_tenant set to TENANT-G. We assert the
        rejection reason (if any) is NOT 'kill-switch enforcement
        unavailable' — meaning the gate was actually evaluated."""
        # The setUp lead already has tenant_id (added in the round-1
        # fixture fix). jane@acme.example -> lead-001 -> tenant fix uuid.
        # Confirm the email-resolution path enforces.
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                # Caller supplies NO lead_id, NO tenant_id.
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                brand="conaugh_mckenna",
                intent="commercial",
                db=self.db,
            )
        # The seed lead has a tenant_id. The gate runs. The gate doesn't
        # complain about 'kill-switch enforcement unavailable' because
        # the post-resolve lookup found the tenant.
        reason = (r.get("reason") or "").lower()
        self.assertNotIn("kill-switch enforcement unavailable", reason, r)

    def test_23_e164_normalization_helper(self):
        """VPS health audit 2026-06-09 — every SunBiz SMS was failing on
        the strict E.164 check because lead.data.phone stores bare 10-digit
        numbers. New to_e164() helper in casl_compliance.py normalizes
        before the SMS dispatch. Pin all 5 accept patterns + rejects."""
        from casl_compliance import to_e164
        # Accept patterns
        self.assertEqual(to_e164("7634218229"), "+17634218229")
        self.assertEqual(to_e164("17634218229"), "+17634218229")
        self.assertEqual(to_e164("(763) 421-8229"), "+17634218229")
        self.assertEqual(to_e164("1-763-421-8229"), "+17634218229")
        self.assertEqual(to_e164("+17634218229"), "+17634218229")
        # Strip whitespace + dashes inside an already-E.164 string.
        self.assertEqual(to_e164(" +1 763 421 8229 "), "+17634218229")
        # Reject patterns (returns None — caller fails closed)
        self.assertIsNone(to_e164(""))
        self.assertIsNone(to_e164(None))
        self.assertIsNone(to_e164("12345"))  # too short
        self.assertIsNone(to_e164("1234567890123"))  # too long for US/CA bare
        self.assertIsNone(to_e164("abc"))  # no digits
        self.assertIsNone(to_e164("+"))  # plus with no digits

    def test_23e_e164_helper_rejects_unicode_digit_imposters(self):
        """Codex audit 2026-06-09 round-6 [medium]: round-5's to_e164 used
        str.isdigit() which returns True for Unicode decimal digits
        (Arabic-Indic, fullwidth, Devanagari, etc.). The resulting "+" +
        digits string would contain non-ASCII bytes that SMS providers
        reject silently. Round-6 restricts digit handling to ASCII 0-9.

        Pins:
          - Arabic-Indic digits in plus-prefixed input rejected
          - Fullwidth digits in bare input rejected
          - Mixed ASCII + Unicode digits rejected
          - Pure ASCII NANP still accepts (regression check)"""
        from casl_compliance import to_e164
        # Arabic-Indic digits inside a plus-prefixed string.
        # Without ASCII restriction: would become "+1234567890" (wrong bytes).
        # With ASCII restriction: digits are 0, regex fails, returns None.
        self.assertIsNone(to_e164("+١٢٣٤٥٦٧٨٩٠"))
        # Fullwidth digits bare.
        self.assertIsNone(to_e164("７６３４２１８２２９"))
        # Mixed ASCII + Arabic-Indic — the non-ASCII digits get dropped,
        # leaving fewer ASCII digits than required, so rejected.
        self.assertIsNone(to_e164("763٤٢٦1229"))
        # Sanity: pure ASCII still works.
        self.assertEqual(to_e164("7634218229"), "+17634218229")
        self.assertEqual(to_e164("+17634218229"), "+17634218229")

    def test_23d_e164_helper_strict_validation(self):
        """Codex audit 2026-06-09 round-5 [medium]: round-4's to_e164
        was too permissive — '+1' / '+12345' passed through because the
        plus-prefix branch only stripped non-digits without validating
        E.164 shape. Round-5 adds strict ITU E.164 regex
        ^\\+[1-9]\\d{7,14}$ for already-prefixed input.

        Pins:
          - '+1' rejected (too short — plus prefix needs 8-15 digits)
          - '+12345' rejected (still too short)
          - '+0123456789' rejected (country code can't start with 0)
          - '+447946112233' accepted (valid UK E.164)
          - '+12345678901234567' rejected (too long)"""
        from casl_compliance import to_e164
        # Too short plus-prefixed — round-4 wrongly accepted these.
        self.assertIsNone(to_e164("+1"))
        self.assertIsNone(to_e164("+12345"))
        self.assertIsNone(to_e164("+1234567"))  # 7 digits, below 8 min
        # Country code starting with 0 — invalid per E.164.
        self.assertIsNone(to_e164("+0123456789"))
        # Too long.
        self.assertIsNone(to_e164("+1234567890123456"))
        # Valid international (non-NANP) E.164 — must still pass.
        self.assertEqual(to_e164("+447946112233"), "+447946112233")
        self.assertEqual(to_e164("+33612345678"), "+33612345678")
        # Already-correct NANP stays correct.
        self.assertEqual(to_e164("+17634218229"), "+17634218229")

    def test_23b_sms_send_passes_e164_gate_with_bare_10_digit_phone(self):
        """The production breakage VPS health audit caught: a sequence
        step calling send(channel='sms', to_phone='7634218229', ...)
        used to be rejected with 'sms to_phone must be E.164'. After
        the patch, the bare 10-digit number is normalized to
        '+17634218229' BEFORE the strict check, so the send proceeds
        past this gate (downstream gates like SMS TCPA timezone check
        may still apply — that's not what this test is about).

        Scoped assertion: the rejection reason MUST NOT be about E.164
        format anymore. Any other reason (timezone, suppression, etc.)
        means the patch did its job."""
        with mock.patch.object(self.sg, "should_suppress_phone", return_value=False):
            r = self.sg.send(
                channel="sms",
                agent_source="test_harness",
                to_phone="7634218229",  # bare 10-digit — the VPS-found pattern
                body_text="Hi from SunBiz.",
                brand="conaugh_mckenna",
                intent="commercial",
                tenant_id="00000000-0000-0000-0000-000000000fix",
                db=self.db,
            )
        reason = (r.get("reason") or "").lower()
        self.assertNotIn("must be e.164", reason, r)
        self.assertNotIn("could not be normalized to e.164", reason, r)

    def test_23c_sms_send_rejects_unnormalizable_phone(self):
        """A garbage phone (too short / too long / no digits) must still
        fail closed — the patch is liberal in accept but conservative
        in reject. Better to drop one SMS than send to a bad number."""
        with mock.patch.object(self.sg, "should_suppress_phone", return_value=False):
            r = self.sg.send(
                channel="sms",
                agent_source="test_harness",
                to_phone="12345",  # too short, can't normalize
                body_text="Hi.",
                brand="conaugh_mckenna",
                intent="commercial",
                tenant_id="00000000-0000-0000-0000-000000000fix",
                db=self.db,
            )
        self.assertEqual(r["status"], "error", r)
        self.assertIn("could not be normalized to E.164", r["reason"])

    def test_22f_truly_unscoped_internal_send_bypasses_gates(self):
        """The exempt path is now structural, not intent-based. A send
        with NO caller-supplied lead_id AND NO tenant_id is genuinely
        cross-tenant infrastructure (system-wide health alert, daemon
        ping, etc.) and intentionally skips the tenant-scope gates —
        there's nothing tenant-scoped to enforce.

        Codex audit 2026-06-09 round-4 [medium] caught a subtle bug
        in the round-3 fix: resolve_lead_id() auto-creates a tenant-less
        leads row from to_email when the caller passes no lead_id, and
        the original `if lead_id or tenant_id:` check fired on the
        auto-created row — silently blocking internal infrastructure
        email. The round-4 fix snapshots caller_supplied_tenant_scope
        BEFORE resolve_lead_id so auto-creation doesn't widen scope.

        Uses a non-reserved domain (oasisai.work) to actually exercise
        the auto-create path — example.com would bounce at the RFC 2606
        reserved-domain gate before reaching kill-switch."""
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="ops@oasisai.work",  # non-reserved; triggers auto-create
                subject="health alert",
                body_text="all green",
                # No lead_id, no tenant_id — genuinely cross-tenant.
                intent="internal",
                brand="conaugh_mckenna",
                db=self.db,
            )
        # Must NOT be blocked by the tenant-scope gates.
        reason = (r.get("reason") or "").lower()
        self.assertNotIn("tenant_id mismatch", reason, r)
        self.assertNotIn("kill-switch enforcement unavailable", reason, r)

    def test_22e_kill_switch_runs_for_internal_intent_when_tenant_scoped(self):
        """Codex audit 2026-06-09 round-3 [high]: intent='internal' is
        caller-controlled input. The round-2 fix exempted internal from
        the mismatch + kill-switch checks entirely. A direct Python caller
        could pass intent='internal' with a paused tenant's lead_id and
        a different tenant_id and slip past every tenant-scope gate.

        After round-3: the gates run whenever lead_id OR tenant_id is
        present, regardless of intent. Only structurally cross-tenant
        sends (no lead_id, no tenant_id, intent='internal') are exempt."""
        self.db.table("tenant_records").rows.append({
            "id": "rec-tenant-e",
            "entity_type": "lead",
            "tenant_id": "TENANT-E-PAUSED",
        })
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="rec-tenant-e",
                tenant_id="TENANT-F-UNPAUSED",
                # The bypass attempt: intent='internal'
                intent="internal",
                brand="conaugh_mckenna",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked", r)
        self.assertIn("tenant_id mismatch", r["reason"])

    def test_22c_kill_switch_runs_for_transactional_intent(self):
        """Codex audit 2026-06-09 round-2 [high]: a caller could pass
        intent='transactional' with a mismatched tenant_id to skip the
        kill-switch and mismatch checks entirely. After the fix, the
        mismatch block runs for transactional too. Internal is the only
        intent that bypasses (true cross-tenant infrastructure)."""
        self.db.table("tenant_records").rows.append({
            "id": "rec-tenant-c",
            "entity_type": "lead",
            "tenant_id": "TENANT-C-PAUSED",
        })
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="rec-tenant-c",
                tenant_id="TENANT-D-UNPAUSED",
                # The bypass attempt: intent='transactional'
                intent="transactional",
                brand="conaugh_mckenna",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked", r)
        self.assertIn("tenant_id mismatch", r["reason"])

    def test_22d_kill_switch_resolution_runs_for_transactional_intent(self):
        """Companion to 22c: when the caller supplies only lead_id (no
        tenant_id) and the lookup misses, transactional intent must also
        fail-closed on 'kill-switch enforcement unavailable' — not silently
        skip the resolution like the round-1 fix did."""
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="never-existed-anywhere",
                intent="transactional",
                brand="conaugh_mckenna",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked", r)
        self.assertIn("kill-switch enforcement unavailable", r["reason"])

    def test_22b_kill_switch_blocks_caller_tenant_mismatch(self):
        """Codex audit 2026-06-09 [critical]: when both the DB lookup AND
        the caller supply a tenant_id and they DISAGREE, the gate MUST
        refuse the send. Otherwise a hostile/buggy caller could defeat a
        paused tenant's kill-switch by passing the paused tenant's lead_id
        with an unpaused tenant's tenant_id as the kwarg."""
        # Seed a record that belongs to tenant-A.
        self.db.table("tenant_records").rows.append({
            "id": "rec-tenant-a",
            "entity_type": "application",
            "tenant_id": "TENANT-A-PAUSED",
        })
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="rec-tenant-a",
                # Caller TRIES to point at a different unpaused tenant.
                tenant_id="TENANT-B-UNPAUSED",
                brand="conaugh_mckenna",
                intent="commercial",
                db=self.db,
            )
        self.assertEqual(r["status"], "blocked", r)
        self.assertIn("tenant_id mismatch", r["reason"])

    def test_22_kill_switch_resolves_tenant_records_for_any_entity_type(self):
        """tenant_records.id is a UUID PK — globally unique across
        entity_types. The lookup must match regardless of whether the row
        is a 'lead' / 'application' / 'offer'. Before the fix this filtered
        entity_type='lead' only, so the shop-out fallback (passing
        application_id as the lead_id) failed to resolve and blocked.

        Scoped assertion (see test_21) — kill-switch gate must not fire."""
        # Seed an APPLICATION row (NOT a lead). Pre-fix: filter rejects.
        # Post-fix: lookup hits, tenant resolves, send proceeds past the
        # kill-switch gate.
        self.db.table("tenant_records").rows.append({
            "id": "app-row-001",
            "entity_type": "application",
            "tenant_id": "tenant-from-application-row",
        })
        with self._patch_smtp_ok(), self._patch_suppress(False):
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="hi",
                body_text="hi",
                lead_id="app-row-001",
                brand="conaugh_mckenna",
                intent="commercial",
                db=self.db,
            )
        self.assertNotIn(
            "kill-switch enforcement unavailable",
            r.get("reason") or "",
            f"lookup should have resolved across entity_types: {r}",
        )


class TestNameUtils(unittest.TestCase):
    """Honorific stripping + placeholder detection (no DB, no API)."""

    def setUp(self):
        import importlib, sys
        for m in [m for m in list(sys.modules) if m.startswith("name_utils")]:
            del sys.modules[m]
        import name_utils
        importlib.reload(name_utils)
        self.nu = name_utils

    def test_01_strip_dr_prefix(self):
        self.assertEqual(self.nu.strip_honorifics("Dr. Micah Smith"), "Micah Smith")
        self.assertEqual(self.nu.strip_honorifics("dr. micah"), "micah")
        self.assertEqual(self.nu.strip_honorifics("Dr Micah"), "Micah")

    def test_02_strip_other_honorifics(self):
        for prefix in ["Mr.", "Mrs.", "Ms.", "Prof.", "Rev.", "Sir"]:
            self.assertEqual(
                self.nu.strip_honorifics(f"{prefix} Jane"), "Jane",
                f"failed to strip {prefix}",
            )

    def test_03_no_honorific_unchanged(self):
        self.assertEqual(self.nu.strip_honorifics("Micah Smith"), "Micah Smith")
        self.assertEqual(self.nu.strip_honorifics("Bev"), "Bev")

    def test_04_empty_safe(self):
        self.assertEqual(self.nu.strip_honorifics(""), "")
        self.assertEqual(self.nu.strip_honorifics("   "), "")
        self.assertEqual(self.nu.strip_honorifics("Dr."), "")  # honorific only

    def test_05_safe_first_name_strips_honorifics(self):
        # safe_first_name should now treat "Dr. Micah" as "Dr. Micah" -> "Micah"
        self.assertEqual(self.nu.safe_first_name("Dr. Micah"), "Micah")
        self.assertEqual(self.nu.safe_first_name("Dr."), "team")  # all-honorific -> fallback
        self.assertEqual(self.nu.safe_first_name("Mrs. Jane Doe"), "Jane Doe")


class TestRegionInference(unittest.TestCase):
    """Deterministic tests for region_inference (no DB, no API)."""

    def setUp(self):
        import importlib, sys
        for m in [m for m in list(sys.modules) if m.startswith("region_inference")]:
            del sys.modules[m]
        import region_inference
        importlib.reload(region_inference)
        self.ri = region_inference

    def test_01_city_in_company_wins(self):
        self.assertEqual(
            self.ri.infer_region({"company": "Collingwood Charters"}),
            "the Collingwood area",
        )
        self.assertEqual(
            self.ri.infer_region({"company": "Hamilton Roofing"}),
            "the Hamilton area",
        )

    def test_02_phone_area_code_fallback(self):
        # 416 → Toronto
        self.assertEqual(
            self.ri.infer_region({"company": "Acme Co", "phone": "(416) 555-1212"}),
            "the Toronto area",
        )
        # 905 → GTA
        self.assertEqual(
            self.ri.infer_region({"company": "Acme Co", "phone": "905-555-1212"}),
            "the Greater Toronto area",
        )
        # 705 → Central Ontario
        self.assertEqual(
            self.ri.infer_region({"company": "Acme Co", "phone": "(705) 443-1124"}),
            "Central Ontario",
        )

    def test_03_default_fallback_when_unknown(self):
        self.assertEqual(self.ri.infer_region({}), "your area")
        self.assertEqual(
            self.ri.infer_region({"company": "Acme Co"}),
            "your area",
        )

    def test_04_phone_with_country_code(self):
        # 1-prefixed phone still resolves
        self.assertEqual(
            self.ri.infer_region({"company": "Acme", "phone": "1-416-555-1212"}),
            "the Toronto area",
        )

    def test_05_city_beats_phone(self):
        # Even if phone is non-Ontario, a known city in company wins
        self.assertEqual(
            self.ri.infer_region({"company": "Toronto Plumbing", "phone": "(555) 555-5555"}),
            "the Toronto area",
        )

    def test_06_none_lead_safe(self):
        # Defensive: empty / None / missing fields shouldn't crash
        self.assertEqual(self.ri.infer_region(None), "your area")  # type: ignore[arg-type]
        self.assertEqual(self.ri.infer_region({"company": None, "phone": None}), "your area")


class TestInboundClassifier(unittest.TestCase):
    """Pure-logic tests — no Haiku calls, no DB. Keyword fallback + enum
    validation are the deterministic pieces we can test offline."""

    def setUp(self):
        _fresh_env({})
        import importlib, sys
        for m in [m for m in list(sys.modules) if m.startswith("inbound_classifier")]:
            del sys.modules[m]
        import inbound_classifier
        importlib.reload(inbound_classifier)
        self.ic = inbound_classifier

    def test_01_fallback_classifies_booking(self):
        r = self.ic._keyword_fallback("yes definitely book me in for wednesday")
        self.assertEqual(r["sentiment"], "positive")
        self.assertEqual(r["priority"], "hot")
        self.assertTrue(r["fallback"])

    def test_02_fallback_classifies_unsubscribe(self):
        r = self.ic._keyword_fallback("please stop emailing me, unsubscribe")
        self.assertEqual(r["intent"], "unsubscribe")
        self.assertEqual(r["suggested_action"], "mark_unsubscribed")

    def test_03_fallback_classifies_bounce(self):
        r = self.ic._keyword_fallback("mailer-daemon: delivery status undeliverable")
        self.assertEqual(r["intent"], "spam_bounce")
        self.assertEqual(r["priority"], "low")

    def test_04_fallback_classifies_ooo(self):
        r = self.ic._keyword_fallback("I am out of office until next week")
        self.assertEqual(r["intent"], "out_of_office")

    def test_05_validate_normalizes_bad_enum(self):
        r = self.ic._validate_and_normalize({
            "sentiment": "super-positive",  # invalid
            "intent": "nonsense",  # invalid
            "priority": "blazing",  # invalid
            "stage_signal": "fake",  # invalid
            "suggested_action": "invalid_action",
            "confidence": 3.5,  # clamp to 1.0
        })
        self.assertEqual(r["sentiment"], "neutral")
        self.assertEqual(r["intent"], "other")
        self.assertEqual(r["priority"], "cold")
        self.assertEqual(r["stage_signal"], "hold")
        self.assertEqual(r["suggested_action"], "hold_for_review")
        self.assertEqual(r["confidence"], 1.0)

    def test_06_validate_preserves_valid(self):
        r = self.ic._validate_and_normalize({
            "sentiment": "positive",
            "intent": "booking",
            "priority": "hot",
            "stage_signal": "escalate_to_engaged",
            "suggested_action": "draft_booking_confirmation",
            "confidence": 0.94,
        })
        self.assertEqual(r["sentiment"], "positive")
        self.assertEqual(r["intent"], "booking")
        self.assertEqual(r["priority"], "hot")
        self.assertEqual(r["confidence"], 0.94)


class TestDraftCritic(unittest.TestCase):
    """Pure-logic tests for the slop detector + verdict validator."""

    def setUp(self):
        _fresh_env({})
        import importlib, sys
        for m in [m for m in list(sys.modules) if m.startswith("draft_critic")]:
            del sys.modules[m]
        import draft_critic
        importlib.reload(draft_critic)
        self.dc = draft_critic

    def test_01_catches_classic_slop(self):
        # 2026-04-27: "wanted to reach out" was demoted from auto-flag —
        # CC wants brief personal-sounding cold opens to ship. Assert that
        # truly-bad phrases still flag and that "wanted to reach out" no
        # longer does.
        body = ("Hi Jane,\n\nI hope this email finds you well. I wanted to "
                "reach out about how we can leverage your synergies to "
                "circle back...")
        hits = self.dc.find_slop(body)
        excerpts = [h["excerpt"].lower() for h in hits]
        self.assertTrue(any("finds you well" in e for e in excerpts))
        self.assertTrue(any("leverage" in e for e in excerpts))
        self.assertTrue(any("synerg" in e for e in excerpts))
        self.assertTrue(any("circle back" in e for e in excerpts))
        self.assertFalse(any("wanted to reach out" in e for e in excerpts),
                         "wanted-to-reach-out should no longer auto-flag")

    def test_02_clean_draft_has_zero_hits(self):
        body = ("Hey Jane — saw you're taking 5 days to send HVAC quotes. "
                "Our clients cut that to 15 minutes with one automation. Want a "
                "5-min walkthrough next week?")
        hits = self.dc.find_slop(body)
        self.assertEqual(len(hits), 0)

    def test_03_ungrounded_claim_forces_escalate(self):
        r = self.dc._validate_critic_output({
            "verdict": "ship",  # critic said ship
            "score": 8.5,
            "issues": [{"type": "ungrounded_claim", "excerpt": "...", "reason": "..."}],
        }, slop_hits=[])
        # Validator must override ship → escalate because of ungrounded claim
        self.assertEqual(r["verdict"], "escalate")

    def test_04_slop_hit_downgrades_ship_to_revise(self):
        r = self.dc._validate_critic_output(
            {"verdict": "ship", "score": 8.0, "issues": []},
            slop_hits=[{"excerpt": "I hope this finds you well"}],
        )
        self.assertEqual(r["verdict"], "revise")

    def test_05_score_clamped_to_valid_range(self):
        r = self.dc._validate_critic_output(
            {"verdict": "ship", "score": 50.0, "issues": []},
            slop_hits=[],
        )
        self.assertLessEqual(r["score"], 10.0)


class TestAutonomousAgentPolicy(unittest.TestCase):
    """Pure-logic tests for the verify() policy gates. These were the source
    of the 2026-04-20 bug where escalations were buffered instead of firing
    through business-hours — that ordering is what's tested here."""

    def setUp(self):
        _fresh_env({})
        import importlib, sys
        for m in [m for m in list(sys.modules) if m.startswith("autonomous_agent")]:
            del sys.modules[m]
        import autonomous_agent
        importlib.reload(autonomous_agent)
        self.aa = autonomous_agent

    def _mk(self, decision_type: str = "day2_followup", score: int = 45) -> Any:
        return self.aa.Decision(
            tick_id="test",
            phase="recall",
            decision_type=decision_type,
            target_lead_id="lead-X",
            target_description="test",
            reasoning="test",
            confidence=0.8,
            chosen_action="draft_and_send",
            metadata={"lead_score": score},
        )

    def test_01_hot_inbound_escalates_even_outside_business_hours(self):
        # The bug that was caught + fixed: hot inbound should escalate
        # regardless of hour. Escalations must bypass the business-hours gate.
        d = self._mk(decision_type="hot_inbound_reply", score=45)
        out = self.aa.verify([d], daily_sends=0, in_business_hours=False)
        self.assertEqual(out[0].chosen_action, "escalate_to_cc")

    def test_02_high_value_always_escalates(self):
        d = self._mk(decision_type="day2_followup", score=95)  # score>=80
        out = self.aa.verify([d], daily_sends=0, in_business_hours=True)
        self.assertEqual(out[0].chosen_action, "escalate_to_cc")

    def test_03_routine_followup_buffers_outside_business_hours(self):
        d = self._mk(decision_type="day2_followup", score=45)
        out = self.aa.verify([d], daily_sends=0, in_business_hours=False)
        self.assertEqual(out[0].chosen_action, "buffer_until_business_hours")

    def test_04_tick_cap_defers_after_threshold(self):
        decisions = [self._mk() for _ in range(self.aa.TICK_MAX_SENDS + 2)]
        out = self.aa.verify(decisions, daily_sends=0, in_business_hours=True)
        deferred = [d for d in out if d.chosen_action == "defer_to_next_tick"]
        self.assertEqual(len(deferred), 2)  # 5 sent, 2 deferred

    def test_05_daily_cap_defers(self):
        d = self._mk(decision_type="day2_followup", score=45)
        out = self.aa.verify([d], daily_sends=50, in_business_hours=True)
        self.assertEqual(out[0].chosen_action, "defer_to_next_day")

    def test_06_mark_dormant_not_consumed_by_caps(self):
        # mark_dormant should not consume the tick cap — it's not a send.
        dormants = [
            self.aa.Decision(
                tick_id="t", phase="recall", decision_type="mark_dormant",
                target_lead_id=f"lead-{i}", target_description="d", reasoning="r",
                confidence=0.9, chosen_action="mark_dormant", metadata={"lead_score": 20},
            ) for i in range(10)
        ]
        out = self.aa.verify(dormants, daily_sends=0, in_business_hours=True)
        self.assertTrue(all(d.chosen_action == "mark_dormant" for d in out))

    def test_07_compose_summary_empty_pipeline(self):
        state = {"tick_number": 1, "now_local": datetime.now(timezone.utc),
                 "business_hours": True}
        s = self.aa._compose_summary("t", state, [], duration_s=1.5)
        self.assertEqual(s["decisions_total"], 0)
        self.assertIn("Nothing actionable", s["english_summary"])

    def test_08_compose_summary_with_escalation(self):
        d = self._mk()
        d.chosen_action = "escalate_to_cc"
        d.outcome_status = "escalated"
        state = {"tick_number": 2, "now_local": datetime.now(timezone.utc),
                 "business_hours": True}
        s = self.aa._compose_summary("t", state, [d], duration_s=1.0)
        self.assertEqual(s["escalated"], 1)
        self.assertIn("Escalated", s["english_summary"])


class TestRegisterSkill(unittest.TestCase):
    """Light structural tests against the real skills/send-gateway dir
    (it's known-clean from Build #6). No Supabase writes."""

    def setUp(self):
        _fresh_env({})
        import importlib, sys
        for m in [m for m in list(sys.modules) if m.startswith("register_skill")]:
            del sys.modules[m]
        import register_skill
        importlib.reload(register_skill)
        self.rs = register_skill

    def test_01_validate_known_good_skill(self):
        r = self.rs.validate_skill("send-gateway")
        self.assertTrue(r["valid"])
        self.assertTrue(r["exists"])
        self.assertEqual(r["frontmatter"].get("name"), "send-gateway")

    def test_02_validate_nonexistent(self):
        r = self.rs.validate_skill("does-not-exist-xyz-123")
        self.assertFalse(r["valid"])
        self.assertFalse(r["exists"])
        errors = [i for i in r["issues"] if i["severity"] == "error"]
        self.assertTrue(len(errors) >= 1)

    def test_03_frontmatter_parser_rejects_mismatch(self):
        # Build a fake skill in a tmp dir where frontmatter name != folder name
        import shutil
        import uuid
        from pathlib import Path as P
        tmp_root = PROJECT_ROOT / "tmp"
        tmp_root.mkdir(exist_ok=True)
        tmp = tmp_root / f"skill-test-{uuid.uuid4().hex}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            fake_skills = P(tmp) / "skills"
            (fake_skills / "my-skill").mkdir(parents=True)
            (fake_skills / "my-skill" / "SKILL.md").write_text(
                "---\nname: different-name\ndescription: test\n---\n\n# content",
                encoding="utf-8",
            )
            # Monkeypatch SKILLS_DIR for this test
            orig = self.rs.SKILLS_DIR
            self.rs.SKILLS_DIR = fake_skills
            try:
                r = self.rs.validate_skill("my-skill")
                self.assertFalse(r["valid"])
                msgs = " ".join(i["message"] for i in r["issues"])
                self.assertIn("does not match folder", msgs)
            finally:
                self.rs.SKILLS_DIR = orig
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestContextBuilder(unittest.TestCase):

    def setUp(self):
        _fresh_env({})
        # context_builder moved to scripts/core/ during the 2026-05 reorg.
        from core import context_builder
        import importlib
        importlib.reload(context_builder)
        self.cb = context_builder
        self.db = FakeSupabase()
        self.db.tables["leads"].rows.append({
            "id": "L1",
            "name": "John",
            "email": "john@acme.example",
            "company": "Acme",
            "status": "new",
            "source": "cold_outreach",
        })

    def test_01_cold_stage_no_history(self):
        ctx = self.cb.get_entity_context(lead_id="L1", db=self.db)
        self.assertEqual(ctx["relationship_stage"], "cold")
        self.assertEqual(ctx["outbound_count"], 0)

    def test_02_contacted_stage_after_one_outbound(self):
        now = datetime.now(timezone.utc).isoformat()
        self.db.tables["lead_interactions"].rows.append({
            "id": "ix1", "lead_id": "L1", "channel": "email",
            "type": "email_sent", "created_at": now,
        })
        ctx = self.cb.get_entity_context(lead_id="L1", db=self.db)
        self.assertEqual(ctx["relationship_stage"], "contacted")
        self.assertEqual(ctx["outbound_count"], 1)

    def test_03_engaged_stage_after_recent_reply(self):
        now = datetime.now(timezone.utc)
        self.db.tables["lead_interactions"].rows.extend([
            {"id": "o1", "lead_id": "L1", "channel": "email",
             "type": "email_sent", "created_at": (now - timedelta(days=3)).isoformat()},
            {"id": "i1", "lead_id": "L1", "channel": "email",
             "type": "email_reply", "content": "yes interested, book me in",
             "created_at": (now - timedelta(days=1)).isoformat()},
        ])
        ctx = self.cb.get_entity_context(lead_id="L1", db=self.db)
        self.assertEqual(ctx["relationship_stage"], "engaged")
        self.assertEqual(ctx["sentiment_signal"], "positive")

    def test_04_sentiment_negative(self):
        self.assertEqual(self.cb._infer_sentiment("not interested, unsubscribe"), "negative")

    def test_05_prompt_context_includes_stage(self):
        ctx = self.cb.get_entity_context(lead_id="L1", db=self.db)
        prompt = self.cb.compose_prompt_context(ctx)
        self.assertIn("RELATIONSHIP STAGE", prompt)
        self.assertIn("cold", prompt)
        self.assertIn("TONE GUIDANCE", prompt)


# ---- Runner -----------------------------------------------------------------

class TestAutonomousNurtureLane(unittest.TestCase):
    """2026-08-01 policy (CC, operator-approved): autonomous inbound-nurture
    replies skip ONLY the reply-since-last-outbound gate — an inbound
    last-touch is their trigger, not a hand-off signal. Every other gate
    still applies, and each successful send fires a Telegram log ping."""

    def setUp(self):
        self._env_patcher = mock.patch.dict(os.environ, _fresh_env({}), clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        self.sg = _import_gateway_fresh()
        self.db = FakeSupabase()
        self.sg._DAILY_CAP_ALERTS_SENT.clear()
        self._critic_patcher = mock.patch.object(
            self.sg,
            "critique_draft",
            return_value={"verdict": "ship", "reasons": [], "notes": ""},
        )
        self._critic_patcher.start()
        self.addCleanup(self._critic_patcher.stop)
        self.db.tables["leads"].rows.append({
            "id": "lead-001",
            "name": "Jane Test",
            "email": "jane@acme.example",
            "status": "new",
            "tenant_id": "00000000-0000-0000-0000-000000000fix",
        })

    def _seed_inbound_last_touch(self):
        # 7 days old: recent enough to be the lead's last touch (reply-since
        # gate trigger), old enough to stay clear of the 72h implied cooldown
        # and the 90-min inter-touch gap.
        old = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        self.db.tables["lead_interactions"].rows.append({
            "id": "in-1",
            "lead_id": "lead-001",
            "channel": "email",
            "direction": "inbound",
            "type": "email_received",
            "created_at": old,
        })

    def test_nurture_allows_inbound_last_touch(self):
        self._seed_inbound_last_touch()
        r = self.sg.can_act(
            lead_id="lead-001", channel="email",
            to_email="jane@acme.example",
            agent_source="inbound_nurture", db=self.db,
        )
        self.assertTrue(r["allowed"], r.get("reason"))

    def test_cold_source_still_blocked_by_reply_gate(self):
        self._seed_inbound_last_touch()
        r = self.sg.can_act(
            lead_id="lead-001", channel="email",
            to_email="jane@acme.example",
            agent_source="funnel_nurture", db=self.db,
        )
        self.assertFalse(r["allowed"])
        self.assertIn("merchant replied", r["reason"])

    def test_nurture_still_blocked_by_manual_pause(self):
        self._seed_inbound_last_touch()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.db.tables["leads"].rows[0]["data"] = {"paused_until": future}
        r = self.sg.can_act(
            lead_id="lead-001", channel="email",
            to_email="jane@acme.example",
            agent_source="inbound_nurture", db=self.db,
        )
        self.assertFalse(r["allowed"])

    def test_nurture_send_fires_telegram_ping(self):
        self._seed_inbound_last_touch()
        with mock.patch.object(self.sg, "_send_email_smtp", return_value=(True, None)), \
             mock.patch.object(self.sg, "should_suppress", return_value=False), \
             mock.patch.object(self.sg, "_telegram_notify", return_value=True) as notify:
            r = self.sg.send(
                channel="email", agent_source="inbound_nurture",
                to_email="jane@acme.example", subject="Re: hi",
                body_text="reply", body_html="<p>reply</p>", db=self.db,
            )
        self.assertEqual(r["status"], "sent", r.get("reason"))
        notify.assert_called_once()
        self.assertIn("[SENT] Responded to Lead: jane@acme.example",
                      notify.call_args[0][0])

    def test_non_nurture_send_fires_no_ping(self):
        with mock.patch.object(self.sg, "_send_email_smtp", return_value=(True, None)), \
             mock.patch.object(self.sg, "should_suppress", return_value=False), \
             mock.patch.object(self.sg, "_telegram_notify", return_value=True) as notify:
            r = self.sg.send(
                channel="email", agent_source="test_harness",
                to_email="jane@acme.example", subject="hi",
                body_text="hello", body_html="<p>hello</p>", db=self.db,
            )
        self.assertEqual(r["status"], "sent", r.get("reason"))
        notify.assert_not_called()


def _run_all(verbose: bool = False) -> bool:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(TestSendGateway),
        loader.loadTestsFromTestCase(TestAutonomousNurtureLane),
        loader.loadTestsFromTestCase(TestInboundClassifier),
        loader.loadTestsFromTestCase(TestDraftCritic),
        loader.loadTestsFromTestCase(TestAutonomousAgentPolicy),
        loader.loadTestsFromTestCase(TestRegisterSkill),
        loader.loadTestsFromTestCase(TestContextBuilder),
    ])
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    return result.wasSuccessful()


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    ok = _run_all(verbose=args.verbose)
    if args.json:
        print(json.dumps({"ok": ok}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
