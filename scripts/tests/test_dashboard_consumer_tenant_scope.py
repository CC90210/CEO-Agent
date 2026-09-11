"""test_dashboard_consumer_tenant_scope.py — the SunBiz box may neither CLAIM
nor SEND OASIS mail, and the reverse.

THE INCIDENT PATH, one layer deeper than PR #72 closed it. #72 put an identity
guard in lib/smtp_send keyed on the postal address in a CASL footer. Codex and
CodeRabbit, reviewing PR #73 independently, found what that cannot see:

  - an INTERNAL dashboard message carries no CASL footer but still renders the
    brand's HTML chrome, so an OASIS internal row authenticated as
    submissions@sunbizfunding.com passed the address guard untouched;
  - the per-user Gmail API path never reaches smtp_send at all;
  - and underneath both, _fetch_queued had NO tenant filter, so the SunBiz VPS
    claimed every tenant's queued mail. In the 30 days to 2026-09-10 the only
    OASIS rows through that queue were the six incident rows — all sent by the
    SunBiz box.

Pinned here: the claim is scoped to the host mailbox's company, a known
tenant's brand comes from the static map (a DB blip cannot rebrand it), and
both transports refuse a mailbox that belongs to the other company — while a
rep's personal Gmail still sends, because refusing it would be a new SunBiz
outage for no leak.

Run:  python -m pytest scripts/tests/test_dashboard_consumer_tenant_scope.py -q
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
from lib import smtp_send as transport  # noqa: E402
from lib import tenant_brand as tb  # noqa: E402

SUNBIZ = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
OASIS_CC = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
OASIS_WEBDEV = "42423fde-be8b-454f-932a-750e8c9b743d"

SUNBIZ_BOX = {"GMAIL_USER": "submissions@sunbizfunding.com", "GMAIL_APP_PASSWORD": "app-pw"}


def _row(tenant_id: str, intent: str = "commercial", acted_by: str | None = None) -> dict:
    md: dict = {"status": "queued", "intent": intent}
    if acted_by:
        md["acted_by_user_id"] = acted_by
    return {
        "id": "row-1",
        "tenant_id": tenant_id,
        "lead_id": "lead-1",
        "subject": "Following up",
        "content": "Hi there, following up on our call.",
        "to_email": "owner@somebusiness.example",  # reserved test domain
        "metadata": md,
    }


class TestTheCompanyLine(unittest.TestCase):
    def test_every_sending_brand_has_a_company(self):
        for brand in tb.BRAND_SENDING_DOMAIN:
            self.assertIn(brand, tb.BRAND_COMPANY, f"{brand} sends mail but belongs to no company")

    def test_the_company_map_agrees_with_the_transport_entitlements(self):
        # Domains allowed to carry the SAME identification address are one
        # company. If this map and smtp_send disagree, one of them is wrong.
        for address, domains in transport._IDENTITY_ADDRESSES:
            companies = {tb.BRAND_COMPANY[tb.brand_for_mailbox("x@" + d)] for d in domains}
            self.assertEqual(len(companies), 1,
                             f"{address!r} is entitled to {sorted(domains)}, which span {companies}")

    def test_oasis_and_sunbiz_are_different_companies(self):
        self.assertNotEqual(tb.BRAND_COMPANY["oasis"], tb.BRAND_COMPANY["sunbiz"])

    def test_other_company_pairs(self):
        cases = [
            ("oasis", "submissions@sunbizfunding.com", True),    # the incident
            ("sunbiz", "conaugh@oasisai.work", True),            # its mirror
            ("oasis", "ops@bluerisebusinesscapital.com", True),  # Bluerise is SunBiz's side
            ("sunbiz", "submissions@sunbizfunding.com", False),
            ("sunbiz", "ops@bluerisebusinesscapital.com", False),
            ("sunbiz", "rep.personal@gmail.com", False),         # personal Gmail rep
            ("oasis", "conaugh@oasisai.work", False),
            ("oasis", "", False),
        ]
        for brand, mailbox, want in cases:
            with self.subTest(brand=brand, mailbox=mailbox):
                self.assertEqual(tb.mailbox_is_other_company(brand, mailbox)[0], want)


class TestTheClaimIsScoped(unittest.TestCase):
    def test_scope_per_mailbox(self):
        self.assertEqual(tb.tenants_for_mailbox("submissions@sunbizfunding.com"), [SUNBIZ])
        self.assertEqual(tb.tenants_for_mailbox("rep.example@sunbizfunding.com"), [SUNBIZ])
        self.assertEqual(tb.tenants_for_mailbox("ops@bluerisebusinesscapital.com"), [SUNBIZ])
        self.assertEqual(tb.tenants_for_mailbox("conaugh@oasisai.work"),
                         sorted([OASIS_CC, OASIS_WEBDEV]))
        self.assertEqual(tb.tenants_for_mailbox("someone@gmail.com"), [])
        self.assertEqual(tb.tenants_for_mailbox(""), [])

    def test_the_sunbiz_box_claims_only_sunbiz_rows(self):
        with mock.patch.object(dec, "_fetch_queued", return_value=[]) as fetch:
            dec.tick(SUNBIZ_BOX, object())
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs.get("tenant_ids"), [SUNBIZ])

    def test_an_unregistered_host_mailbox_claims_nothing(self):
        with mock.patch.object(dec, "_fetch_queued", return_value=[]) as fetch:
            out = dec.tick({"GMAIL_USER": "someone@unknown.example"}, object())
        fetch.assert_not_called()
        self.assertEqual(out["queued_seen"], 0)

    def test_a_blank_gmail_user_does_not_mask_gmail_address(self):
        # Codex, PR #73: a whitespace-only GMAIL_USER is truthy, so the old
        # `(a or b).strip()` never reached GMAIL_ADDRESS and gave "" — no
        # scope, nothing drained, and no error anywhere.
        env = {"GMAIL_USER": "   ", "GMAIL_ADDRESS": "  Submissions@SunBizFunding.com "}
        with mock.patch.object(dec, "_fetch_queued", return_value=[]) as fetch:
            dec.tick(env, object())
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs.get("tenant_ids"), [SUNBIZ])

    def test_the_scope_reaches_the_query_itself(self):
        # In the QUERY, not a post-filter — a post-filter starves the queue.
        calls: list = []

        class Query:
            data: list = []

            def __getattr__(self, name):
                def step(*args, **kwargs):
                    calls.append((name, args))
                    return self
                return step

        class Client:
            def table(self, name):
                calls.append(("table", (name,)))
                return Query()

        dec._fetch_queued(Client(), tenant_ids=[SUNBIZ])
        self.assertIn(("in_", ("tenant_id", [SUNBIZ])), calls)

    def test_a_known_tenant_is_branded_even_when_the_db_is_down(self):
        class DownDB:
            def table(self, *_a, **_k):
                raise RuntimeError("db unavailable")

        self.assertEqual(dec._brand_for_tenant(DownDB(), SUNBIZ), "sunbiz")
        self.assertEqual(dec._brand_for_tenant(DownDB(), OASIS_CC), "oasis")


class TestSendRefusesTheOtherCompany(unittest.TestCase):
    def _run(self, env, row, *, identity=None):
        marks: list = []
        events: list = []
        smtp_mock = mock.MagicMock(return_value=(True, None))
        api_mock = mock.MagicMock(return_value=(True, None))
        ident = identity or {"mode": "tenant_smtp"}

        def fake_mark(sb, row_id, *, status, error=None, **_kw):
            marks.append((status, error))

        def fake_event(sb, *, event_type, tenant_id, payload):
            events.append((event_type, payload))

        with mock.patch.object(dec, "should_suppress", return_value=False), \
             mock.patch.object(dec, "smtp_send", smtp_mock), \
             mock.patch.object(dec, "_mark_status", fake_mark), \
             mock.patch.object(dec, "_publish_event", fake_event), \
             mock.patch.object(dec, "_resolve_send_identity", lambda sb, tid, uid: ident), \
             mock.patch.object(dec, "_send_via_gmail_api", api_mock), \
             mock.patch.object(dec, "_rep_display_name", return_value=None):
            result = dec._send_one(env, object(), row)
        return result, marks, events, smtp_mock, api_mock

    def _assert_refused(self, result, marks, events):
        self.assertEqual(result, "failed")
        self.assertTrue(any(s == "failed" and "sender-identity guard" in (e or "") for s, e in marks),
                        f"expected a sender-identity refusal, got {marks}")
        self.assertTrue(any(p.get("reason") == "mailbox_is_other_company" for _t, p in events))

    def test_codex_an_internal_oasis_row_on_the_sunbiz_box_is_refused(self):
        # No CASL footer, so smtp_send's address guard would see nothing.
        # It must never get the chance.
        result, marks, events, smtp_mock, _api = self._run(SUNBIZ_BOX, _row(OASIS_CC, intent="internal"))
        self._assert_refused(result, marks, events)
        smtp_mock.assert_not_called()

    def test_a_commercial_oasis_row_on_the_sunbiz_box_is_refused(self):
        result, marks, events, smtp_mock, _api = self._run(SUNBIZ_BOX, _row(OASIS_CC))
        self._assert_refused(result, marks, events)
        smtp_mock.assert_not_called()

    def test_a_sunbiz_row_on_the_sunbiz_box_still_sends(self):
        result, _marks, _events, smtp_mock, _api = self._run(SUNBIZ_BOX, _row(SUNBIZ))
        self.assertEqual(result, "sent")
        smtp_mock.assert_called_once()

    def test_coderabbit_a_rep_mailbox_on_the_other_company_is_refused(self):
        ident = {"mode": "user_oauth",
                 "bundle": {"access_token": "t", "gmail_address": "rep@oasisai.work"}}
        result, marks, events, _smtp, api_mock = self._run(
            SUNBIZ_BOX, _row(SUNBIZ, acted_by="user-1"), identity=ident)
        self._assert_refused(result, marks, events)
        api_mock.assert_not_called()

    def test_a_rep_on_personal_gmail_still_sends(self):
        # Not another company's identity. Refusing it would be a SunBiz outage.
        ident = {"mode": "user_oauth",
                 "bundle": {"access_token": "t", "gmail_address": "rep.personal@gmail.com"}}
        result, _marks, _events, _smtp, api_mock = self._run(
            SUNBIZ_BOX, _row(SUNBIZ, acted_by="user-1"), identity=ident)
        self.assertEqual(result, "sent")
        api_mock.assert_called_once()

    def test_the_send_authenticates_as_the_mailbox_the_claim_was_scoped_by(self):
        # Scope and send must read the same mailbox, or the box claims rows as
        # one company and logs in as another.
        env = {"GMAIL_USER": "   ", "GMAIL_ADDRESS": " Submissions@SunBizFunding.com ",
               "GMAIL_APP_PASSWORD": "app-pw"}
        result, _marks, _events, smtp_mock, _api = self._run(env, _row(SUNBIZ))
        self.assertEqual(result, "sent")
        smtp_mock.assert_called_once()
        self.assertIn("submissions@sunbizfunding.com", repr(smtp_mock.call_args).lower())


class TestAStrandedRowIsStillSeen(unittest.TestCase):
    """The claim is scoped, so a row no running consumer is entitled to — a
    tenant missing from TENANT_BRAND, or OASIS mail while no OASIS consumer
    runs — stays queued. That is safe only while something still SEES it:
    dashboard_email_queue_monitor counts queued rows of every tenant and
    alerts after 15 minutes. Scope that query too and a stranded row becomes
    invisible. (Codex, PR #73.)"""

    def test_the_queue_monitor_counts_queued_rows_of_every_tenant(self):
        import dashboard_email_queue_monitor as monitor

        calls: list = []
        old = "2000-01-01T00:00:00+00:00"
        rows = [{"id": f"r{i}", "created_at": old, "tenant_id": t,
                 "metadata": {"status": "queued"}}
                for i, t in enumerate([SUNBIZ, OASIS_CC, "tenant-in-no-company"])]

        class Query:
            def __getattr__(self, name):
                def step(*args, **_kwargs):
                    calls.append((name, args[0] if args else None))
                    return self
                return step

            def execute(self):
                return type("Result", (), {"data": rows})()

        class Client:
            def table(self, _name):
                return Query()

        fake = type(sys)("supabase")
        fake.create_client = lambda *_a, **_k: Client()
        with mock.patch.dict(sys.modules, {"supabase": fake}):
            count, _oldest = monitor._stale_queued(
                {"BRAVO_SUPABASE_URL": "u", "BRAVO_SUPABASE_SERVICE_ROLE_KEY": "k"})
        self.assertEqual(count, 3, "a queued row of some tenant went uncounted")
        self.assertNotIn("tenant_id", [col for _op, col in calls],
                         "the monitor's stale query is now tenant-scoped")


if __name__ == "__main__":
    unittest.main(verbosity=2)
