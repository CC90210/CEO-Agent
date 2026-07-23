"""Tests for email_brain — the multi-brain router + hybrid/guarded autonomy.

Native replacement for the n8n "OASIS Inbound Qualifier" agent brains. The
decision layer (decide_action) is pure and fully covered here; process_email
dispatches to injected I/O handlers so wiring is verified without sending mail.

Run:
  python scripts/tests/test_email_brain.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from email_brain import decide_action, process_email  # noqa: E402


class TestDecideAction(unittest.TestCase):
    def test_financial_always_hands_off_no_send(self):
        d = decide_action("financial_legal", confidence=0.95)
        self.assertEqual(d["action"], "handoff_atlas")
        self.assertFalse(d["should_send"])
        self.assertFalse(d["should_archive"])

    def test_financial_low_confidence_still_handoff(self):
        d = decide_action("financial_legal", confidence=0.2)
        self.assertEqual(d["action"], "handoff_atlas")

    def test_low_priority_high_conf_archives(self):
        d = decide_action("low_priority", confidence=0.9)
        self.assertEqual(d["action"], "archive")
        self.assertTrue(d["should_archive"])
        self.assertFalse(d["should_send"])

    def test_low_priority_low_conf_holds_for_review(self):
        # Never auto-archive an uncertain read — could be a real email.
        d = decide_action("low_priority", confidence=0.4, archive_threshold=0.6)
        self.assertEqual(d["action"], "review")
        self.assertFalse(d["should_archive"])
        self.assertTrue(d["hold_for_review"])

    def test_business_opportunity_always_drafts_never_sends(self):
        d = decide_action("business_opportunity", confidence=0.99,
                          is_known_client=True, auto_send_enabled=True)
        self.assertEqual(d["action"], "draft_hold")
        self.assertFalse(d["should_send"])
        self.assertTrue(d["hold_for_review"])

    def test_tech_support_known_client_high_conf_autosends(self):
        d = decide_action("technical_support", confidence=0.85,
                          is_known_client=True, auto_send_enabled=True,
                          reply_threshold=0.7)
        self.assertEqual(d["action"], "auto_reply")
        self.assertTrue(d["should_send"])

    def test_tech_support_autosend_disabled_drafts(self):
        d = decide_action("technical_support", confidence=0.85,
                          is_known_client=True, auto_send_enabled=False)
        self.assertEqual(d["action"], "draft_hold")
        self.assertFalse(d["should_send"])

    def test_tech_support_unknown_sender_drafts(self):
        d = decide_action("technical_support", confidence=0.9,
                          is_known_client=False, auto_send_enabled=True)
        self.assertEqual(d["action"], "draft_hold")
        self.assertFalse(d["should_send"])

    def test_tech_support_low_conf_drafts(self):
        d = decide_action("technical_support", confidence=0.5,
                          is_known_client=True, auto_send_enabled=True,
                          reply_threshold=0.7)
        self.assertEqual(d["action"], "draft_hold")
        self.assertFalse(d["should_send"])

    def test_contract_keys_present_and_mutually_exclusive(self):
        for cat in ("technical_support", "business_opportunity",
                    "financial_legal", "low_priority"):
            d = decide_action(cat, confidence=0.9, is_known_client=True,
                              auto_send_enabled=True)
            for k in ("brain", "action", "should_send", "should_archive",
                      "hold_for_review", "reason"):
                self.assertIn(k, d)
            # A send and an archive can never both fire on one email.
            self.assertFalse(d["should_send"] and d["should_archive"])


def _email(**over):
    base = {"from": "ops@client.example", "subject": "hi", "body": "hello",
            "message_id": "<1@x>", "is_known_client": True, "attachments": []}
    base.update(over)
    return base


def _deps():
    return {
        "draft_reply": MagicMock(return_value={"subject": "Re: hi", "body": "hi back"}),
        "send_reply": MagicMock(return_value={"status": "sent"}),
        "store_draft": MagicMock(return_value="draft-1"),
        "archive": MagicMock(),
        "handoff_atlas": MagicMock(),
        "notify": MagicMock(),
        "mark_read": MagicMock(),
    }


def _classifier(category, confidence=0.9):
    def c(content=None, subject=None, from_identity=None):
        return {"category": category, "confidence": confidence,
                "fallback": False, "notes": ""}
    return c


class TestProcessEmailDispatch(unittest.TestCase):
    def test_autoreply_sends_notifies_marks_read(self):
        deps = _deps()
        out = process_email(_email(), classifier=_classifier("technical_support"),
                            deps=deps, config={"auto_send_enabled": True})
        self.assertTrue(out["sent"])
        deps["send_reply"].assert_called_once()
        deps["notify"].assert_called_once()
        deps["mark_read"].assert_called_once()
        deps["archive"].assert_not_called()

    def test_business_opportunity_drafts_and_holds_no_send(self):
        deps = _deps()
        out = process_email(_email(from_identity="lead@prospect.example"),
                            classifier=_classifier("business_opportunity"),
                            deps=deps, config={"auto_send_enabled": True})
        self.assertFalse(out["sent"])
        self.assertTrue(out["drafted"])
        deps["send_reply"].assert_not_called()
        deps["store_draft"].assert_called_once()
        deps["notify"].assert_called_once()      # CC pinged a draft is ready
        deps["mark_read"].assert_not_called()    # stays unread for review

    def test_draft_hold_notification_contains_the_reply(self):
        # The hold ping must carry the actual proposed reply — there is no
        # separate approval UI, so the Telegram message IS the review surface.
        deps = _deps()
        deps["draft_reply"] = MagicMock(
            return_value={"subject": "Re: intro", "body": "Happy to chat Thursday. CC"})
        process_email(_email(from_identity="lead@prospect.example"),
                      classifier=_classifier("business_opportunity"),
                      deps=deps, config={"auto_send_enabled": True})
        msg = deps["notify"].call_args.args[0]
        self.assertIn("Happy to chat Thursday", msg)
        self.assertIn("proposed reply", msg.lower())

    def test_low_priority_archives_silently(self):
        deps = _deps()
        out = process_email(_email(), classifier=_classifier("low_priority", 0.9),
                            deps=deps, config={"auto_send_enabled": True})
        self.assertTrue(out["archived"])
        deps["archive"].assert_called_once()
        deps["mark_read"].assert_called_once()
        deps["send_reply"].assert_not_called()
        deps["notify"].assert_not_called()       # no ping on archive

    def test_financial_hands_off_to_atlas_no_send(self):
        deps = _deps()
        out = process_email(_email(), classifier=_classifier("financial_legal"),
                            deps=deps, config={"auto_send_enabled": True})
        self.assertTrue(out["handed_off"])
        deps["handoff_atlas"].assert_called_once()
        deps["send_reply"].assert_not_called()
        deps["notify"].assert_called_once()      # CC pinged; never silently swallowed
        deps["mark_read"].assert_not_called()    # stays unread until Atlas consumes it

    def test_autosend_disabled_globally_never_sends(self):
        deps = _deps()
        out = process_email(_email(), classifier=_classifier("technical_support"),
                            deps=deps, config={"auto_send_enabled": False})
        self.assertFalse(out["sent"])
        self.assertTrue(out["drafted"])
        deps["send_reply"].assert_not_called()

    def test_autoreply_downgrades_when_critic_rejects(self):
        deps = _deps()
        # Drafter reports the reply is not ship-worthy (critic rejected).
        deps["draft_reply"] = MagicMock(
            return_value={"subject": "Re: hi", "body": "slop", "ship": False})
        out = process_email(_email(), classifier=_classifier("technical_support"),
                            deps=deps, config={"auto_send_enabled": True})
        self.assertFalse(out["sent"])
        self.assertTrue(out["drafted"])
        self.assertEqual(out["action"], "draft_hold")
        deps["send_reply"].assert_not_called()
        deps["store_draft"].assert_called_once()
        deps["mark_read"].assert_not_called()

    def test_never_raises_on_handler_failure(self):
        deps = _deps()
        deps["send_reply"].side_effect = RuntimeError("smtp down")
        # Must not raise; outcome reflects the failure.
        out = process_email(_email(), classifier=_classifier("technical_support"),
                            deps=deps, config={"auto_send_enabled": True})
        self.assertIn("error", out)
        self.assertFalse(out["sent"])


class TestDraftReply(unittest.TestCase):
    def test_ships_when_critic_ships(self):
        from email_brain import draft_reply_via_cli
        runner = lambda p, system=None, model="sonnet", timeout=90: '{"subject":"Re: down","body":"On it — fix out within the hour. CC"}'
        critic = lambda s, b: {"verdict": "ship"}
        d = draft_reply_via_cli(_email(), "technical_support", runner=runner, critic=critic)
        self.assertTrue(d["ship"])
        self.assertIn("fix", d["body"].lower())

    def test_downgrades_when_critic_rejects(self):
        from email_brain import draft_reply_via_cli
        runner = lambda p, system=None, model="sonnet", timeout=90: '{"subject":"Re","body":"I hope this email finds you well!!!"}'
        critic = lambda s, b: {"verdict": "reject"}
        d = draft_reply_via_cli(_email(), "technical_support", runner=runner, critic=critic)
        self.assertFalse(d["ship"])

    def test_empty_body_is_not_shippable(self):
        from email_brain import draft_reply_via_cli
        runner = lambda p, system=None, model="sonnet", timeout=90: None  # CLI down
        d = draft_reply_via_cli(_email(), "technical_support", runner=runner,
                                critic=lambda s, b: {"verdict": "ship"})
        self.assertFalse(d["ship"])
        self.assertEqual(d["body"], "")

    def test_critic_failure_does_not_autoship(self):
        from email_brain import draft_reply_via_cli
        runner = lambda p, system=None, model="sonnet", timeout=90: '{"subject":"Re","body":"real reply"}'
        def critic(s, b):
            raise RuntimeError("critic down")
        d = draft_reply_via_cli(_email(), "technical_support", runner=runner, critic=critic)
        self.assertFalse(d["ship"])  # fail-safe: never auto-ship if the gate is down


class TestBuildDefaultDeps(unittest.TestCase):
    def test_has_all_handler_keys_and_callable(self):
        from email_brain import build_default_deps
        deps = build_default_deps(mark_read=lambda e: None)
        for k in ("draft_reply", "send_reply", "store_draft", "archive",
                  "handoff_atlas", "notify", "mark_read"):
            self.assertIn(k, deps)
            self.assertTrue(callable(deps[k]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
