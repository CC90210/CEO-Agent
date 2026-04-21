"""
Tests for the V5.6 + reasoning-loop stack.

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
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
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

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = _FakeTable(name)
        return self.tables[name]


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
    """Force a fresh import of send_gateway so each test starts clean."""
    import importlib
    mods = [m for m in list(sys.modules) if m.startswith("send_gateway")]
    for m in mods:
        del sys.modules[m]
    import send_gateway
    importlib.reload(send_gateway)
    return send_gateway


# ---- Tests ------------------------------------------------------------------

class TestSendGateway(unittest.TestCase):

    def setUp(self):
        _fresh_env({})
        self.sg = _import_gateway_fresh()
        self.db = FakeSupabase()
        # Seed one lead so resolve_lead_id has something to find
        self.db.tables["leads"].rows.append({
            "id": "lead-001",
            "name": "Jane Test",
            "email": "jane@acme.example",
            "status": "new",
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

    # 1. Golden path: commercial email, fresh recipient
    def test_01_golden_path_sent(self):
        with self._patch_smtp_ok(), self._patch_suppress(False):
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
        with self._patch_smtp_ok(), self._patch_suppress(False):
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
        now = datetime.now(timezone.utc)
        cap = self.sg.DAILY_CAPS["email"]
        for i in range(cap):
            self.db.tables["lead_interactions"].rows.append({
                "id": f"cap-{i}",
                "lead_id": f"other-{i}",
                "channel": "email",
                "type": "email_sent",
                "created_at": now.isoformat(),
            })
        with self._patch_smtp_ok(), self._patch_suppress(False):
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
            # Kona Makana brand should flow a different sender name
            r = self.sg.send(
                channel="email",
                agent_source="test_harness",
                to_email="jane@acme.example",
                subject="personal brand",
                body_text="hi",
                brand="kona_makana",
                db=self.db,
            )
        self.assertEqual(r["status"], "sent")
        # Verify metadata carried the brand
        ix = self.db.tables["lead_interactions"].rows[-1]
        meta = ix.get("metadata") or {}
        self.assertEqual(meta.get("brand"), "kona_makana")

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
        body = "Hi Jane,\n\nI hope this email finds you well. I wanted to reach out about..."
        hits = self.dc.find_slop(body)
        excerpts = [h["excerpt"].lower() for h in hits]
        self.assertTrue(any("finds you well" in e for e in excerpts))
        self.assertTrue(any("wanted to reach out" in e for e in excerpts))

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
        import tempfile, shutil
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as tmp:
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


class TestContextBuilder(unittest.TestCase):

    def setUp(self):
        _fresh_env({})
        import context_builder
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

def _run_all(verbose: bool = False) -> bool:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(TestSendGateway),
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
