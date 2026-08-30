#!/usr/bin/env python3
"""Contract suite for ig_closer — the module that creates a real calendar event,
mails a stranger a Google invite, and pings CC.

WHY THIS FILE EXISTS
    tests/test_ig_dm_closer.py covers the brain and the state DAO. It never
    drives `ig_closer.close()` and its fixture has no `leads` table, so the one
    module in this system with an irreversible outward effect shipped with zero
    coverage. Arming `--book` against that is how a stranger gets an invite to a
    call nobody meant to book.

WHAT EACH SECTION PINS, and the defect behind it:

  1. DRY IS THE DEFAULT. close() without apply=True must leave the database
     byte-identical and call nothing outward. The two primitives underneath it
     have OPPOSITE defaults — `book_discovery_call.book()` requires `apply` to
     be passed at all, while `send_gateway.send()` is LIVE unless dry_run=True —
     so "we forgot a flag" fails safe in one direction and mails a stranger in
     the other. Section 6 pins that asymmetry at the signature level.

  2. ONE CONVERSATION BOOKS AT MOST ONCE. Not because we checked booking_status
     first (a check-then-act pair has a window a cron running every minute will
     find), but because the claim is a compare-and-swap with read-back. The race
     test interleaves a second caller INSIDE the first caller's calendar write,
     which is the exact window that matters.

  3. THE RECIPIENT IS NEVER TAKEN ON TRUST. A display-name form, a second
     address smuggled past a comma, or a non-ASCII homograph must be refused
     BEFORE the claim, so a rejected address costs nothing and leaves nothing.

  4. CLAIMED-FOREVER IS FORBIDDEN. `claim_booking` writes only the status, the
     token and the timestamp — it does NOT set automation_paused or
     handoff_pending. A row stranded at 'claimed' therefore keeps the automation
     ARMED on a prospect who may already have a meeting on CC's calendar, and it
     never enters the handoff queue, so nobody is told to look. Every exception
     path is driven and asserted against that.

     The mirror-image failure is pinned too: a genuinely booked row must NEVER
     be flipped to 'failed'. finalize_booking leaves booking_claim_token in
     place, so a fail path keyed on the token alone would succeed against a good
     booking and manufacture a fake failure.

  5. PARTIAL SUCCESS IS REPORTED AS PARTIAL. Calendar event created + email
     failed is neither a clean success nor a total failure, and the operator
     hears the email status verbatim.

  7. AN ALERT CANNOT BE SILENCED BY ITS OWN SUBJECT. notify() routes on MESSAGE
     CONTENT: a body matching notify._NOT_BRAVO_DOMAIN_RE is DROPPED. A prospect
     whose handle or email address is "phone_lookup" would otherwise suppress
     the alert about themselves. Everything a stranger shaped goes through
     _notify_safe first, and these tests run the real regexes over the real
     rendered body rather than trusting that.

NOTHING IN HERE TOUCHES PRODUCTION. No Google Calendar call, no send_gateway
send, no Zernio call, no Telegram message, no production database. An autouse
fixture replaces every one of those with a stub that raises on contact, so a
test that reaches for a live effect fails instantly and loudly rather than
doing it. The database is a throwaway local libSQL file built from the real
migration DDL, and every state assertion is read back through a SECOND
CONNECTION — a read on the writing connection sees that connection's own open
transaction and proves nothing (this exact trap silently reverted a production
cron change on 2026-08-20).

Run:
    python -m pytest tests/test_ig_closer.py -q
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for _p in (str(REPO_ROOT), str(SCRIPTS), str(SCRIPTS / "integrations")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import book_discovery_call  # noqa: E402
import ig_closer  # noqa: E402  — the module under test, imported for real
import ig_conversation_brain as brain  # noqa: E402
import ig_dm_state as state  # noqa: E402
import notify as notify_module  # noqa: E402
import send_gateway  # noqa: E402

# Captured at import time, BEFORE the autouse fixture replaces these functions
# with refusal stubs. Reading a signature off the stub would pin the stub.
REAL_SEND_SIG = inspect.signature(send_gateway.send)
REAL_BOOK_SIG = inspect.signature(book_discovery_call.book)

MIGRATIONS_DIR = REPO_ROOT / "database" / "turso_migrations"


def _ig_migrations() -> list[Path]:
    """Every migration that shapes instagram_dm_conversations, in order.

    Globbed rather than naming bravo__009 alone. Pinning one file meant the next
    ALTER TABLE — bravo__010 added booked_event_id — left this fixture building a
    table production no longer had, and 20 tests failed with "no such column" on
    a change that was actually correct. A fixture that has to be hand-updated per
    migration will be out of date the moment someone forgets.
    """
    return sorted(
        p for p in MIGRATIONS_DIR.glob("bravo__0*.sql")
        if "instagram_dm" in p.name or "ig_" in p.name
    )

TENANT = state.OASIS_TENANT_ID
CONV_ID = "conv_closer_0001"
PARTICIPANT = "17841400000000009"
ACCOUNT_ID = "699c92828ab8ae478b3ee83a"

MEET_LINK = "https://meet.google.com/tst-abcd-efg"
EVENT_ID = "7k2m9qb4c1d8e5f6g7h8i9j0"
SLOT = {
    "start": "2026-09-01T09:00-04:00",
    "end": "2026-09-01T09:30-04:00",
    "label": "Tue 1 Sep, 9:00 AM",
}
GOOD_EMAIL = "prospect@gmail.com"

# `leads` and `tenants` are NOT in the conversations migration. book_discovery_call
# reads `leads`, and ig_dm_state.ensure_booking_lead writes one, so the bridge is
# only exercised if the table is really here. Column-for-column from
# database/turso_migrations/bravo__000_master_schema.sql.
LEADS_DDL = """
CREATE TABLE IF NOT EXISTS "tenants" (
  "id" TEXT NOT NULL PRIMARY KEY,
  "name" TEXT
);
CREATE TABLE IF NOT EXISTS "leads" (
  "id" TEXT NOT NULL PRIMARY KEY,
  "name" TEXT NOT NULL,
  "email" TEXT,
  "phone" TEXT,
  "company" TEXT,
  "website" TEXT,
  "source" TEXT NOT NULL DEFAULT 'manual',
  "status" TEXT NOT NULL DEFAULT 'new',
  "score" INTEGER NOT NULL DEFAULT 0,
  "tags" TEXT DEFAULT '[]',
  "notes" TEXT,
  "last_contacted_at" TEXT,
  "next_followup_at" TEXT,
  "assigned_to" TEXT DEFAULT 'bravo',
  "created_at" TEXT,
  "updated_at" TEXT,
  "tenant_id" TEXT,
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id") ON DELETE CASCADE
);
"""


# ── fixtures ────────────────────────────────────────────────────────────────

def _ddl_statements() -> list[str]:
    migrations = _ig_migrations()
    assert migrations, f"no instagram_dm migrations found under {MIGRATIONS_DIR}"
    raw = ";".join(re.sub(r"--[^\n]*", "", p.read_text(encoding="utf-8"))
                   for p in migrations) + ";" + LEADS_DDL
    return [s.strip() for s in raw.split(";") if s.strip()]


@pytest.fixture()
def db_path(tmp_path) -> str:
    """A throwaway local libSQL file holding the real DDL and nothing else."""
    from lib.db_turso import TursoDB  # noqa: PLC0415

    path = str(tmp_path / "ig_closer_test.db")
    boot = TursoDB(path, None, "local")
    for stmt in _ddl_statements():
        boot.execute(stmt, allow_unscoped=True, reason="test fixture DDL")
    boot.execute("insert into tenants (id, name) values (?, ?)",
                 (TENANT, "OASIS AI"), allow_unscoped=True, reason="test fixture")
    boot.commit()
    return path


@pytest.fixture()
def db(db_path):
    """The handle the closer runs against.

    Opened AFTER the DDL so TursoDB's constructor discovers both tenant-scoped
    tables; otherwise the scope guard never fires and an unscoped statement in
    the DAO would slip past unnoticed.
    """
    from lib.db_turso import TursoDB  # noqa: PLC0415

    handle = TursoDB(db_path, None, "local")
    assert handle.is_tenant_scoped("instagram_dm_conversations")
    assert handle.is_tenant_scoped("leads"), (
        "leads must be tenant-scoped, otherwise ensure_booking_lead's insert is "
        "never checked for a tenant stamp"
    )
    return handle


def committed_row(db_path: str, row_id: str) -> dict | None:
    """Read the conversation row through a SECOND CONNECTION.

    A read on the writing connection sees that connection's own open
    transaction, so it confirms writes that were never durable. Every state
    assertion in this file goes through here.
    """
    from lib.db_turso import TursoDB  # noqa: PLC0415

    fresh = TursoDB(db_path, None, "local")
    rows = fresh.query(
        "select * from instagram_dm_conversations where tenant_id = ? and id = ?",
        (TENANT, str(row_id)),
    )
    return dict(rows[0]) if rows else None


def committed_leads(db_path: str) -> list[dict]:
    from lib.db_turso import TursoDB  # noqa: PLC0415

    fresh = TursoDB(db_path, None, "local")
    return fresh.query("select * from leads where tenant_id = ?", (TENANT,))


class Boom:
    """A live effect that must never be reached. Records nothing, refuses all."""

    def __init__(self, what: str) -> None:
        self.what = what

    def __call__(self, *args, **kwargs):
        raise AssertionError(
            f"test reached the LIVE {self.what}. This suite must never create a "
            f"calendar event, send an email or a Telegram message, or open the "
            f"production database."
        )


@pytest.fixture(autouse=True)
def no_live_side_effects(monkeypatch):
    """Every outward effect ig_closer can reach, replaced with a refusal."""
    import lib.db_turso as dbt  # noqa: PLC0415

    monkeypatch.setattr(dbt, "get_db", Boom("production Turso database"))
    monkeypatch.setattr(state, "get_db_handle", Boom("production Turso database"))

    # Google Calendar: the orchestration entry point AND the primitives under it,
    # so a refactor that calls free_slots/busy_windows directly is caught too.
    monkeypatch.setattr(book_discovery_call, "book", Boom("calendar booking"))
    monkeypatch.setattr(book_discovery_call, "_run", Boom("google_tool subprocess"))
    monkeypatch.setattr(book_discovery_call, "busy_windows", Boom("real calendar read"))
    monkeypatch.setattr(book_discovery_call, "free_slots", Boom("real calendar read"))

    # Outbound email.
    monkeypatch.setattr(send_gateway, "send", Boom("send_gateway.send"))

    # Telegram. close()'s `notifier` default is bound to notify_result at def
    # time, so patching the name does nothing — the only way to neutralise a
    # test that forgets notifier= is to break the transport underneath it.
    monkeypatch.setattr(notify_module, "notify", Boom("Telegram notify()"))

    # Env probes: resolve_meet_link goes through lib.secret_loader, and
    # verify_calendar_readable shells out to google_tool.
    monkeypatch.setattr(ig_closer, "resolve_meet_link", lambda: MEET_LINK)
    monkeypatch.setattr(ig_closer, "verify_calendar_readable", lambda **k: True)
    monkeypatch.setattr(ig_closer, "choose_slot", lambda **k: dict(SLOT))


# ── stubs ───────────────────────────────────────────────────────────────────

class Calls:
    """Records every call. Never performs one."""

    def __init__(self, result=None, *, raises: BaseException | None = None,
                 side_effect=None) -> None:
        self.result = result
        self.raises = raises
        self.side_effect = side_effect
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if self.side_effect is not None:
            return self.side_effect(*args, **kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result

    @property
    def n(self) -> int:
        return len(self.calls)

    def kwarg(self, name, i: int = 0):
        return self.calls[i]["kwargs"].get(name)


class Notifier(Calls):
    """notify_result's (ok, reason) shape, with the rendered body kept."""

    def __init__(self, result=(True, "sent"), **kw) -> None:
        super().__init__(result, **kw)

    @property
    def bodies(self) -> list[str]:
        return [str(c["args"][0]) if c["args"] else str(c["kwargs"].get("message", ""))
                for c in self.calls]


