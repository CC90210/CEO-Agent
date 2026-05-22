"""Tests for scripts/lib/lead_contract.py — the canonical contract every
scraping agent must fulfil when inserting a lead.

These tests are the safety net: if a scraper drops `phone` or stops
populating `source`, the test fails before the bad row hits the DB. Wired
into pytest via tests/conftest.py (which adds scripts/ to sys.path)."""
from __future__ import annotations

import pytest

from lib.lead_contract import (  # type: ignore
    HARD_REQUIRED,
    REQUIRED_FIELDS,
    enrich_lead_defaults,
    has_hard_required,
    validate_lead,
)


class TestValidateLead:
    def test_complete_row_has_no_missing_fields(self):
        row = {
            "name": "Jane Doe",
            "company": "Acme",
            "email": "jane@acme.com",
            "phone": "555-1234",
            "source": "firecrawl",
            "stage": "new",
            "score": 42,
            "value_estimate": 5000,
            "notes": "AI: high-fit, replied warmly to last touch.",
        }
        assert validate_lead(row) == []

    def test_minimal_row_returns_all_missing(self):
        row = {"email": "x@y.com"}
        missing = validate_lead(row)
        for required in REQUIRED_FIELDS:
            if required != "email":
                assert required in missing

    def test_empty_string_is_missing(self):
        row = {"name": "", "email": "x@y.com", "source": "manual"}
        assert "name" in validate_lead(row)

    def test_whitespace_only_is_missing(self):
        row = {"name": "   ", "email": "x@y.com", "source": "manual"}
        assert "name" in validate_lead(row)

    def test_zero_score_is_treated_as_unscored(self):
        # Contract: score=0 means "not yet scored", which is missing —
        # auto_score_leads will fill it in. This is the behavior that
        # surfaces "needs scoring" on the dashboard chip.
        row = {"score": 0, "email": "x@y.com", "source": "manual"}
        assert "score" in validate_lead(row)

    def test_none_value_estimate_is_missing(self):
        row = {"value_estimate": None, "email": "x@y.com", "source": "manual"}
        assert "value_estimate" in validate_lead(row)


class TestHasHardRequired:
    def test_email_and_source_present_returns_true(self):
        assert has_hard_required({"email": "x@y.com", "source": "manual"})

    def test_missing_email_returns_false(self):
        assert not has_hard_required({"source": "manual"})

    def test_missing_source_returns_false(self):
        assert not has_hard_required({"email": "x@y.com"})

    def test_empty_email_returns_false(self):
        assert not has_hard_required({"email": "", "source": "manual"})

    def test_hard_required_is_a_subset_of_required_fields(self):
        # Contract sanity: every HARD_REQUIRED must be in REQUIRED_FIELDS
        # — otherwise we'd reject rows for fields nobody enforces.
        for k in HARD_REQUIRED:
            assert k in REQUIRED_FIELDS


class TestEnrichLeadDefaults:
    def test_fills_in_stage_default(self):
        out = enrich_lead_defaults({"email": "x@y.com", "source": "manual"})
        assert out["stage"] == "new"

    def test_fills_in_score_default(self):
        out = enrich_lead_defaults({"email": "x@y.com", "source": "manual"})
        assert out["score"] == 0

    def test_does_not_overwrite_existing_values(self):
        out = enrich_lead_defaults(
            {"email": "x@y.com", "source": "manual", "stage": "qualified", "score": 85}
        )
        assert out["stage"] == "qualified"
        assert out["score"] == 85

    def test_populates_missing_info(self):
        out = enrich_lead_defaults({"email": "x@y.com", "source": "manual"})
        # name/company/phone/value_estimate/notes all blank → all in missing_info
        for f in ("name", "company", "phone", "value_estimate", "notes"):
            assert f in out["missing_info"]

    def test_missing_info_empty_when_complete(self):
        complete = {
            "name": "Jane",
            "company": "Acme",
            "email": "j@a.com",
            "phone": "555",
            "source": "firecrawl",
            "stage": "new",
            "score": 50,
            "value_estimate": 1000,
            "notes": "warm",
        }
        out = enrich_lead_defaults(complete)
        assert out["missing_info"] == []

    def test_idempotent(self):
        row = {"email": "x@y.com", "source": "manual"}
        once = enrich_lead_defaults(row)
        twice = enrich_lead_defaults(once)
        assert once == twice

    def test_does_not_mutate_input(self):
        row = {"email": "x@y.com", "source": "manual"}
        before = dict(row)
        enrich_lead_defaults(row)
        assert row == before


@pytest.mark.parametrize("contract_field", list(REQUIRED_FIELDS))
def test_each_required_field_individually_detected(contract_field: str):
    """Parametric coverage — drop each field one at a time and confirm
    validate_lead surfaces it. Guards against silent contract drift if
    someone reorders REQUIRED_FIELDS or changes the _is_present check."""
    complete: dict[str, object] = {
        "name": "Jane",
        "company": "Acme",
        "email": "j@a.com",
        "phone": "555",
        "source": "firecrawl",
        "stage": "new",
        "score": 50,
        "value_estimate": 1000,
        "notes": "warm",
    }
    complete.pop(contract_field)
    assert contract_field in validate_lead(complete)
