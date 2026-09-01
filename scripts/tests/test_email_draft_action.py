"""Tests for email_draft_action — the Telegram Approve/Reject path.

THE PROPERTY WORTH PROTECTING: there is no unsend. A double-tap, a Telegram
retry, or two people on the same account tapping the same button must produce
exactly one email. Everything else here is in service of that.

The DB is faked rather than mocked loosely: the fake records the exact filter
chain each call makes, so a test cannot pass by accident when the production
code stops applying the compare-and-set predicate that makes the claim atomic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "scripts" / "integrations"))

import email_draft_action as eda  # noqa: E402


# --- fake DB ---------------------------------------------------------------

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table, mode, payload=None):
        self.table = table
        self.mode = mode
        self.payload = payload
        self.filters: list[tuple[str, str]] = []

    def select(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def eq(self, col, val):
        self.filters.append((col, str(val)))
        return self

    def execute(self):
        if self.mode == "select":
            rows = [r for r in self.table.rows
                    if all(str(r.get(c)) == v for c, v in self.filters if c == "id")]
            return _Result(rows)
        # update: honour EVERY filter, including the metadata->>awaiting_approval
        # compare-and-set. This is the whole point of the fake.
        matched = []
        for r in self.table.rows:
            ok = True
            for col, val in self.filters:
                if col == "id":
                    ok = ok and str(r.get("id")) == val
                elif col == "metadata->>awaiting_approval":
                    # Turso stores metadata as TEXT and the Supabase shim hands
                    # back a dict; the real `->>` operator reads both. The fake
                    # has to as well, or a JSON-string row would never match the
                    # claim predicate and the test would be exercising a
                    # different code path than production.
                    current = r.get("metadata") or {}
                    if isinstance(current, str):
                        current = json.loads(current) if current.strip() else {}
                    ok = ok and json.dumps(current.get("awaiting_approval")) == val
                else:
                    ok = ok and str(r.get(col)) == val
            if ok:
                matched.append(r)
        for r in matched:
            r.update(self.payload)
        return _Result(matched)


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_k):
        return _Query(self, "select")

    def update(self, payload):
        return _Query(self, "update", payload)


class FakeDB:
    def __init__(self, rows):
        self._t = _Table(rows)

    def table(self, _name):
        return self._t


def _draft_row(**over):
    row = {
        "id": "11111111-2222-3333-4444-555555555555",
        "type": "email_draft_pending",
        "subject": "Re: Twilio Business Profile",
        "content": "Got the notice on Bundle BU7672...",
        "tenant_id": "tenant-a",
        "metadata": {
            "awaiting_approval": True,
            "from_identity": "trusthub-verify@twilio.com",
            "rfc_message_id": "<abc@twilio.com>",
            "category": "financial_legal",
        },
    }
    row.update(over)
    return row


@pytest.fixture
def sent(monkeypatch):
    """Capture every send_gateway.send call."""
    calls = []

    def _fake_send(**kwargs):
        calls.append(kwargs)
        return {"status": "sent", "interaction_id": "int-1"}

    mod = type(sys)("send_gateway")
    mod.send = _fake_send
    monkeypatch.setitem(sys.modules, "send_gateway", mod)
    return calls


# --- the exactly-once property ---------------------------------------------

def test_approve_sends_once_and_marks_the_row(sent):
    row = _draft_row()
    db = FakeDB([row])
    out = eda.cmd_approve(row["id"], db=db)
    assert out["ok"] is True, out
    assert len(sent) == 1
    assert sent[0]["to_email"] == "trusthub-verify@twilio.com"
    assert sent[0]["channel"] == "email"
    assert row["metadata"]["awaiting_approval"] is False
    assert row["metadata"]["approved_at"]


def test_double_tap_sends_exactly_once(sent):
    row = _draft_row()
    db = FakeDB([row])
    first = eda.cmd_approve(row["id"], db=db)
    second = eda.cmd_approve(row["id"], db=db)
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"] == "already_approved"
    assert len(sent) == 1, "a second tap must never produce a second email"


def test_claim_happens_before_send(sent):
    """If the claim cannot be made, the gateway must not be called at all."""
    row = _draft_row(metadata={"awaiting_approval": False,
                               "from_identity": "x@y.com"})
    db = FakeDB([row])
    out = eda.cmd_approve(row["id"], db=db)
    assert out["ok"] is False
    assert sent == []


def test_rejected_draft_cannot_later_be_approved(sent):
    row = _draft_row()
    db = FakeDB([row])
    assert eda.cmd_reject(row["id"], reason="not now", db=db)["ok"] is True
    out = eda.cmd_approve(row["id"], db=db)
    assert out["ok"] is False and out["error"] == "already_rejected"
    assert sent == []


def test_reject_never_sends(sent):
    row = _draft_row()
    db = FakeDB([row])
    out = eda.cmd_reject(row["id"], db=db)
    assert out["ok"] is True and out["action"] == "rejected"
    assert sent == []
    assert row["metadata"]["rejected_at"]


def test_claim_is_compare_and_set_not_a_blind_update():
    """The race the `_resolution` guard cannot cover.

    Two taps that both read the row BEFORE either writes will both pass the
    `_resolution` check — that guard is a read, and a read cannot serialize
    anything. Only the `metadata->>awaiting_approval = true` predicate on the
    UPDATE makes the second writer lose. Assert it directly, because a
    sequential test of cmd_approve would pass even if this predicate were
    deleted, and the bug would then only appear under a real double-tap.
    """
    row = _draft_row()
    db = FakeDB([row])
    meta = dict(row["metadata"])          # both callers hold the pre-write view
    assert eda._claim(row["id"], meta, {"approved_at": "t1"}, db=db) is True
    assert eda._claim(row["id"], meta, {"approved_at": "t2"}, db=db) is False
    assert row["metadata"]["approved_at"] == "t1", "the loser must not overwrite"


# --- refusals that must happen before any send -----------------------------

def test_missing_draft_is_refused(sent):
    out = eda.cmd_approve("00000000-0000-0000-0000-000000000000", db=FakeDB([]))
    assert out["ok"] is False and out["error"] == "draft_not_found"
    assert sent == []


def test_wrong_row_type_is_refused(sent):
    row = _draft_row(type="email_received")
    out = eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert out["ok"] is False and out["error"] == "not_a_draft_row"
    assert sent == []


def test_draft_without_recipient_is_refused(sent):
    row = _draft_row(metadata={"awaiting_approval": True, "from_identity": ""})
    out = eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert out["ok"] is False and out["error"] == "draft_has_no_recipient"
    assert sent == []


def test_empty_body_is_refused(sent):
    row = _draft_row(content="   ")
    out = eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert out["ok"] is False and out["error"] == "draft_body_empty"
    assert sent == []


# --- the "unreadable is not undecided" property ----------------------------

def test_unparseable_metadata_raises_rather_than_reading_as_undecided():
    """A metadata blob we cannot parse must NOT degrade to {}.

    {} has `awaiting_approval` absent, which _resolution() reads as "no decision
    recorded" — i.e. an already-sent draft would look sendable again. Failing
    loudly is the only safe reading.
    """
    row = _draft_row(metadata="{not json")
    with pytest.raises(json.JSONDecodeError):
        eda.cmd_approve(row["id"], db=FakeDB([row]))


def test_metadata_accepts_a_json_string_from_turso(sent):
    """Turso stores metadata as TEXT; the Supabase shim hands back a dict."""
    row = _draft_row(metadata=json.dumps({
        "awaiting_approval": True,
        "from_identity": "a@b.com",
        "rfc_message_id": "<m1>",
    }))
    out = eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert out["ok"] is True, out
    assert len(sent) == 1


# --- threading -------------------------------------------------------------

def test_reply_is_threaded_onto_the_inbound_message(sent):
    row = _draft_row()
    eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert sent[0]["in_reply_to"] == "<abc@twilio.com>"
    assert sent[0]["references"] == "<abc@twilio.com>"


def test_send_is_operator_initiated_and_transactional(sent):
    """CC tapped approve. A nurture cooldown must not silently eat the reply."""
    row = _draft_row()
    eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert sent[0]["agent_source"] == "manual_cc"
    assert sent[0]["intent"] == "transactional"


# --- a blocked send must be visible on the row -----------------------------

def test_blocked_send_records_why_on_the_row(monkeypatch):
    mod = type(sys)("send_gateway")
    mod.send = lambda **kw: {"status": "blocked", "reason": "suppressed"}
    monkeypatch.setitem(sys.modules, "send_gateway", mod)
    row = _draft_row()
    out = eda.cmd_approve(row["id"], db=FakeDB([row]))
    assert out["ok"] is False and out["error"] == "send_blocked"
    assert row["metadata"]["send_status"] == "blocked"
    assert row["metadata"]["send_error"] == "suppressed"