def calendar_ok(**over) -> dict:
    # `meet_link` is part of book()'s contract as of 2026-08-21: the room is
    # minted per event by the calendar create and read back off the tool output,
    # so the double has to carry it or it models a primitive that no longer
    # exists.
    out = {"ok": True, "applied": True, "lead_id": "x",
           "title": "OASIS AI - discovery call",
           "start": SLOT["start"], "end": SLOT["end"],
           "meet_link": MEET_LINK,
           # book() parses this off google_tool's "Event-Id:" line. It is the
           # meeting's only inverse (`calendar delete <id>`), so the double must
           # carry it or the tests model a primitive that cannot be undone.
           "event_id": EVENT_ID,
           "calendar_output": "Event created: OASIS AI discovery call"}
    out.update(over)
    return out


def sent_ok(**over) -> dict:
    out = {"status": "sent", "reason": "delivered"}
    out.update(over)
    return out


def extracted(**over):
    fields = {"name": "Sam", "email": GOOD_EMAIL, "phone": None,
              "business": "Sam's Shop", "need": "a website", "timeline": "soon"}
    fields.update(over)
    return brain.Extracted(**fields)


def make_row(db, *, stage: str = "qualified", conv_id: str = CONV_ID,
             handle: str = "someprospect", name: str = "Some Prospect",
             **over) -> dict:
    """A conversation row in a closeable state, created through the real DAO."""
    row = state.get_or_create(db, conv={
        "id": conv_id, "participantId": PARTICIPANT, "accountId": ACCOUNT_ID,
        "participantUsername": handle, "participantName": name,
    }, tenant_id=TENANT)
    row = state.set_stage(db, row["id"], stage=stage, tenant_id=TENANT, force=True)
    out = dict(row)
    out.update(over)
    return out


def close(db, row, **kw):
    """close() with the test defaults: explicit tenant, recording notifier."""
    kw.setdefault("extracted", extracted())
    kw.setdefault("tenant_id", TENANT)
    kw.setdefault("notifier", Notifier())
    return ig_closer.close(db, row, **kw)


# ════════════════════════════════════════════════════════════════════════════
# 1. DRY IS THE DEFAULT — apply=True is the only thing that acts
# ════════════════════════════════════════════════════════════════════════════

def test_close_defaults_to_dry_and_performs_no_outward_act(db, db_path):
    """No apply= at all. Every live effect is a Boom, so reaching one fails."""
    row = make_row(db)
    notifier = Notifier()

    result = close(db, row, notifier=notifier)

    assert result.ok is True
    assert result.applied is False, "applied means a real calendar event exists"
    assert result.email_status == "dry_run"
    assert result.slot_start == SLOT["start"]
    # Was `== MEET_LINK`, the shared static room. That assertion encoded the
    # defect: the room is MINTED by the calendar create, which a dry run does
    # not perform, so a dry run has no room to report and saying otherwise named
    # a URL the real booking would not use.
    assert result.meet_link is None
    assert "minted" in (result.email_reason or "")
    assert notifier.n == 0, "a dry run must not ping CC"


def test_dry_run_leaves_the_database_byte_identical(db, db_path):
    """No claim, no lead bridge, no state write of any kind. Read back from a
    second connection, because the writing connection would show us our own
    uncommitted transaction and prove nothing."""
    row = make_row(db)
    before = committed_row(db_path, row["id"])

    result = close(db, row, apply=False)

    after = committed_row(db_path, row["id"])
    assert after == before, "dry mode wrote to the conversation row"
    assert after["booking_status"] == "none"
    assert after["booking_claim_token"] is None
    assert committed_leads(db_path) == [], "dry mode created a bridging lead row"
    assert result.booking_lead_id is None


def test_dry_run_never_calls_the_outward_primitives(db, monkeypatch):
    """Not 'calls them with a dry flag' — does not call them at all."""
    book = Calls(calendar_ok())
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", send)

    close(db, make_row(db))

    assert book.n == 0, "dry mode reached book_discovery_call.book()"
    assert send.n == 0, "dry mode reached send_gateway.send()"


def test_the_cli_only_books_on_the_explicit_apply_flag():
    """--apply is the gate; --dry-run is the explicit form of the default, and
    the two are mutually exclusive so `--apply --dry-run` cannot be ambiguous."""
    parser = ig_closer._build_parser()
    assert parser.parse_args(["close", "--conversation-id", "x"]).apply is False
    assert parser.parse_args(["close", "--conversation-id", "x", "--dry-run"]).apply is False
    assert parser.parse_args(["close", "--conversation-id", "x", "--apply"]).apply is True
    with pytest.raises(SystemExit):
        parser.parse_args(["close", "--conversation-id", "x", "--apply", "--dry-run"])


NON_CLOSEABLE = sorted(set(brain.STAGES) - ig_closer.CLOSEABLE_STAGES)


