# -*- coding: utf-8 -*-
"""A standing never-email order must not be silently tenant-local.

WHY THIS EXISTS
---------------
2026-09-07. checkEmailSuppressed() enforces on (tenant_id, email), deliberately:
a merchant unsubscribing from one brand must not be silently unsubscribed from
another. But that makes a STANDING ORDER tenant-local without saying so. The
operator's "never email this address, suppress on sight" order for a test
account was filed against SunBiz only, while two live OASIS leads carried that
exact address, both at stage founder_meeting_booked -- a stage whose automation
sends confirmations and reminders. Every guardrail read as passing.

audit_suppression_coverage.find_gaps is the guard for that class. A guard that
reports "no gaps" against live data proves nothing on its own -- an empty result
and a broken query look identical -- so these drive it with fixtures where the
right answer is known.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit_suppression_coverage import find_gaps  # noqa: E402

SUNBIZ = "aa04fa1f-sunbiz"
OASIS = "ef8d389e-oasis"


class _FakeDb:
    """Answers the two queries find_gaps issues, in order."""

    def __init__(self, suppressions, leads):
        self._suppressions = suppressions
        self._leads = leads

    def query(self, sql, params=None, **kwargs):
        return self._leads if "tenant_records" in sql else self._suppressions


def _sup(email, tenant):
    return {"email": email, "tenant_id": tenant}


def _lead(email, tenant, lead_id="L1", stage="assigned"):
    return {"email": email, "tenant_id": tenant, "id": lead_id, "stage": stage}


# -- 1. the incident itself ------------------------------------------------

def test_the_incident_is_detected():
    """Suppressed on SunBiz, live lead on OASIS -> one gap."""
    gaps = find_gaps(_FakeDb(
        [_sup("goldstorm2003@gmail.com", SUNBIZ)],
        [_lead("goldstorm2003@gmail.com", OASIS, "3cdc815b", "founder_meeting_booked")],
    ))
    assert len(gaps) == 1
    g = gaps[0]
    assert g["email"] == "goldstorm2003@gmail.com"
    assert g["mailable_from_tenant"] == OASIS
    assert g["suppressed_on"] == [SUNBIZ]
    assert g["stage"] == "founder_meeting_booked", (
        "the stage must ride along -- a booked meeting is actively sending"
    )


def test_once_the_missing_row_exists_the_gap_closes():
    """The fix was the row, not a redesign. Prove the guard agrees."""
    gaps = find_gaps(_FakeDb(
        [_sup("goldstorm2003@gmail.com", SUNBIZ),
         _sup("goldstorm2003@gmail.com", OASIS)],
        [_lead("goldstorm2003@gmail.com", OASIS)],
    ))
    assert gaps == []


# -- 2. it must not cry wolf ----------------------------------------------

def test_a_lead_on_the_same_tenant_that_suppressed_it_is_not_a_gap():
    gaps = find_gaps(_FakeDb(
        [_sup("x@example.com", SUNBIZ)],
        [_lead("x@example.com", SUNBIZ)],
    ))
    assert gaps == []


def test_an_address_nobody_holds_as_a_lead_is_not_a_gap():
    """84 suppressions with no matching lead must stay silent, or the report
    is noise and nobody reads it."""
    gaps = find_gaps(_FakeDb(
        [_sup(f"user{i}@example.com", SUNBIZ) for i in range(84)],
        [_lead("someone.else@example.com", OASIS)],
    ))
    assert gaps == []


def test_an_unsuppressed_lead_is_not_a_gap():
    gaps = find_gaps(_FakeDb([], [_lead("fresh@example.com", OASIS)]))
    assert gaps == []


# -- 3. matching is case- and whitespace-insensitive ----------------------

def test_case_and_padding_do_not_hide_a_gap():
    """A real address arrives however the rep typed it."""
    gaps = find_gaps(_FakeDb(
        [_sup("  GoldStorm2003@Gmail.COM ", SUNBIZ)],
        [_lead("goldstorm2003@gmail.com", OASIS)],
    ))
    assert len(gaps) == 1, "an address that differs only by case must still match"


# -- 4. shape ---------------------------------------------------------------

def test_one_address_mailable_from_two_tenants_reports_both():
    gaps = find_gaps(_FakeDb(
        [_sup("a@b.co", SUNBIZ)],
        [_lead("a@b.co", OASIS, "L1"), _lead("a@b.co", "third-tenant", "L2")],
    ))
    assert {g["mailable_from_tenant"] for g in gaps} == {OASIS, "third-tenant"}


def test_a_null_email_on_a_lead_is_skipped_not_crashed():
    gaps = find_gaps(_FakeDb(
        [_sup("a@b.co", SUNBIZ)],
        [{"email": None, "tenant_id": OASIS, "id": "L1", "stage": "assigned"},
         _lead("a@b.co", OASIS, "L2")],
    ))
    assert len(gaps) == 1 and gaps[0]["lead_id"] == "L2"


def test_the_audit_never_writes():
    """It reports. Deciding that one brand's opt-out binds another is a consent
    judgement, and it is the operator's, not a script's."""
    src = (Path(__file__).resolve().parent.parent / "audit_suppression_coverage.py"
           ).read_text(encoding="utf-8")
    import ast

    # Scoped to calls ON THE DB HANDLE, not to bare identifiers anywhere in the
    # file. The first version of this test asserted the name "insert" never
    # appeared and failed on `sys.path.insert(0, ...)` -- a guard tripping over
    # unrelated code, which is how guards get deleted instead of fixed.
    called_on_db = {
        node.func.attr
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "db"
    }
    for forbidden in ("insert", "execute", "commit", "executemany", "update", "delete"):
        assert forbidden not in called_on_db, (
            f"the audit must not call db.{forbidden}() -- it reports, it does not act"
        )
    assert called_on_db == {"query"}, (
        f"the audit may only READ from the database; it calls {sorted(called_on_db)}"
    )
