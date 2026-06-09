"""CASL-compliance tests for the dashboard outbound-email consumer.

Audit Phase 2 (2026-06-09): the dashboard drawer queues operator-composed
lead emails straight through lib.smtp_send, bypassing send_gateway. These
tests lock in that the consumer now applies the same compliance the gateway
does — suppression (commercial only) + CASL footer + List-Unsubscribe
(non-internal) — at send time.

Transport is fully mocked: no real email, no real Supabase, no network.

Run:
  python -m pytest scripts/tests/test_dashboard_email_consumer_compliance.py -q
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dashboard_email_consumer as dec  # noqa: E402
from casl_compliance import build_casl_footer  # noqa: E402


def _plain_part(msg) -> str:
    """Extract the decoded text/plain body from a MIMEMultipart message."""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            return payload.decode("utf-8", "replace") if payload else ""
    return ""


def _row(intent: str | None = None, content: str = "Hi there, just checking in on your project.") -> dict:
    md: dict = {"status": "queued"}
    if intent is not None:
        md["intent"] = intent
    return {
        "id": "row-123",
        "tenant_id": "tenant-abc",
        "lead_id": "lead-xyz",
        "subject": "Quick check-in",
        "content": content,
        "to_email": "owner@somebusiness.example",  # reserved/test domain — never a real send
        "metadata": md,
    }


SEND_ENV = {"GMAIL_USER": "sender@oasisai.work", "GMAIL_APP_PASSWORD": "app-pw"}


class TestBuildMessageFooter(unittest.TestCase):
    """_build_message footer/header behavior is a pure function — test it directly."""

    def test_commercial_appends_casl_footer_and_headers(self):
        msg = dec._build_message(_row(intent="commercial"), "sender@oasisai.work", "commercial")
        plain = _plain_part(msg)
        expected_footer = build_casl_footer("owner@somebusiness.example")
        self.assertIn(expected_footer.strip(), plain,
                      "commercial send must carry the CASL footer in the plain part")
        self.assertIsNotNone(msg["List-Unsubscribe"],
                             "commercial send must carry a List-Unsubscribe header")

    def test_transactional_still_gets_footer(self):
        msg = dec._build_message(_row(intent="transactional"), "sender@oasisai.work", "transactional")
        plain = _plain_part(msg)
        self.assertIn(build_casl_footer("owner@somebusiness.example").strip(), plain,
                      "transactional send still gets the footer (matches send_gateway: intent != internal)")
        self.assertIsNotNone(msg["List-Unsubscribe"])

    def test_internal_intent_skips_footer_and_headers(self):
        msg = dec._build_message(_row(intent="internal"), "sender@oasisai.work", "internal")
        plain = _plain_part(msg)
        self.assertNotIn("OASIS AI Solutions", plain,
                         "internal send must NOT append the CASL footer")
        self.assertIsNone(msg["List-Unsubscribe"],
                          "internal send must NOT carry List-Unsubscribe")

    def test_footer_not_double_stamped_when_operator_already_signed(self):
        footer = build_casl_footer("owner@somebusiness.example")
        signed_content = "Hi there.\n\n" + footer
        msg = dec._build_message(_row(intent="commercial", content=signed_content),
                                 "sender@oasisai.work", "commercial")
        plain = _plain_part(msg)
        # The "<sender> — <business>" signature line must appear exactly once
        # (the footer block itself mentions the business name twice — sig +
        # address — so we key on the unique signature line, not the name).
        sig_line = next(ln for ln in footer.splitlines() if " — " in ln)
        self.assertEqual(plain.count(sig_line), 1,
                         "footer must not be double-stamped when already present")


class TestSendOneCompliance(unittest.TestCase):
    """_send_one suppression gating — the core compliance behavior."""

    def _run_send_one(self, row, *, suppress: bool):
        """Call _send_one with transport + side effects mocked. Returns
        (result_status, mark_calls, publish_calls, smtp_mock)."""
        mark_calls: list = []
        publish_calls: list = []

        def fake_mark(sb, row_id, *, status, error=None):
            mark_calls.append({"row_id": row_id, "status": status, "error": error})

        def fake_publish(sb, *, event_type, tenant_id, payload):
            publish_calls.append({"event_type": event_type, "payload": payload})

        smtp_mock = mock.MagicMock(return_value=(True, None))
        with mock.patch.object(dec, "should_suppress", return_value=suppress), \
             mock.patch.object(dec, "smtp_send", smtp_mock), \
             mock.patch.object(dec, "_mark_status", fake_mark), \
             mock.patch.object(dec, "_publish_event", fake_publish), \
             mock.patch.object(dec, "_resolve_send_identity", None), \
             mock.patch.object(dec, "_send_via_gmail_api", None):
            result = dec._send_one(SEND_ENV, object(), row)
        return result, mark_calls, publish_calls, smtp_mock

    def test_suppressed_commercial_is_not_sent(self):
        result, marks, pubs, smtp_mock = self._run_send_one(_row(intent="commercial"), suppress=True)
        self.assertEqual(result, "suppressed")
        smtp_mock.assert_not_called()
        self.assertTrue(any(m["status"] == "suppressed" for m in marks),
                        "suppressed recipient must mark row status='suppressed'")
        self.assertTrue(any(p["event_type"] == "BRAVO_DASHBOARD_EMAIL_SUPPRESSED" for p in pubs),
                        "must emit a suppression event")

    def test_non_suppressed_commercial_is_sent(self):
        result, marks, pubs, smtp_mock = self._run_send_one(_row(intent="commercial"), suppress=False)
        self.assertEqual(result, "sent")
        smtp_mock.assert_called_once()
        # footer present in the message handed to the transport
        msg = smtp_mock.call_args.args[2]
        self.assertIn(build_casl_footer("owner@somebusiness.example").strip(), _plain_part(msg))
        self.assertTrue(any(m["status"] == "sent" for m in marks))

    def test_transactional_skips_suppression(self):
        # Even with should_suppress -> True, a transactional row must still send
        # (matches send_gateway: suppression gates commercial only).
        result, marks, pubs, smtp_mock = self._run_send_one(_row(intent="transactional"), suppress=True)
        self.assertEqual(result, "sent")
        smtp_mock.assert_called_once()
        self.assertFalse(any(m["status"] == "suppressed" for m in marks),
                         "transactional must not be suppressed")

    def test_unknown_intent_defaults_to_commercial_and_is_suppressed(self):
        # A garbage intent must fall back to commercial -> suppression applies.
        result, marks, pubs, smtp_mock = self._run_send_one(_row(intent="garbage"), suppress=True)
        self.assertEqual(result, "suppressed")
        smtp_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