@pytest.mark.parametrize("stage", NON_CLOSEABLE)
def test_a_conversation_that_never_agreed_to_a_call_is_not_booked(db, db_path, stage,
                                                                  monkeypatch):
    """Derived from the live enum, not a hand-typed list: a stage added to the
    brain without a decision about bookability lands here automatically."""
    assert NON_CLOSEABLE and "disqualified" in NON_CLOSEABLE
    book = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    row = make_row(db, stage=stage)

    result = close(db, row, apply=True)

    assert result.ok is False
    assert result.stage_of_failure == "precondition"
    assert book.n == 0
    assert committed_row(db_path, row["id"])["booking_status"] == "none"


@pytest.mark.parametrize("stage", sorted(ig_closer.CLOSEABLE_STAGES))
def test_both_closeable_stages_really_close(db, db_path, stage, monkeypatch):
    """The negative test above is only meaningful if the positive set works."""
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))
    row = make_row(db, stage=stage)

    result = close(db, row, apply=True)

    assert (result.ok, result.applied) == (True, True)
    assert committed_row(db_path, row["id"])["booking_status"] == "booked"


def test_a_paused_conversation_is_not_booked(db, db_path, monkeypatch):
    book = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    row = make_row(db)
    state.pause(db, row["id"], tenant_id=TENANT)
    row = dict(state.get_by_conversation_id(db, CONV_ID, tenant_id=TENANT))

    result = close(db, row, apply=True)

    assert (result.ok, result.stage_of_failure) == (False, "precondition")
    assert book.n == 0


def test_an_unreadable_calendar_refuses_to_book_rather_than_guessing(db, monkeypatch):
    """busy_windows() returns [] both for an empty week and for a FAILED read.
    CC's calendar is never empty across five weekdays, so [] is evidence the
    read failed and booking on it would double-book him."""
    book = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(ig_closer, "verify_calendar_readable", lambda **k: False)

    result = close(db, make_row(db), apply=True)

    assert (result.ok, result.stage_of_failure) == (False, "calendar_unverified")
    assert book.n == 0


def test_no_slot_means_no_booking(db, monkeypatch):
    book = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(ig_closer, "choose_slot", lambda **k: None)

    result = close(db, make_row(db), apply=True)

    assert (result.ok, result.stage_of_failure) == (False, "no_slots")
    assert book.n == 0


def test_a_booking_that_comes_back_without_a_room_is_a_failure(db, db_path,
                                                              monkeypatch):
    """Rewritten 2026-08-21. It used to assert that an absent GOOGLE_MEET_LINK
    blocked the booking, which pinned the wrong gate on the wrong link: that
    static URL is ONE shared room pasted onto every event ever created, so two
    prospects booked an hour apart could join each other's call. The room is now
    minted per event by the calendar create, and the gate that matters is the
    one on the room that actually came back.

    There is NO fallback to the static link, so this is a failure — and the
    event EXISTS by the time we know, which is why it must be parked and say so.
    """
    send = Calls(sent_ok())
    book = Calls(calendar_ok(meet_link=None))
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", send)
    notifier = Notifier()

    result = close(db, make_row(db), apply=True, notifier=notifier)

    assert (result.ok, result.stage_of_failure) == (False, "meet_link_missing")
    assert result.stage_of_failure in ig_closer.STAGES_OF_FAILURE
    assert result.applied is True, "the calendar event exists; saying otherwise "\
                                   "is what makes an operator retry blind"
    assert send.n == 0, "no confirmation may go out with no room in it"
    after = committed_row(db_path, result.row_id)
    assert after["booking_status"] == "failed"
    assert (after["booking_error"] or "").startswith(ig_closer.CALENDAR_EXISTS_PREFIX)
    assert any("at step meet_link_missing" in b for b in notifier.bodies)


def test_the_confirmation_carries_the_room_that_was_actually_created(db, db_path,
                                                                    monkeypatch):
    """The static room reached the prospect as "Here is the room". It was the
    same URL for everyone, forever."""
    minted = "https://meet.google.com/per-event-room-1"
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(meet_link=minted)))
    monkeypatch.setattr(send_gateway, "send", send)
    monkeypatch.setattr(ig_closer, "resolve_meet_link",
                        Boom("the shared static Meet room"))

    result = close(db, make_row(db), apply=True)

    assert result.ok is True and result.meet_link == minted
    body = send.kwarg("body_text")
    assert minted in body
    assert MEET_LINK not in body, "the shared static room reached a prospect"
    assert ig_closer.TEMPLATE_PROBE_LINK not in body, (
        "the placeholder used to validate the template was sent to a real person"
    )
    assert committed_row(db_path, result.row_id)["booked_meet_link"] == minted


def test_an_interrupt_between_the_claim_and_finalize_parks_the_row(db, db_path,
                                                                  monkeypatch):
    """`except Exception` does not catch KeyboardInterrupt or SystemExit, and
    there is no out-of-process reaper. Ctrl-C during the documented first
    supervised --apply — while book() is blocked in the google_tool subprocess
    for up to 180s — left booking_status='claimed' with automation_paused=0,
    handoff_pending=0 and the stage untouched: invisible to `list --handoffs`,
    permanently un-bookable, and still being auto-replied to."""
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(raises=KeyboardInterrupt()))
    monkeypatch.setattr(send_gateway, "send", Boom("send_gateway.send"))
    notifier = Notifier()
    row = make_row(db)

    with pytest.raises(KeyboardInterrupt):
        close(db, row, apply=True, notifier=notifier)

    after = committed_row(db_path, row["id"])
    assert after["booking_status"] == "failed", (
        f"the row is stranded at {after['booking_status']!r}"
    )
    assert after["handoff_pending"] == 1 and after["automation_paused"] == 1
    assert notifier.n == 1, "nobody was told the booking died mid-flight"


def test_a_stranded_claim_is_discoverable(db, db_path, monkeypatch):
    """A kill -9, a PM2 restart or a cron timeout runs no handler at all, so
    parking cannot be the only answer. booking_claimed_at was written and — I
    grepped the whole repo — read by nothing; list_handoffs filters on
    handoff_pending=1 and there was no list variant for 'claimed'."""
    row = make_row(db)
    assert state.claim_booking(db, row["id"], claim_token="tok-1", tenant_id=TENANT)

    fresh = state.list_stale_claims(db, older_than_minutes=-1, tenant_id=TENANT)

    assert [r["id"] for r in fresh] == [row["id"]]
    assert state.list_handoffs(db, tenant_id=TENANT) == [], (
        "a claimed row is not a handoff; it needs its own queue"
    )


# ════════════════════════════════════════════════════════════════════════════
# 2. ONE CONVERSATION BOOKS AT MOST ONCE
# ════════════════════════════════════════════════════════════════════════════

def test_a_successful_apply_books_exactly_once_and_records_it(db, db_path, monkeypatch):
    book = Calls(calendar_ok())
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", send)
    row = make_row(db)
    notifier = Notifier()

    result = close(db, row, apply=True, notifier=notifier)

    assert (result.ok, result.applied) == (True, True)
    assert result.email_status == "sent"
    assert book.n == 1 and send.n == 1
    after = committed_row(db_path, row["id"])
    assert after["booking_status"] == "booked"
    assert after["booked_meet_link"] == MEET_LINK
    assert after["booking_email_status"] == "sent"
    assert after["automation_paused"] == 1, (
        "a booked conversation must stop being auto-replied to"
    )
    assert len(committed_leads(db_path)) == 1, "exactly one bridging lead row"
    assert notifier.n == 1


def test_a_second_close_on_a_booked_row_is_refused_before_any_outward_act(
        db, db_path, monkeypatch):
    book = Calls(calendar_ok())
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", send)
    row = make_row(db)
    close(db, row, apply=True)

    reread = dict(state.get_by_conversation_id(db, CONV_ID, tenant_id=TENANT))
    second = close(db, reread, apply=True)

    assert second.ok is False
    assert second.stage_of_failure == "precondition"
    assert "booking_status" in (second.error or ""), (
        "the booking_status gate must be the one that fires. finalize_booking "
        "also moves the stage to 'booked', so the stage gate would refuse this "
        "too and mask the removal of the status check entirely"
    )
    assert book.n == 1, "the calendar was written twice for one conversation"
    assert send.n == 1


