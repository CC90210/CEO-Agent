"""The extraction daemon must never lose a capability to a usage limit.

THE INCIDENT (2026-09-03). A SunBiz rep dropped a merchant application. The
Claude CLI answered "You've hit your session limit - resets 8pm". The daemon
asked `is_claude_auth_or_quota_failure()` whether that counted as a quota
failure, the Python copy of that predicate did not know the phrase, and the
answer was no — so the daemon treated a capped subscription as a code bug,
wrote `cli_failed:`, and never tried the free tier it already had. The rep saw
"Couldn't read this application."

Two defects, and this file pins both:

  1. The predicate did not know the phrase.  → test_the_incident_string_alone_*
  2. The fallback existed only BEHIND the predicate, so any phrase it did not
     know took the whole feature down. → test_ladder_descends_on_*

Defect 2 is the important one. Widening a regex buys time until the next
unrecognised message; making the ladder unconditional means a miss costs one
wasted retry instead of the feature. These tests assert the ladder descends on
failures the predicate does NOT recognise — deliberately, because that is the
case the old code got wrong.

Run: python -m pytest scripts/tests/test_extraction_fallback_ladder.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

ec = pytest.importorskip("integrations.extraction_consumer")
from lib.application_fields import extract_fields, is_useful  # noqa: E402
from lib.claude_auth import is_claude_auth_or_quota_failure  # noqa: E402
from lib.doc_text import extract_text  # noqa: E402

SESSION_LIMIT = "You've hit your session limit - resets 8pm\nWarning: no stdin data received in 3s, proceeding without it."

APPLICATION_TEXT = """MERCHANT FUNDING APPLICATION
Legal Business Name: Red Door Homes of North Central Florida, LLC
DBA: Red Door Homes
Business Address: 4014 NW 13th St, Gainesville FL 32609
Federal Tax ID: 82-3391847
Date Business Started: 03/14/2016
Entity Type: Limited Liability Company
Business Phone: (352) 505-1180
Email: ezra@reddoorhomesncf.com
Owner Name: Ezra Whitfield
Ownership %: 100%
Average Monthly Revenue: $148,500
Amount Requested: $1,105,462
"""


def _pdf_bytes(text: str = APPLICATION_TEXT) -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((50, 60), text, fontsize=9)
    raw = doc.tobytes()
    doc.close()
    return raw


@pytest.fixture(autouse=True)
def _reset_daemon_state():
    """Cooldown and deferral counters are module globals — isolate every test."""
    ec._quota_cooldown_until = 0.0
    ec._deferrals.clear()
    yield
    ec._quota_cooldown_until = 0.0
    ec._deferrals.clear()


@pytest.fixture
def doc(tmp_path):
    raw = _pdf_bytes()
    path = tmp_path / "application.pdf"
    path.write_bytes(raw)
    return path, raw


def _cli_returning(output: str, code: int = 1):
    def _stub(_env, _doc_path):
        return False, None, output, code

    return _stub


def _opencode_unavailable(monkeypatch):
    """Force the ladder past tier 2 so tier 3 (no model at all) is exercised."""
    monkeypatch.setattr(ec, "_extract_via_opencode", lambda *_a, **_k: (False, None, "stubbed_off"))


# ── defect 1: the predicate ────────────────────────────────────────────────


def test_the_incident_string_alone_is_recognised_as_quota():
    assert is_claude_auth_or_quota_failure(SESSION_LIMIT, 1) is True


def test_the_stdin_warning_alone_is_not_a_quota_signal():
    """That warning rode along on every failure, including genuine bugs."""
    warning_only = "Warning: no stdin data received in 3s, proceeding without it."
    assert is_claude_auth_or_quota_failure(warning_only, 1) is False


# ── defect 2: the ladder must descend regardless ───────────────────────────


def test_ladder_descends_on_the_incident_string(monkeypatch, doc):
    path, raw = doc
    monkeypatch.setattr(ec, "_extract_via_cli", _cli_returning(SESSION_LIMIT))
    _opencode_unavailable(monkeypatch)

    ok, fields, tier, notes, quota_seen = ec._extract_with_ladder({}, path, raw, "application/pdf", "job-1")

    assert ok, f"the exact production failure still yields nothing: {notes}"
    assert tier == "parser"
    assert quota_seen is True
    assert fields["business_legal_name"].startswith("Red Door Homes")
    assert fields["requested_amount"] == 1105462.0


def test_ladder_descends_on_an_UNRECOGNISED_failure(monkeypatch, doc):
    """The whole point of the rewrite.

    This message is not in config/claude_auth_signals.json and is not supposed
    to be — it stands in for the NEXT phrasing Anthropic ships. Under the old
    code this took the branch that wrote `cli_failed` and gave up. A fallback
    that only runs for failures we already catalogued is not a fallback.
    """
    novel = "Error: your organization's shared capacity pool is exhausted until 04:00 UTC"
    assert is_claude_auth_or_quota_failure(novel, 1) is False, (
        "pick a genuinely unrecognised string — this test is meaningless if the "
        "predicate already matches it"
    )
    path, raw = doc
    monkeypatch.setattr(ec, "_extract_via_cli", _cli_returning(novel))
    _opencode_unavailable(monkeypatch)

    ok, fields, tier, notes, quota_seen = ec._extract_with_ladder({}, path, raw, "application/pdf", "job-2")

    assert ok, f"an unrecognised CLI failure must still reach the free tiers: {notes}"
    assert tier == "parser"
    assert quota_seen is False  # correctly classified, and it did not matter


def test_pdf_no_longer_skips_the_free_model_tier(monkeypatch, doc):
    """The old code refused tier 2 for application/pdf.

    Every one of the 45 real jobs in the queue was a PDF, so the free tier was
    dead on 100% of production traffic while looking, in review, like coverage.
    """
    path, raw = doc
    seen: dict[str, str] = {}

    def _fake_opencode(text, truncated):
        seen["text"] = text
        return True, {"business_legal_name": "Red Door Homes", "_signature": {"present": False, "page": None, "bbox": None}}, "opencode_ok"

    monkeypatch.setattr(ec, "_extract_via_cli", _cli_returning(SESSION_LIMIT))
    monkeypatch.setattr(ec, "_extract_via_opencode", _fake_opencode)

    ok, fields, tier, notes, _ = ec._extract_with_ladder({}, path, raw, "application/pdf", "job-3")

    assert ok and tier == "opencode", notes
    assert "Red Door Homes" in seen.get("text", ""), "the PDF's text never reached the free model"


def test_successful_cli_never_touches_a_fallback(monkeypatch, doc):
    path, raw = doc
    monkeypatch.setattr(ec, "_extract_via_cli", lambda *_a: (True, {"business_legal_name": "X"}, "", 0))
    monkeypatch.setattr(ec, "_extract_via_opencode", lambda *_a, **_k: pytest.fail("fallback ran on success"))

    ok, fields, tier, _notes, quota_seen = ec._extract_with_ladder({}, path, raw, "application/pdf", "job-4")
    assert (ok, tier, quota_seen) == (True, "claude_cli", False)


# ── cooldown: stop hammering a capped subscription ─────────────────────────


def test_quota_failure_puts_the_cli_on_cooldown(monkeypatch, doc):
    path, raw = doc
    calls = {"n": 0}

    def _counting_cli(_env, _p):
        calls["n"] += 1
        return False, None, SESSION_LIMIT, 1

    monkeypatch.setattr(ec, "_extract_via_cli", _counting_cli)
    monkeypatch.setattr(ec, "_notify_ops", lambda _m: None)
    _opencode_unavailable(monkeypatch)

    ec._extract_with_ladder({}, path, raw, "application/pdf", "job-5")
    ec._extract_with_ladder({}, path, raw, "application/pdf", "job-6")
    ec._extract_with_ladder({}, path, raw, "application/pdf", "job-7")

    assert calls["n"] == 1, (
        "the capped CLI was spawned again while cooling down — at an 8s poll "
        "that is ~450 pointless 3s spawns an hour"
    )


def test_cooldown_still_reports_quota_so_jobs_park_not_fail(monkeypatch, doc):
    path, raw = doc
    monkeypatch.setattr(ec, "_extract_via_cli", _cli_returning(SESSION_LIMIT))
    monkeypatch.setattr(ec, "_notify_ops", lambda _m: None)
    monkeypatch.setattr(ec, "_extract_via_opencode", lambda *_a, **_k: (False, None, "off"))
    monkeypatch.setattr(ec, "_extract_via_parser", lambda *_a, **_k: (False, None, "off"))

    ec._extract_with_ladder({}, path, raw, "application/pdf", "job-8")
    ok, _f, _t, notes, quota_seen = ec._extract_with_ladder({}, path, raw, "application/pdf", "job-9")

    assert ok is False
    assert quota_seen is True, (
        "during cooldown the daemon must still know it is capped, or a job that "
        "only needs to WAIT gets marked permanently failed"
    )
    assert any("cli-skipped:quota-cooldown" in n for n in notes)


# ── a scan is a different failure from a bug, and must say so ──────────────


def test_scanned_pdf_names_its_own_reason(monkeypatch, tmp_path):
    fitz = pytest.importorskip("fitz")
    doc_ = fitz.open()
    doc_.new_page()  # a page with no text layer at all
    raw = doc_.tobytes()
    doc_.close()
    path = tmp_path / "scan.pdf"
    path.write_bytes(raw)

    monkeypatch.setattr(ec, "_extract_via_cli", _cli_returning(SESSION_LIMIT))
    monkeypatch.setattr(ec, "_notify_ops", lambda _m: None)

    ok, _f, tier, notes, _q = ec._extract_with_ladder({}, path, raw, "application/pdf", "job-10")

    assert ok is False and tier == "none"
    joined = " ".join(notes)
    assert "free-tiers-skipped" in joined and "no_text_layer" in joined, (
        f"a scan must be distinguishable from a parser bug; got: {joined}"
    )


# ── the free tiers themselves ──────────────────────────────────────────────


def test_parser_reads_a_real_application_with_no_model():
    fields, report = extract_fields(extract_text(_pdf_bytes(), "application/pdf").text)
    assert is_useful(fields)
    assert fields["tax_id_ein"] == "82-3391847"
    assert fields["email"] == "ezra@reddoorhomesncf.com"
    assert fields["monthly_revenue"] == 148500.0
    assert fields["owner_ownership_pct"] == 100.0
    assert report["fields_found"] >= 10


def test_parser_never_claims_a_signature():
    """It reads text; a signature is pixels. Claiming one would let the
    dashboard embed a signature block that was never located."""
    fields, report = extract_fields(APPLICATION_TEXT)
    assert fields["_signature"] == {"present": False, "page": None, "bbox": None}
    assert report["signature_detected"] is False


def test_parser_declines_rather_than_guesses():
    thin = "Thank you for your interest. A representative will call you back.\n"
    fields, _report = extract_fields(thin)
    assert not is_useful(fields), "a parse this thin must not be applied to a funding application"
