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

SUNBIZ_BOX = {"GMAIL_USER": "submissions@sunbizfunding.com",
              "GMAIL_APP_PASSWORD": str(mock.sentinel.gmail_app_password)}


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
               "GMAIL_APP_PASSWORD": str(mock.sentinel.gmail_app_password)}
        result, _marks, _events, smtp_mock, _api = self._run(env, _row(SUNBIZ))
        self.assertEqual(result, "sent")
        smtp_mock.assert_called_once()
        # args[0] is the account smtp_send() logs in as. The MIME message also
        # carries the address in its From header, so matching the whole call
        # would pass even if the login were a different mailbox. (CodeRabbit)
        self.assertEqual(smtp_mock.call_args.args[0], "Submissions@SunBizFunding.com")


class TestEachCompanyWatchesOnlyItsOwnQueue(unittest.TestCase):
    """A box serves ONE company: the one its host mailbox belongs to. Its
    consumer claims only that company's rows, and its queue monitor watches
    only that company's rows, names that company and alerts only that
    company's channel. It never reads, counts or reports another company's
    queue. (CC, 2026-09-11: an earlier version of this monitor counted every
    tenant's rows, so a stuck OASIS email would have alerted SunBiz's channel.)"""

    def _stale_query(self, env):
        import dashboard_email_queue_monitor as monitor

        calls: list = []

        class Query:
            def __getattr__(self, name):
                def step(*args, **_kwargs):
                    calls.append((name, args))
                    return self
                return step

            def execute(self):
                return type("Result", (), {"data": []})()

        fake = type(sys)("supabase")
        fake.create_client = lambda *_a, **_k: type("Client", (), {"table": lambda _s, _n: Query()})()
        store: dict = {}
        with mock.patch.dict(sys.modules, {"supabase": fake}), \
             mock.patch.object(monitor, "_consumer_online", return_value=True), \
             mock.patch.object(monitor, "_read_state", side_effect=lambda: dict(store)), \
             mock.patch.object(monitor, "_write_state", side_effect=store.update), \
             mock.patch.object(monitor, "_telegram", return_value=True):
            result = monitor.check(dict(env, BRAVO_SUPABASE_URL=str(mock.sentinel.db_url),
                                        BRAVO_SUPABASE_SERVICE_ROLE_KEY=str(mock.sentinel.service_role_key)))
        scopes = [args[1] for name, args in calls if name == "in_" and args and args[0] == "tenant_id"]
        return result, scopes

    def test_the_sunbiz_box_watches_only_sunbiz_rows(self):
        result, scopes = self._stale_query(SUNBIZ_BOX)
        self.assertEqual(scopes, [[SUNBIZ]], "the SunBiz monitor's query was not scoped to SunBiz")
        self.assertEqual(result["company"], "sunbiz")

    def test_an_oasis_box_watches_only_oasis_rows(self):
        result, scopes = self._stale_query({"GMAIL_USER": "conaugh@oasisai.work"})
        self.assertEqual(scopes, [sorted([OASIS_CC, OASIS_WEBDEV])],
                         "the OASIS monitor's query was not scoped to OASIS")
        self.assertEqual(result["company"], "oasis")

    def test_a_box_whose_mailbox_belongs_to_no_company_watches_nothing_and_says_so(self):
        result, scopes = self._stale_query({"GMAIL_USER": "someone@unknown.example"})
        self.assertEqual(scopes, [], "a box of no company queried the queue")
        self.assertTrue(any("no registered company" in p for p in result["problems"]))

    def test_each_company_alerts_only_its_own_channel_and_names_itself(self):
        import dashboard_email_queue_monitor as monitor

        env: dict = {}
        for company, (tok_key, chat_key) in monitor._ALERT_CHANNEL_KEYS.items():
            env[tok_key] = f"token-{company}"
            env[chat_key] = f"chat-{company}"
        for company, mailbox in (("sunbiz", "submissions@sunbizfunding.com"),
                                 ("oasis", "conaugh@oasisai.work")):
            if company not in monitor._ALERT_CHANNEL_KEYS:
                continue
            posts: list = []

            def fake_post(url, json=None, timeout=None):  # noqa: A002
                posts.append((url, json))
                return type("R", (), {"json": lambda _s: {"ok": True}, "text": "ok"})()

            store: dict = {}
            with self.subTest(company=company), \
                 mock.patch.object(monitor.requests, "post", side_effect=fake_post), \
                 mock.patch.object(monitor, "_consumer_online", return_value=True), \
                 mock.patch.object(monitor, "_stale_queued", return_value=(2, "2026-09-11T00:00:00+00:00")), \
                 mock.patch.object(monitor, "_read_state", side_effect=lambda: dict(store)), \
                 mock.patch.object(monitor, "_write_state", side_effect=store.update):
                monitor.check(dict(env, GMAIL_USER=mailbox))
                self.assertEqual(len(posts), 1)
                url, body = posts[0]
                self.assertIn(f"token-{company}", url, f"the {company} monitor used another company's bot")
                self.assertEqual(body["chat_id"], f"chat-{company}")
                for other in (c for c in monitor._ALERT_CHANNEL_KEYS if c != company):
                    self.assertNotIn(f"token-{other}", url)
                label = monitor.COMPANY_DISPLAY_NAME[company]
                self.assertTrue(body["text"].startswith(f"⚠️ {label} outbound stalled"),
                                f"the {company} alert does not name its own company: {body['text'][:60]!r}")

    def test_oasis_never_alerts_through_the_sunbiz_channel(self):
        import dashboard_email_queue_monitor as monitor

        for key in monitor._ALERT_CHANNEL_KEYS.get("oasis", ()):
            self.assertNotIn("EZRA", key.upper(), "OASIS alerts must never use SunBiz's EZRA channel")
        self.assertNotEqual(monitor._ALERT_CHANNEL_KEYS.get("oasis"), monitor._ALERT_CHANNEL_KEYS["sunbiz"])

    def test_a_failed_alert_is_retried_not_put_on_cooldown(self):
        # Codex, PR #73: check() recorded last_alert_ts even when Telegram
        # refused, timed out or had no credentials, so the one alert for a
        # stalled queue could fail and then be suppressed for an hour. The
        # guarantee above is only as good as that delivery.
        import dashboard_email_queue_monitor as monitor

        store: dict = {}
        sent: list = []
        outcomes = iter([False, True])

        def fake_telegram(_env, _company, _text):
            ok = next(outcomes)
            sent.append(ok)
            return ok

        def write_state(state):
            store.clear()
            store.update(state)

        with mock.patch.object(monitor, "_consumer_online", return_value=True), \
             mock.patch.object(monitor, "_stale_queued",
                               return_value=(1, "2026-09-10T00:00:00+00:00")), \
             mock.patch.object(monitor, "_read_state", side_effect=lambda: dict(store)), \
             mock.patch.object(monitor, "_write_state", side_effect=write_state), \
             mock.patch.object(monitor, "_telegram", side_effect=fake_telegram):
            first = monitor.check(SUNBIZ_BOX)
            self.assertFalse(first["alerted"], "an undelivered alert was reported as sent")
            self.assertNotIn("last_alert_ts", store, "a failed alert started the cooldown")
            second = monitor.check(SUNBIZ_BOX)
        self.assertEqual(sent, [False, True], "the failed alert was not retried on the next check")
        self.assertTrue(second["alerted"])
        self.assertIn("last_alert_ts", store, "a delivered alert must start the cooldown")

    def test_the_monitor_reads_the_database_the_consumer_reads(self):
        # On the SunBiz VPS neither daemon holds a database key in its process
        # env (read from /proc, 2026-09-10) and the env file holds none either:
        # the consumer gets Turso's compatibility values from lib/secret_loader.
        # The monitor parsed the file by hand, so _stale_queued returned -1 on
        # every check and the stuck-row alert could not fire. This models that
        # host: no env file, nothing in the process env, only the loader.
        import os
        import dashboard_email_queue_monitor as monitor

        loader = type(sys)("lib.secret_loader")
        loader.SecretLoaderRefused = type("SecretLoaderRefused", (Exception,), {})
        loader.load_env = lambda: {
            "BRAVO_SUPABASE_URL": "https://turso.compat",
            "BRAVO_SUPABASE_SERVICE_ROLE_KEY": str(mock.sentinel.compat_key),
        }
        rows = [{"id": "r1", "created_at": "2000-01-01T00:00:00+00:00", "tenant_id": SUNBIZ,
                 "metadata": {"status": "queued"}}]

        class Query:
            def __getattr__(self, _name):
                return lambda *_a, **_k: self

            def execute(self):
                return type("Result", (), {"data": rows})()

        db = type(sys)("supabase")
        db.create_client = lambda *_a, **_k: type("Client", (), {"table": lambda _s, _n: Query()})()
        with mock.patch.object(monitor, "PROJECT_ROOT", Path(__file__).parent / "_no_such_root_"), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.dict(sys.modules, {"lib.secret_loader": loader, "supabase": db}):
            count, _oldest = monitor._stale_queued(monitor._load_env(), [SUNBIZ])
        self.assertEqual(count, 1, "the monitor could not read the queue the consumer drains")

    def test_an_unreadable_queue_alerts_after_three_checks_not_one(self):
        # -1 used to read as "no stuck rows". Now it is a problem, but only after
        # three unreadable checks in a row, so one DB blip does not page the
        # client's ops channel (Codex). A good read resets the count.
        import dashboard_email_queue_monitor as monitor

        store: dict = {}
        sent: list = []
        reads = iter([(-1, None), (-1, None), (-1, None), (0, None), (-1, None)])

        def fake_telegram(_env, _company, text):
            sent.append(text)
            return True

        def write_state(state):
            store.clear()
            store.update(state)

        with mock.patch.object(monitor, "_consumer_online", return_value=True), \
             mock.patch.object(monitor, "_stale_queued", side_effect=lambda _env, _scope: next(reads)), \
             mock.patch.object(monitor, "_read_state", side_effect=lambda: dict(store)), \
             mock.patch.object(monitor, "_write_state", side_effect=write_state), \
             mock.patch.object(monitor, "_telegram", side_effect=fake_telegram):
            results = [monitor.check(SUNBIZ_BOX) for _ in range(5)]
        self.assertEqual(results[0]["problems"], [], "one unreadable check paged")
        self.assertEqual(results[1]["problems"], [], "two unreadable checks paged")
        self.assertTrue(results[2]["problems"], "three unreadable checks in a row raised nothing")
        self.assertIn("cannot read", sent[0])
        self.assertEqual(results[3]["problems"], [])
        self.assertEqual(results[4]["problems"], [], "a good read did not reset the count")

    def test_on_linux_the_monitor_sees_this_checkouts_consumer_and_nothing_else(self):
        # fleet_watchdog reads the process table through WMI only; on the Linux
        # VPS it saw nothing, so the monitor could never report the consumer
        # down. The /proc reader must not be fooled either (Codex): a grep,
        # another checkout's consumer, or a zombie with the right path is not it.
        import tempfile
        import dashboard_email_queue_monitor as monitor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ceo-agent"
            (root / "scripts").mkdir(parents=True)
            real = str((root / "scripts" / "dashboard_email_consumer.py").resolve())
            other = str((Path(tmp) / "other-checkout" / "scripts" / "dashboard_email_consumer.py").resolve())
            proc = Path(tmp) / "proc"

            def process(pid, state, *argv):
                (proc / pid).mkdir(parents=True)
                (proc / pid / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
                (proc / pid / "stat").write_text(f"{pid} (python) {state} 1 1 1")

            process("201", "S", "/usr/bin/grep", "dashboard_email_consumer.py")
            process("202", "S", "/srv/.venv/bin/python", other, "loop")
            process("203", "Z", "/srv/.venv/bin/python", real, "loop")
            with mock.patch.object(monitor, "_IS_WINDOWS", False), \
                 mock.patch.object(monitor, "_PROC_ROOT", proc), \
                 mock.patch.object(monitor, "PROJECT_ROOT", root):
                self.assertIs(monitor._consumer_online(), False,
                              "a grep, another checkout or a zombie read as the consumer")
                process("204", "S", "/srv/.venv/bin/python", real, "loop")
                self.assertIs(monitor._consumer_online(), True, "the running consumer read as down")

    def test_an_unreadable_process_makes_liveness_unknown_not_down(self):
        # A process whose command line cannot be read might be the consumer, so
        # the honest answer is "unknown", which never pages, not "down". A
        # process that exits mid-scan is simply skipped. (CodeRabbit, PR #73.)
        import tempfile
        import dashboard_email_queue_monitor as monitor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ceo-agent"
            (root / "scripts").mkdir(parents=True)
            proc = Path(tmp) / "proc"
            for pid in ("301", "302"):
                (proc / pid).mkdir(parents=True)
                (proc / pid / "cmdline").write_bytes(b"/usr/bin/sleep\0100\0")
                (proc / pid / "stat").write_text(f"{pid} (sleep) S 1 1 1")
            real_read = Path.read_bytes

            def read_bytes(path):
                if path.parent.name == "302":
                    raise PermissionError("denied")
                return real_read(path)

            with mock.patch.object(monitor, "_IS_WINDOWS", False), \
                 mock.patch.object(monitor, "_PROC_ROOT", proc), \
                 mock.patch.object(monitor, "PROJECT_ROOT", root):
                self.assertIs(monitor._consumer_online(), False)
                with mock.patch.object(Path, "read_bytes", read_bytes):
                    self.assertIsNone(monitor._consumer_online(),
                                      "an unreadable process read as a definite 'down'")

    def test_a_secret_loader_refusal_is_not_routed_around(self):
        # A refusal (interactive shell, caller under tmp/) is the loader's
        # policy. Falling back to a direct read of the env file would bypass
        # it, so it must propagate. (CodeRabbit, PR #73.)
        import dashboard_email_queue_monitor as monitor

        refused = type("SecretLoaderRefused", (Exception,), {})
        loader = type(sys)("lib.secret_loader")
        loader.SecretLoaderRefused = refused

        def refuse():
            raise refused("refusing to load secrets from an interactive shell")

        loader.load_env = refuse
        with mock.patch.dict(sys.modules, {"lib.secret_loader": loader}):
            with self.assertRaises(refused):
                monitor._load_env()


if __name__ == "__main__":
    unittest.main(verbosity=2)