def test_two_callers_racing_the_claim_produce_exactly_one_calendar_event(
        db, db_path, monkeypatch):
    """The real race, not a sequential re-read.

    Both callers hold the SAME pre-claim snapshot, so both pass the
    booking_status precondition. The second one enters INSIDE the first one's
    calendar write — the exact window a check-then-act pair leaves open and the
    every-minute cron will eventually find. Only the compare-and-swap with
    read-back closes it.
    """
    stale = make_row(db)
    second: dict = {}
    send = Calls(sent_ok())
    monkeypatch.setattr(send_gateway, "send", send)

    def racing_book(compat, lead_id, start, *, apply):
        book.calls.append({"args": (lead_id, start), "kwargs": {"apply": apply}})
        if len(book.calls) == 1:
            second["result"] = close(db, dict(stale), apply=True)
        return calendar_ok()

    book = Calls(side_effect=None)
    book.calls = []
    monkeypatch.setattr(book_discovery_call, "book", racing_book)

    first = close(db, dict(stale), apply=True)

    assert len(book.calls) == 1, (
        "two calendar events for one prospect — the claim did not hold"
    )
    assert first.ok is True and first.applied is True
    loser = second["result"]
    assert loser.ok is False
    assert loser.stage_of_failure == "claim_lost"
    assert loser.applied is False, "the loser must not report a meeting it never made"
    assert send.n == 1, "the loser must not mail a confirmation for the winner's call"
    assert committed_row(db_path, stale["id"])["booking_status"] == "booked"


def test_a_row_another_process_already_claimed_is_refused_at_the_precondition(
        db, db_path, monkeypatch):
    """The booking_status gate, isolated from every gate that overlaps it.

    claim_booking writes ONLY the status, the token and the timestamp — it leaves
    `stage` at 'qualified'. So a claimed row is the one state in which the status
    check is the sole thing standing between a second process and a second
    calendar event; on a 'booked' or 'failed' row the stage gate would refuse it
    anyway and hide the removal of this check.
    """
    book = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    row = make_row(db)
    assert state.claim_booking(db, row["id"], claim_token="someone_elses_token",
                               tenant_id=TENANT)
    reread = dict(state.get_by_conversation_id(db, CONV_ID, tenant_id=TENANT))
    assert reread["stage"] == "qualified", "the stage gate must not be what fires"

    result = close(db, reread, apply=True)

    assert (result.ok, result.stage_of_failure) == (False, "precondition")
    assert "booking_status" in (result.error or "")
    assert book.n == 0
    after = committed_row(db_path, row["id"])
    assert after["booking_claim_token"] == "someone_elses_token", (
        "the refused caller must not have touched the other process's claim"
    )


def test_a_failed_booking_never_decays_back_to_bookable_on_its_own(db, db_path,
                                                                   monkeypatch):
    """'failed' parks until a human runs reset-booking. Retrying a half-finished
    booking is how a prospect gets two invites."""
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(ok=False, applied=False, error="calendar 500")))
    row = make_row(db)
    close(db, row, apply=True)
    assert committed_row(db_path, row["id"])["booking_status"] == "failed"

    book2 = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book2)
    reread = dict(state.get_by_conversation_id(db, CONV_ID, tenant_id=TENANT))
    again = close(db, reread, apply=True)

    assert (again.ok, again.stage_of_failure) == (False, "precondition")
    assert book2.n == 0


# ════════════════════════════════════════════════════════════════════════════
# 3. THE RECIPIENT IS NEVER TAKEN ON TRUST
# ════════════════════════════════════════════════════════════════════════════

BAD_RECIPIENTS = [
    (None, "no address at all"),
    ("", "empty string"),
    ("   ", "whitespace only"),
    ("notanemail", "no @"),
    ("no@tld", "no dot in the domain"),
    ("Sam <sam@gmail.com>", "display-name form"),
    ("a@gmail.com, b@gmail.com", "a second recipient smuggled past a comma"),
    ("a@gmail.com; b@gmail.com", "a second recipient smuggled past a semicolon"),
    ("a@gmail.com\nbcc: b@gmail.com", "header injection via newline"),
    ("a@gmail.com\r\nbcc: b@gmail.com", "header injection via CRLF"),
    ("üser@gmail.com", "non-ASCII local part"),
    ("user@gmaıl.com", "non-ASCII homograph domain"),
    ("a b@gmail.com", "embedded space"),
    ("a" * 250 + "@gmail.com", "longer than 254 characters"),
]


@pytest.mark.parametrize("address,why", BAD_RECIPIENTS,
                         ids=[w.replace(" ", "_") for _, w in BAD_RECIPIENTS])
def test_a_recipient_that_fails_validation_is_never_mailed(db, db_path, monkeypatch,
                                                           address, why):
    book = Calls(calendar_ok())
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", send)
    row = make_row(db)

    result = close(db, row, extracted=extracted(email=address), apply=True)

    assert result.ok is False, f"{why!r} was accepted as a recipient"
    assert result.stage_of_failure == "precondition"
    assert send.n == 0, f"{why!r} reached send_gateway"
    assert book.n == 0, f"{why!r} still created a calendar event"
    after = committed_row(db_path, row["id"])
    assert after["booking_status"] == "none", (
        "a rejected address must cost nothing — the gate runs before the claim"
    )
    assert committed_leads(db_path) == []


@pytest.mark.parametrize("address", ["cc@oasisai.work", "x@OASISAISOLUTIONS.COM",
                                     "y@gmail.com.oasisai.work"])
def test_an_address_on_our_own_perimeter_is_refused(db, db_path, monkeypatch, address):
    """An address inside our perimeter puts whoever controls it in CC's calendar
    with a Meet link. The deny list has one home, in the brain."""
    assert ig_closer._email_domain(address) in brain.DENIED_EMAIL_DOMAINS
    book = Calls(calendar_ok())
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", send)
    row = make_row(db)

    result = close(db, row, extracted=extracted(email=address), apply=True)

    assert (result.ok, result.stage_of_failure) == (False, "denied_domain")
    assert send.n == 0 and book.n == 0
    assert committed_row(db_path, row["id"])["booking_status"] == "none"


def test_the_recipient_gate_rejects_a_trailing_newline_the_regex_would_allow():
    """The one shape _EMAIL_RE alone does NOT stop.

    Python's `$` matches before a single trailing newline, so "addr\\n" satisfies
    the anchored pattern, is pure ASCII and is under 254 characters. Only the
    forbidden-character set rejects it, and a trailing newline on an SMTP
    recipient is the first half of a header injection.

    Tested here rather than through close(), because close() reads the address
    via _field(), which strips first — so the whole-loop test would be measuring
    the strip, not the gate, and would stay green with this check deleted.
    """
    assert ig_closer._EMAIL_RE.match("a@gmail.com\n"), (
        "the regex no longer accepts it, so this test would pass for the wrong "
        "reason; re-derive the case the character set is uniquely responsible for"
    )
    ok, why = ig_closer._valid_recipient("a@gmail.com\n")
    assert ok is False
    assert "separator" in why
    assert ig_closer._valid_recipient("a@gmail.com")[0] is True


def test_the_validated_address_is_the_one_that_gets_mailed(db, monkeypatch):
    """Not the row's column, not a re-derived value — the address that passed
    the gate, lower-cased, and nothing else."""
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", send)

    close(db, make_row(db), extracted=extracted(email="Prospect@Gmail.COM"), apply=True)

    assert send.kwarg("to_email") == "prospect@gmail.com"
    assert send.kwarg("cc_email") is None
    assert send.kwarg("to_phone") is None


def test_a_hostile_display_name_cannot_restructure_the_email_body():
    """The salutation is prospect-supplied text on its way into an outbound
    body. Everything that is not a letter, space, hyphen, apostrophe or period
    is dropped."""
    subject, body = ig_closer.build_confirmation_email(
        first_name="Sam\n\nFrom: CC <cc@oasisai.work>\nClick http://evil.test",
        slot_label=SLOT["label"], slot_start_iso=SLOT["start"], meet_link=MEET_LINK)
    assert body.startswith("Hi Sam,\n")
    assert "evil.test" not in body
    assert "From:" not in body
    assert body.count(MEET_LINK) == 1
    assert "\n" not in subject


# ════════════════════════════════════════════════════════════════════════════
# 4. CLAIMED-FOREVER IS FORBIDDEN
# ════════════════════════════════════════════════════════════════════════════
#
# claim_booking writes ONLY booking_status / booking_claim_token /
# booking_claimed_at. It does NOT set automation_paused or handoff_pending —
# fail_booking is what does. A row stranded at 'claimed' therefore keeps the
# automation ARMED on a prospect who may already have a real meeting on CC's
# calendar, and never reaches the handoff queue, so nobody is told to look.

def _blow_up_in_book(monkeypatch, send):
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(raises=RuntimeError("google_tool exploded")))
    monkeypatch.setattr(send_gateway, "send", send)


def _blow_up_in_send(monkeypatch, send):
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send",
                        Calls(raises=RuntimeError("smtp layer exploded")))


def _blow_up_in_finalize(monkeypatch, send):
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", send)
    monkeypatch.setattr(state, "finalize_booking",
                        Calls(raises=RuntimeError("turso write exploded")))


def _blow_up_in_the_lead_bridge(monkeypatch, send):
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", send)
    monkeypatch.setattr(state, "ensure_booking_lead",
                        Calls(raises=RuntimeError("leads insert exploded")))


# The claim is the boundary, so the two sides have DIFFERENT correct outcomes.
# Before it, nothing has been staked: the row must be left exactly as it was,
# fully retryable, and no alert is owed. After it, this process owns the booking
# and the row must be parked so a human is queued and the automation stops.
POST_CLAIM_BLOWUPS = [
    ("calendar_create", _blow_up_in_book),
    ("confirmation_send", _blow_up_in_send),
    ("state_finalize", _blow_up_in_finalize),
]
PRE_CLAIM_BLOWUPS = [
    ("lead_bridge", _blow_up_in_the_lead_bridge),
]
BLOWUPS = POST_CLAIM_BLOWUPS + PRE_CLAIM_BLOWUPS


@pytest.mark.parametrize("where,inject", BLOWUPS, ids=[w for w, _ in BLOWUPS])
def test_close_never_raises_whatever_explodes(db, monkeypatch, where, inject):
    """close()'s contract is that it returns a CloseResult, always. A raise here
    reaches the poller, which is mid-loop over other live conversations."""
    inject(monkeypatch, Calls(sent_ok()))

    result = close(db, make_row(db), apply=True)

    assert isinstance(result, ig_closer.CloseResult)
    assert result.ok is False
    assert result.stage_of_failure in ig_closer.STAGES_OF_FAILURE
    assert result.error


@pytest.mark.parametrize("where,inject", POST_CLAIM_BLOWUPS,
                         ids=[w for w, _ in POST_CLAIM_BLOWUPS])
def test_an_exception_never_strands_the_row_at_claimed(db, db_path, monkeypatch,
                                                       where, inject):
    inject(monkeypatch, Calls(sent_ok()))
    row = make_row(db)

    close(db, row, apply=True)

    after = committed_row(db_path, row["id"])
    assert after["booking_status"] != "claimed", (
        f"a failure at {where} left the row CLAIMED. claim_booking does not set "
        f"automation_paused or handoff_pending, so this row keeps getting "
        f"auto-replies and never reaches a human."
    )
    assert after["booking_status"] == "failed"
    assert after["automation_paused"] == 1, "the automation must stop on this row"
    assert after["handoff_pending"] == 1, "a human must be queued to look at it"
    assert (after["booking_error"] or "").strip(), (
        "reset_booking's contract is 'check the calendar first' — booking_error "
        "is the only field that can tell the operator what happened"
    )


@pytest.mark.parametrize("where,inject", POST_CLAIM_BLOWUPS,
                         ids=[w for w, _ in POST_CLAIM_BLOWUPS])
def test_an_exception_after_the_claim_reaches_a_human(db, monkeypatch, where, inject):
    inject(monkeypatch, Calls(sent_ok()))
    notifier = Notifier()

    close(db, make_row(db), apply=True, notifier=notifier)

    assert notifier.n == 1, f"a failure at {where} notified nobody"
    assert "Booking failed" in notifier.bodies[0]
    assert where.replace("confirmation_send", "email").replace(
        "state_finalize", "finalize") in notifier.bodies[0], (
        "the alert must name the step that broke; 'unexpected' is the one word "
        "an operator can do nothing with"
    )


@pytest.mark.parametrize("where,inject", PRE_CLAIM_BLOWUPS,
                         ids=[w for w, _ in PRE_CLAIM_BLOWUPS])
def test_an_exception_before_the_claim_leaves_the_row_untouched(
        db, db_path, monkeypatch, where, inject):
    """Nothing was staked yet, so nothing needs unwinding. The row stays exactly
    bookable and no operator cleanup is owed."""
    send = Calls(sent_ok())
    inject(monkeypatch, send)
    row = make_row(db)
    before = committed_row(db_path, row["id"])

    result = close(db, row, apply=True)

    assert result.ok is False
    assert result.applied is False
    assert committed_row(db_path, row["id"]) == before
    assert send.n == 0


@pytest.mark.parametrize("where,inject",
                         [b for b in BLOWUPS if b[0] in ("confirmation_send",
                                                         "state_finalize")],
                         ids=["confirmation_send", "state_finalize"])
def test_a_failure_after_the_calendar_write_says_the_meeting_exists(
        db, db_path, monkeypatch, where, inject):
    """The operator who runs reset-booking has to know an invite is already in
    a stranger's inbox. booking_error is the only channel that carries it."""
    inject(monkeypatch, Calls(sent_ok()))
    row = make_row(db)

    result = close(db, row, apply=True)

    assert result.applied is True, (
        "the calendar event exists; reporting applied=False would be a lie"
    )
    assert "CALENDAR EVENT EXISTS" in (committed_row(db_path, row["id"])["booking_error"] or "")


def test_a_failure_before_the_calendar_write_does_not_claim_a_meeting_exists(
        db, db_path, monkeypatch):
    _blow_up_in_the_lead_bridge(monkeypatch, Calls(sent_ok()))
    row = make_row(db)

    result = close(db, row, apply=True)

    assert result.applied is False
    error = committed_row(db_path, row["id"])["booking_error"] or ""
    assert "CALENDAR EVENT EXISTS" not in error, (
        "claiming a meeting exists when none does sends the operator hunting "
        "through a calendar for an event that was never created"
    )


def test_a_genuinely_booked_row_is_never_flipped_to_failed(db, db_path, monkeypatch):
    """The mirror-image trapdoor, and the reason the fail path must key on
    FINALIZATION rather than on the claim token.

    finalize_booking sets booking_status='booked' but leaves booking_claim_token
    in place, so fail_booking's token-guarded UPDATE would still match a good
    booking. A crash after finalize must not manufacture a fake failure, set
    handoff_pending and move the stage to handed_off on a conversation that
    really is booked.

    Reaching the outer handler AFTER finalize takes care. A notifier that raises
    will not do it — _notify_call catches that — so this test would stay green
    against a fail path keyed on the claim token alone, which is exactly the
    mutation it exists to catch. The injected crash is therefore in the
    post-finalize rendering itself, standing in for any raise between the state
    write and the return.
    """
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))
    real_notify_safe = ig_closer._notify_safe

    def boom_after_finalize(text=None, limit=ig_closer._MAX_NOTIFY_DETAIL_CHARS):
        if text == SLOT["label"]:  # rendered only once finalize_booking returned
            raise RuntimeError("post-finalize rendering exploded")
        return real_notify_safe(text, limit)

    monkeypatch.setattr(ig_closer, "_notify_safe", boom_after_finalize)
    row = make_row(db)

    result = close(db, row, apply=True, notifier=Notifier())

    after = committed_row(db_path, row["id"])
    assert after["booking_status"] == "booked", (
        "the meeting exists and the row was finalized; flipping it to 'failed' "
        "would make an operator cancel a real call"
    )
    assert after["booked_meet_link"] == MEET_LINK
    assert after["handoff_pending"] == 0
    assert result.applied is True


def test_a_notifier_that_raises_does_not_turn_a_real_booking_into_a_failure(
        db, db_path, monkeypatch):
    """The meeting exists and the row says so, both irreversibly, before the
    alert is attempted. A dead Telegram must not make the poller report a
    booking failure for a call that is on CC's calendar."""
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))
    row = make_row(db)

    result = close(db, row, apply=True,
                   notifier=Notifier(raises=RuntimeError("telegram exploded")))

    assert result.ok is True
    assert result.applied is True
    assert result.notify_ok is False
    assert committed_row(db_path, row["id"])["booking_status"] == "booked"


def test_a_stolen_claim_after_the_calendar_write_is_reported_not_overwritten(
        db, db_path, monkeypatch):
    """The one partial failure the operator absolutely must hear about.

    Simulated for real, not by monkeypatching finalize_booking: while the
    confirmation email is going out, another process resets and re-claims the
    row. The genuine finalize_booking then finds a token that is not ours and
    raises BookingClaimLost.
    """
    row = make_row(db)
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))

    def steal_the_claim(**kwargs):
        state.reset_booking(db, row["id"], tenant_id=TENANT)
        assert state.claim_booking(db, row["id"], claim_token="thief_token",
                                   tenant_id=TENANT)
        return sent_ok()

    monkeypatch.setattr(send_gateway, "send", Calls(side_effect=steal_the_claim))
    notifier = Notifier()

    result = close(db, row, apply=True, notifier=notifier)

    assert result.ok is False
    assert result.stage_of_failure == "claim_lost"
    assert result.applied is True, "the calendar event really does exist"
    assert notifier.n == 1 and "Booking failed" in notifier.bodies[0]
    after = committed_row(db_path, row["id"])
    assert after["booking_claim_token"] == "thief_token", (
        "the loser must not stomp the winner's claim"
    )


def test_a_calendar_refusal_is_parked_and_never_mailed(db, db_path, monkeypatch):
    """book() reporting ok=False is not an exception, and must not be treated as
    a success by omission."""
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(ok=False, applied=False,
                                          error="lead not found")))
    monkeypatch.setattr(send_gateway, "send", send)
    row = make_row(db)
    notifier = Notifier()

    result = close(db, row, apply=True, notifier=notifier)

    assert (result.ok, result.applied) == (False, False)
    assert result.stage_of_failure == "calendar_create"
    assert send.n == 0, "no meeting was created, so nothing may be confirmed"
    after = committed_row(db_path, row["id"])
    assert after["booking_status"] == "failed"
    assert after["handoff_pending"] == 1
    assert notifier.n == 1


def test_book_reporting_ok_without_applied_is_not_a_booking(db, db_path, monkeypatch):
    """book() returns {"ok": true, "dry_run": true} when it did nothing. Reading
    `ok` alone would treat that as a real meeting."""
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls({"ok": True, "applied": False, "dry_run": True}))
    monkeypatch.setattr(send_gateway, "send", send)
    row = make_row(db)

    result = close(db, row, apply=True)

    assert result.applied is False
    assert result.stage_of_failure == "calendar_create"
    assert send.n == 0
    assert committed_row(db_path, row["id"])["booking_status"] == "failed"


# ════════════════════════════════════════════════════════════════════════════
# 5. PARTIAL SUCCESS IS REPORTED AS PARTIAL
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status,reason", [
    ("error", "smtp 550 mailbox unavailable"),
    ("suppressed", "recipient is on the suppression list"),
    ("skipped", "cooldown window"),
    ("unknown", ""),
])
def test_a_created_meeting_with_a_failed_email_is_reported_as_exactly_that(
        db, db_path, monkeypatch, status, reason):
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send",
                        Calls({"status": status, "reason": reason}))
    row = make_row(db)
    notifier = Notifier()

    result = close(db, row, apply=True, notifier=notifier)

    # Not a total failure: the Google invite already went out.
    assert result.ok is True
    assert result.applied is True
    assert result.stage_of_failure is None
    # Not a clean success either.
    assert result.email_status == status != "sent"
    after = committed_row(db_path, row["id"])
    assert after["booking_status"] == "booked"
    assert after["booking_email_status"] == status, (
        "the email status has to be durable — the operator repairs this later"
    )
    assert notifier.n == 1
    assert status in notifier.bodies[0], (
        "the operator must be able to see from the alert that the confirmation "
        "did not land"
    )


def test_a_send_that_returns_no_status_is_not_read_as_sent(db, db_path, monkeypatch):
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls({}))

    result = close(db, make_row(db), apply=True)

    assert result.email_status == "unknown"
    assert result.applied is True


# ════════════════════════════════════════════════════════════════════════════
# 6. THE TWO PRIMITIVES HAVE OPPOSITE DEFAULTS
# ════════════════════════════════════════════════════════════════════════════

def test_send_gateway_is_live_by_default_and_book_forces_the_choice():
    """The asymmetry that makes a forgotten flag dangerous in one direction:

      book(db, lead_id, start_iso, apply)   -> `apply` is REQUIRED; forgetting it
                                               is a TypeError, not a booking.
      send_gateway.send(..., dry_run=False) -> LIVE unless told otherwise;
                                               forgetting it mails a stranger.
    """
    assert REAL_SEND_SIG.parameters["dry_run"].default is False, (
        "send_gateway.send stopped being live-by-default; the closer's "
        "dry_run=not apply is written for the live default and this test is the "
        "only thing that would notice the flip"
    )
    assert REAL_BOOK_SIG.parameters["apply"].default is inspect.Parameter.empty


def test_the_closer_passes_dry_run_explicitly_rather_than_relying_on_the_default(
        db, monkeypatch):
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", send)

    close(db, make_row(db), apply=True)

    assert "dry_run" in send.calls[0]["kwargs"], (
        "dry_run must be passed by name on every send; inheriting the live "
        "default is one refactor away from an unintended send"
    )
    assert send.kwarg("dry_run") is False
    assert send.kwarg("intent") == "transactional", (
        "a booking confirmation is not a solicitation; intent='commercial' runs "
        "the draft critic, whose outage would fail closed on a legitimate "
        "confirmation"
    )
    assert send.kwarg("body_html") is None, (
        "send_gateway returns status 'error' for a non-HTML body_html, which is "
        "a silent send failure"
    )
    assert send.kwarg("agent_source") == ig_closer.CLOSER_AGENT_SOURCE
    assert send.kwarg("tenant_id") == TENANT


def test_the_closer_never_calls_send_gateway_at_all_without_apply(db, monkeypatch):
    """Not 'calls it with dry_run=True' — never calls it. A dry run that still
    reaches the send path is one flag-inversion away from a live send."""
    send = Calls(sent_ok())
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", send)

    for kwargs in ({}, {"apply": False}):
        close(db, make_row(db), **kwargs)

    assert send.n == 0


def test_book_is_only_ever_called_with_apply_true_from_the_apply_path(db, monkeypatch):
    """close() normalises both primitives onto its single `apply`. book() is
    reached only after the claim, and then only to really book."""
    book = Calls(calendar_ok())
    monkeypatch.setattr(book_discovery_call, "book", book)
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))

    close(db, make_row(db), apply=True)

    assert book.n == 1
    assert book.calls[0]["kwargs"].get("apply") is True
    assert book.calls[0]["args"][2] == SLOT["start"], "booked at the chosen slot"


def test_the_lead_bridge_is_created_only_under_apply(db, db_path, monkeypatch):
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))
    row = make_row(db)

    close(db, row, apply=False)
    assert committed_leads(db_path) == []

    close(db, row, apply=True)
    leads = committed_leads(db_path)
    assert len(leads) == 1
    assert leads[0]["source"] == "instagram_dm"
    assert leads[0]["tenant_id"] == TENANT, "an unstamped lead row is orphaned"
    assert str(leads[0]["notes"] or "").startswith("Bridged from Instagram DM"), (
        "the bridge row must carry its lineage so the two lead tables can be "
        "reconciled later"
    )


# ════════════════════════════════════════════════════════════════════════════
# 7. AN ALERT CANNOT BE SILENCED BY ITS OWN SUBJECT
# ════════════════════════════════════════════════════════════════════════════
#
# notify() routes on MESSAGE CONTENT. A body matching _NOT_BRAVO_DOMAIN_RE is
# DROPPED outright (it is read as APEX's territory); one matching
# _GROUP_BLOCKED_TERMS_RE is rerouted away from CC. Both patterns contain
# phrases a stranger can simply type into a DM.

SILENCERS = ["phone_lookup", "phone lookup", "texttorrent", "tps lookup"]


@pytest.mark.parametrize("silencer", SILENCERS)
def test_a_prospect_named_after_a_blocked_term_cannot_silence_the_failure_alert(
        db, monkeypatch, silencer):
    assert notify_module._NOT_BRAVO_DOMAIN_RE.search(silencer), (
        f"{silencer!r} is no longer a term notify() drops on; pick another"
    )
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(ok=False, applied=False, error="calendar 500")))
    row = make_row(db, handle=silencer, name=silencer)
    notifier = Notifier()

    close(db, row, apply=True, notifier=notifier)

    assert notifier.n == 1
    body = notifier.bodies[0]
    assert notify_module._NOT_BRAVO_DOMAIN_RE.search(body) is None, (
        f"a prospect whose handle is {silencer!r} silenced the alert about "
        f"themselves: notify() would drop this body entirely"
    )


@pytest.mark.parametrize("silencer", SILENCERS)
def test_a_prospect_whose_email_is_a_blocked_term_cannot_silence_the_booked_alert(
        db, monkeypatch, silencer):
    """The success path interpolates the recipient address into the alert. An
    address is prospect-supplied text like any other."""
    address = f"{silencer.replace(' ', '_')}@gmail.com"
    ok_shape, _ = ig_closer._valid_recipient(address)
    assert ok_shape, "the address must be one the recipient gate accepts"
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))
    notifier = Notifier()

    close(db, make_row(db), extracted=extracted(email=address), apply=True,
          notifier=notifier)

    assert notifier.n == 1
    body = notifier.bodies[0]
    assert notify_module._NOT_BRAVO_DOMAIN_RE.search(body) is None, (
        f"a prospect booking from {address!r} silenced the alert about their own "
        f"booking"
    )


def test_an_error_string_cannot_reroute_the_alert_away_from_cc(db, monkeypatch):
    """'traceback', 'cron failure' and 'stack trace' are all in
    _GROUP_BLOCKED_TERMS_RE and all appear in ordinary error text."""
    hostile = "Traceback (most recent call last): cron failure in stack trace"
    assert notify_module._GROUP_BLOCKED_TERMS_RE.search(hostile)
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(ok=False, applied=False, error=hostile)))
    notifier = Notifier()

    close(db, make_row(db), apply=True, notifier=notifier)

    body = notifier.bodies[0]
    assert notify_module._GROUP_BLOCKED_TERMS_RE.search(body) is None


def test_the_alert_goes_to_a_category_that_actually_delivers(db, monkeypatch):
    """'instagram' is in notify.DEFAULT_BLOCKED and routes to Maven's bot, whose
    token is not in this repo — it would look wired and be dead."""
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))
    notifier = Notifier()

    close(db, make_row(db), apply=True, notifier=notifier)

    assert notifier.kwarg("category") == "lead"
    assert ig_closer.NOTIFY_CATEGORY not in notify_module.DEFAULT_BLOCKED
    assert notifier.kwarg("dedup_key", 0).endswith(":booked")


def test_a_dead_notifier_does_not_mask_the_booking_result(db, db_path, monkeypatch):
    """The failure-alert path is wrapped: a broken Telegram must not turn a
    reported failure into an exception, or hide which step failed."""
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(ok=False, applied=False, error="calendar 500")))
    row = make_row(db)

    result = close(db, row, apply=True, notifier=Notifier(raises=RuntimeError("dead")))

    assert result.stage_of_failure == "calendar_create"
    assert result.notify_ok is False
    assert committed_row(db_path, row["id"])["booking_status"] == "failed"


def test_notify_safe_flattens_truncates_and_masks():
    assert ig_closer._notify_safe("a\nb\tc   d") == "a b c d"
    assert ig_closer._notify_safe(None) == ""
    long = ig_closer._notify_safe("x" * 500, limit=50)
    assert len(long) <= 50
    masked = ig_closer._notify_safe("prospect asked about phone lookup")
    assert notify_module._NOT_BRAVO_DOMAIN_RE.search(masked) is None


def test_no_dm_text_or_raw_traceback_ever_reaches_the_alert(db, monkeypatch):
    """The alert is agent-authored. Quoting the prospect is how the prospect
    writes the alert."""
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(raises=RuntimeError("boom")))
    notifier = Notifier()

    close(db, make_row(db), apply=True, notifier=notifier)

    body = notifier.bodies[0]
    assert "\n" not in body, "a multi-line body is a traceback that got through"
    assert len(body) < 600


# ════════════════════════════════════════════════════════════════════════════
# 8. THE RESULT SHAPE IS A CONTRACT
# ════════════════════════════════════════════════════════════════════════════

GATE_CASES = [
    ("calendar_unverified", "verify_calendar_readable", lambda **k: False),
    ("no_slots", "choose_slot", lambda **k: None),
    # meet_link_missing moved off this list when the room stopped coming from an
    # env var: it can only be detected AFTER the calendar create now, so it has
    # its own test (test_a_booking_that_comes_back_without_a_room_is_a_failure),
    # which asserts membership of STAGES_OF_FAILURE the same way.
]


@pytest.mark.parametrize("expected,attr,stub", GATE_CASES,
                         ids=[c[0] for c in GATE_CASES])
def test_every_failure_names_a_step_from_the_declared_closed_set(
        db, monkeypatch, expected, attr, stub):
    """An operator reads stage_of_failure off a Telegram message. A typo in a
    failure path would name a step that does not exist.

    One gate per test on purpose: patching all three in one function leaves the
    first stub in place for the rest, so every later case would fail at the
    FIRST gate and the test would prove nothing about the others.
    """
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(ig_closer, attr, stub)

    result = close(db, make_row(db), apply=True)

    assert result.stage_of_failure == expected
    assert result.stage_of_failure in ig_closer.STAGES_OF_FAILURE


def test_the_result_serialises_for_the_json_cli(db):
    import json  # noqa: PLC0415

    result = close(db, make_row(db))
    payload = json.loads(json.dumps(result.as_dict()))
    assert payload["applied"] is False
    assert set(payload) == set(ig_closer.CloseResult.__dataclass_fields__)


def test_the_confirmation_template_matches_the_call_the_calendar_creates():
    """The copy promises a duration. The calendar enforces one. Both cannot ship."""
    _, body = ig_closer.build_confirmation_email(
        first_name="Sam", slot_label=SLOT["label"], slot_start_iso=SLOT["start"],
        meet_link=MEET_LINK)
    assert f"{book_discovery_call.CALL_MINUTES} minutes" in body
    assert book_discovery_call.CALL_MINUTES == brain.CALL_MINUTES


def test_the_template_refuses_to_render_without_a_room():
    with pytest.raises(ValueError):
        ig_closer.build_confirmation_email(
            first_name="Sam", slot_label=SLOT["label"],
            slot_start_iso=SLOT["start"], meet_link="")


# ════════════════════════════════════════════════════════════════════════════
# 9. THE CALENDAR IS ONLY HALF-READ, AND THE ROOM IS SHARED
# ════════════════════════════════════════════════════════════════════════════
#
# Captured at import time, before the autouse fixture swaps them for stubs.
REAL_VERIFY = ig_closer.verify_calendar_readable
REAL_BUSY = book_discovery_call.busy_windows
REAL_FREE_SLOTS = book_discovery_call.free_slots
REAL_BOOK = book_discovery_call.book

# What `google_tool.py calendar list` actually prints. The first line is a TIMED
# event: google_tool renders `e['start']['dateTime']` first (google_tool.py:325),
# so the field is a full ISO stamp with a `T`, not a bare date.
CALENDAR_TEXT_OUTPUT = """  2026-09-02T14:00:00-04:00  Client call
  2026-09-03  Conference (all day)
"""

CALENDAR_JSON_OUTPUT = """[
  {"summary": "Client call",
   "start": {"dateTime": "2026-09-02T14:00:00-04:00"},
   "end":   {"dateTime": "2026-09-02T15:00:00-04:00"}},
  {"summary": "Conference (all day)",
   "start": {"date": "2026-09-03"},
   "end":   {"date": "2026-09-04"}}
]"""


def _calendar_reader(rc: int = 0, *, text=CALENDAR_TEXT_OUTPUT,
                     payload=CALENDAR_JSON_OUTPUT, err: str = ""):
    """Stand in for google_tool, honouring --json exactly as the real tool does."""
    def _run(args, timeout=120):
        assert args[:2] == ["calendar", "list"], args
        if rc != 0:
            return rc, "", err or "auth expired"
        return 0, (payload if "--json" in args else text), ""
    return _run


def test_a_timed_meeting_is_seen_by_the_clash_check(monkeypatch):
    """busy_windows' parser was `\\s*(\\d{4}-\\d{2}-\\d{2})\\s+(.*)`, which needs
    whitespace after the date and gets `T`. Every TIMED event — i.e. every real
    meeting — hit `continue`, so the clash check that free_slots() and
    ig_closer.close() depend on only ever saw all-day entries."""
    monkeypatch.setattr(book_discovery_call, "_run", _calendar_reader())

    busy = REAL_BUSY(days=30)
    timed = [(s, e) for s, e in busy if s.hour == 14 and s.day == 2]

    assert timed, (
        f"the 14:00 client call is invisible to the clash check: {busy}"
    )
    start, end = timed[0]
    assert end.hour == 15, "a timed event must block its own window, not the day"


def test_an_all_day_entry_still_blocks_the_whole_day(monkeypatch):
    """The conservative reading of an untimed entry is unchanged."""
    monkeypatch.setattr(book_discovery_call, "_run", _calendar_reader())

    allday = [(s, e) for s, e in REAL_BUSY(days=30) if s.day == 3]
    assert allday, "the all-day entry disappeared"
    start, end = allday[0]
    assert (start.hour, end.hour) == (0, 23)


def test_a_slot_on_top_of_a_timed_meeting_is_never_offered(monkeypatch):
    """The end of the chain: choose_slot() returns slots[0], close() books it,
    google_tool inserts it with sendUpdates:'all'. A prospect was mailed an
    invite on top of CC's existing client call."""
    monkeypatch.setattr(book_discovery_call, "_run", _calendar_reader())
    # free_slots reads busy_windows off the module, which the autouse fixture
    # replaced with a refusal. Put the REAL one back for this test only.
    monkeypatch.setattr(book_discovery_call, "busy_windows", REAL_BUSY)

    class _FixedNow(book_discovery_call.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 1, 8, 0, tzinfo=tz or book_discovery_call.TZ)

    monkeypatch.setattr(book_discovery_call, "datetime", _FixedNow)
    slots = REAL_FREE_SLOTS(days=3, limit=40)
    clashing = [s for s in slots if s["start"].startswith("2026-09-02T14:")]

    assert slots, "the fixture should still leave plenty of free time"
    assert not clashing, f"offered a slot inside CC's 14:00 client call: {clashing}"


def test_an_unreadable_calendar_is_not_the_same_fact_as_an_empty_one(monkeypatch):
    """verify_calendar_readable() inferred "the calendar was read" from
    `bool(busy_windows(days))`, but busy_windows returns [] whenever the horizon
    holds no all-day events — the NORMAL state of a working calendar. The gate
    therefore read a fully-booked week as unreadable and a single all-day entry
    as proof the timed calendar was read. Neither inference is sound."""
    monkeypatch.setattr(book_discovery_call, "_run", _calendar_reader(rc=1))
    assert REAL_VERIFY() is False, "a failed calendar read must fail closed"

    monkeypatch.setattr(
        book_discovery_call, "_run",
        _calendar_reader(text="", payload="[]"))
    assert REAL_VERIFY() is True, (
        "a calendar that was READ and happens to hold no all-day entries is not "
        "an unreadable calendar; refusing here means booking never works"
    )


def test_the_readability_gate_does_not_infer_from_an_empty_list():
    """Source pin: the gate must read the READ STATUS, not the row count."""
    src = inspect.getsource(REAL_VERIFY)
    assert "bool(book_discovery_call.busy_windows" not in src, (
        "the gate is back to inferring readability from a non-empty result"
    )


# ── the shared Meet room ────────────────────────────────────────────────────

MEET_MINTED = "https://meet.google.com/xyz-mint-001"

CREATE_OUTPUT = f"""Event created: OASIS AI - discovery call: Sam's Shop
  When: 2026-09-01T09:00:00-04:00
  Link: https://www.google.com/calendar/event?eid=abc
  Meet: {MEET_MINTED}
  Meet-Scope: per-event (minted by Google for this event)
  Event-Id: evt_123
"""


class _FakeTable:
    def __init__(self, sink): self.sink = sink
    def insert(self, values): self.sink.append(values); return self
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return type("R", (), {"data": []})()


class _FakeDb:
    def __init__(self): self.inserted: list[dict] = []
    def table(self, name): return _FakeTable(self.inserted)


@pytest.fixture()
def booking_env(monkeypatch, tmp_path):
    """book() with the calendar, the CRM read and the brief file all stubbed."""
    calls: list[list[str]] = []

    def _run(args, timeout=120):
        calls.append(list(args))
        return 0, CREATE_OUTPUT, ""

    monkeypatch.setattr(book_discovery_call, "_run", _run)
    monkeypatch.setattr(book_discovery_call, "load_lead",
                        lambda db, lead_id: ({"id": lead_id, "name": "Sam",
                                              "email": GOOD_EMAIL,
                                              "company": "Sam's Shop",
                                              "tenant_id": TENANT}, None))
    # The brief is a real file write into the repo. Stubbed rather than
    # redirected, because book() reports it as a repo-relative path.
    monkeypatch.setattr(
        book_discovery_call, "write_brief",
        lambda lead_id, body: book_discovery_call.BRIEF_DIR / f"{lead_id}.md")
    assert not (tmp_path / "briefs").exists()
    return calls


def test_the_booking_mints_its_own_meet_room(booking_env):
    """`--meet` fills conferenceData from the ONE static GOOGLE_MEET_LINK, so
    every event ever created carries the same URL. Prospect A can join prospect
    B's discovery call, or any future OASIS call, from an email they never
    deleted."""
    result = REAL_BOOK(_FakeDb(), "lead-1", "2026-09-01T09:00", apply=True)
    args = booking_env[0]

    assert "--meet-per-event" in args, f"still pasting the shared room: {args}"
    assert "--meet" not in args, "the legacy static-room flag is still passed"
    assert "--meet-request-id" in args, (
        "without an idempotency key a retried booking mints a SECOND room"
    )
    assert result["ok"] is True and result["applied"] is True
    assert result["meet_link"] == MEET_MINTED, (
        "the room that was actually created has to come back to the caller"
    )


def test_the_meet_request_id_is_stable_per_booking_and_differs_across_them(booking_env):
    """Google treats requestId as the idempotency key: the same id replayed
    returns the existing conference instead of minting a second room."""
    REAL_BOOK(_FakeDb(), "lead-1", "2026-09-01T09:00", apply=True)
    REAL_BOOK(_FakeDb(), "lead-1", "2026-09-01T09:00", apply=True)
    REAL_BOOK(_FakeDb(), "lead-2", "2026-09-01T09:00", apply=True)

    ids = [a[a.index("--meet-request-id") + 1] for a in booking_env]
    assert ids[0] == ids[1], "a retry of the same booking must reuse its key"
    assert ids[0] != ids[2], "two prospects must not share an idempotency key"
    assert all(len(i) <= 64 for i in ids), "Google's requestId limit is 64 chars"


def test_an_event_created_without_a_room_is_a_failure_not_a_fallback(booking_env,
                                                                    monkeypatch):
    """google_tool exits 3 when the event EXISTS but Google minted no room, and
    deliberately refuses to substitute the static link. book() must carry that
    through instead of reporting a clean booking."""
    monkeypatch.setattr(book_discovery_call, "_run",
                        lambda args, timeout=120: (3, '{"ok": false, '
                                                   '"event_created": true, '
                                                   '"event_id": "evt_9"}',
                                                   "EVENT CREATED BUT IT HAS NO "
                                                   "PER-EVENT MEET ROOM"))
    result = REAL_BOOK(_FakeDb(), "lead-1", "2026-09-01T09:00", apply=True)

    assert result["ok"] is False
    assert result.get("meet_link") in (None, ""), "no silent fallback to the shared room"
    assert "evt_9" in str(result.get("error")), (
        "the operator needs the event id to cancel the event that DOES exist"
    )


def test_a_booked_meeting_stores_the_id_that_can_cancel_it(db, db_path, monkeypatch):
    """Creating the event already mailed the invite (sendUpdates:"all").

    The only way back is `google_tool.py calendar delete <event_id>`, and that is
    reachable only while the id is persisted. book() used to keep out[:300] of
    human-readable stdout and throw the id away, leaving a real meeting on CC's
    calendar that no code could find. An action with no inverse is a trapdoor.
    """
    monkeypatch.setattr(book_discovery_call, "book", Calls(calendar_ok()))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))

    result = close(db, make_row(db), apply=True)

    assert result.ok is True
    row = committed_row(db_path, result.row_id)
    assert row["booking_status"] == "booked"
    assert row["booked_event_id"] == EVENT_ID, (
        "the booked meeting has no cancellable id — the invite is in a stranger's "
        "inbox and nothing can withdraw it"
    )


def test_a_booking_without_an_event_id_stores_null_not_a_fake_one(db, db_path,
                                                                  monkeypatch):
    """The legacy static-room path prints no Event-Id line.

    A NULL is honest; an invented id would make `calendar delete` fail against a
    real event while reporting that a cancel was attempted.
    """
    monkeypatch.setattr(book_discovery_call, "book",
                        Calls(calendar_ok(event_id=None)))
    monkeypatch.setattr(send_gateway, "send", Calls(sent_ok()))

    result = close(db, make_row(db), apply=True)

    assert result.ok is True
    assert committed_row(db_path, result.row_id)["booked_event_id"] is None
