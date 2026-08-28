"""The accuracy loop: evals/run_suites.py + scripts/core/accuracy_trend.py.

Both were written 2026-08-28 because the suites had not run since 2026-06-10 and
three time-series existed that nothing read. The first real run found `routing`
had drifted from 100% to 77.8% over eleven weeks with nothing surfacing it.

Every test here pins a trap that was live in the data:

* `score` in harness_eval_history.jsonl is the STRING "12/14" and the
  DENOMINATOR MOVED (10 -> 14 as checks were added), so comparing raw strings or
  numerators shows a fake decline every time a check is added.
* task_outcomes.created_at is bare UTC while the JSONL is ISO+offset.
* A suite with nothing scoreable has score None. Treating that as 0.0 would
  report a total regression for a suite that simply has no offline assertions.
* Two suites (routing_nl, mistakes) have no usable baseline. Gating on them
  would pin the alert permanently red, which is how a gate gets ignored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "evals"))

import run_suites  # noqa: E402
from core import accuracy_trend as trend  # noqa: E402


# --- run_suites: scoring contract --------------------------------------------

def test_rubric_cases_are_unscored_not_failed(tmp_path, monkeypatch):
    """A mistake awaiting a deterministic check is honest-pending. Counting it
    as a failure would make the suite permanently red; counting it as a pass
    would be a lie."""
    case = tmp_path / "c1"
    case.mkdir()
    (case / "expected.json").write_text(
        json.dumps({"scorer": "rubric", "field": "verdict", "expected": "x"}),
        encoding="utf-8")
    r = run_suites._score_case(case)
    assert r["status"] == "unscored"


def test_a_suite_with_nothing_scoreable_has_no_score_not_zero(monkeypatch):
    monkeypatch.setattr(run_suites, "_case_dirs", lambda s: [])
    rep = run_suites.run_suite("mistakes")
    assert rep["score"] is None, "no scoreable cases must be None, never 0.0"
    assert rep["n_scored"] == 0


def test_case_error_is_reported_not_swallowed(tmp_path, monkeypatch):
    case = tmp_path / "boom"
    case.mkdir()
    (case / "expected.json").write_text(
        json.dumps({"scorer": "exact", "field": "f", "expected": 1}), encoding="utf-8")

    def explode(_):
        raise RuntimeError("adapter blew up")
    monkeypatch.setattr(run_suites.adapter, "run_case", explode)
    r = run_suites._score_case(case)
    assert r["status"] == "error"
    assert "adapter blew up" in r["error"]


# --- run_suites: gating contract ---------------------------------------------

def test_only_a_baselined_suite_can_regress():
    """routing_nl scores 0.333 by design. Gating on it makes the weekly alert
    permanently red, and a permanently red gate is an ignored gate."""
    v = run_suites.verdict({"suite": "routing_nl", "score": 0.333}, {})
    assert v["state"] == "unbaselined"


def test_a_baselined_suite_below_tolerance_regresses():
    base = {"routing": {"score": 1.0, "tolerance": 0.1}}
    v = run_suites.verdict({"suite": "routing", "score": 0.778}, base)
    assert v["state"] == "regressed"


def test_a_baselined_suite_inside_tolerance_is_ok():
    base = {"routing": {"score": 1.0, "tolerance": 0.1}}
    assert run_suites.verdict({"suite": "routing", "score": 0.95}, base)["state"] == "ok"


def test_tolerance_boundary_is_not_a_regression():
    """Exactly at the floor must pass, or tolerance means one less than it says."""
    base = {"routing": {"score": 1.0, "tolerance": 0.1}}
    assert run_suites.verdict({"suite": "routing", "score": 0.9}, base)["state"] == "ok"


def test_discovery_includes_suites_absent_from_the_adapter_dispatch():
    """routing_nl's cases carry `suite: routing` in meta.yaml, so keying
    discovery on adapter.DISPATCH silently skipped the whole directory — a suite
    stops being measured without anyone deciding to stop measuring it."""
    found = run_suites.discover_suites()
    assert "routing_nl" in found
    assert "reports" not in found


# --- accuracy_trend: the three incompatible formats ---------------------------

@pytest.mark.parametrize("raw,expected", [
    ("12/14", 12 / 14),
    ("10/10", 1.0),
    ("7/10", 0.7),
    (0.85, 0.85),
    ("nonsense", None),
    ("5/0", None),
    (None, None),
])
def test_score_string_parses_to_a_ratio(raw, expected):
    got = trend._ratio(raw)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)


def test_moving_denominator_does_not_fake_a_decline():
    """THE trap. 10/10 then 13/14 is a real DROP in ratio, but 12/14 after 10/10
    must not read as an improvement just because the numerator grew."""
    assert trend._ratio("12/14") < trend._ratio("10/10")
    assert trend._ratio("14/14") == trend._ratio("10/10")


@pytest.mark.parametrize("raw", [
    "2026-08-28T04:07:44.017Z",          # ISO + Z
    "2026-08-28T04:07:44+00:00",         # ISO + offset (harness jsonl)
    "2026-08-28 04:07:44",               # bare UTC (task_outcomes.created_at)
    "2026-08-28",                        # date only (eval reports)
])
def test_every_timestamp_format_in_play_parses(raw):
    assert trend._as_date(raw) is not None


def test_unparseable_timestamp_is_dropped_not_guessed():
    assert trend._as_date("not a date") is None
    assert trend._as_date(None) is None


def test_week_label_is_iso_and_sortable():
    import datetime as dt
    labels = [trend._week(dt.date(2026, 8, d)) for d in (3, 10, 28)]
    assert labels == sorted(labels), "week labels must sort chronologically"
    assert all(w.startswith("2026-W") for w in labels)


def test_eval_reports_with_null_score_are_skipped_not_zeroed(tmp_path, monkeypatch):
    monkeypatch.setattr(trend, "EVAL_REPORTS", tmp_path)
    (tmp_path / "2026-08-28_mistakes.json").write_text(
        json.dumps({"suite": "mistakes", "date": "2026-08-28", "score": None}),
        encoding="utf-8")
    (tmp_path / "2026-08-28_routing.json").write_text(
        json.dumps({"suite": "routing", "date": "2026-08-28", "score": 0.778}),
        encoding="utf-8")
    weeks = trend.evals_by_week(8)
    scores = next(iter(weeks.values()))
    assert "mistakes" not in scores, "a null score must not be charted as 0%"
    assert scores["routing"] == pytest.approx(0.778)


def test_render_states_what_it_cannot_measure():
    """The brief asked for a hallucination rate. validator_pending.jsonl has no
    verdict and no timestamp, so it is not computable — the report must say so
    rather than invent a denominator."""
    out = trend.render(trend.build(2))
    assert "NOT MEASURED" in out
    assert "validator_pending" in out


# --- trailing windows: current state vs lagging average ----------------------

class TestTrailingWindow:
    """The weekly mean is lagging and, on its own, misleading.

    On 2026-08-28 — the day six substantial defects were fixed — the weekly
    figure read 91.3% because it averaged 110 runs most of which were taken
    while the fleet was genuinely broken. The trailing 20 read 95.7% and the
    last seven runs were all perfect. Reporting only the weekly number tells an
    operator a fix has not landed when it has, which is the opposite of what a
    health report is for.
    """

    def _hist(self, tmp_path, monkeypatch, scores):
        p = tmp_path / "h.jsonl"
        p.write_text("\n".join(
            json.dumps({"timestamp": f"2026-08-28T{i:02d}:00:00+00:00",
                        "score": s, "pass": s.split("/")[0] == s.split("/")[1]})
            for i, s in enumerate(scores)), encoding="utf-8")
        monkeypatch.setattr(trend, "HARNESS_HISTORY", p)

    def test_trailing_window_reflects_recent_runs_only(self, tmp_path, monkeypatch):
        """Ten bad runs then five perfect ones: the last-5 window must be 100%
        even though the overall mean is far lower."""
        self._hist(tmp_path, monkeypatch, ["7/14"] * 10 + ["14/14"] * 5)
        out = trend.harness_trailing(windows=(5, 15))
        assert out[5]["mean"] == pytest.approx(1.0)
        assert out[5]["perfect"] == 5
        assert out[15]["mean"] < 0.8, "the wide window must still show the history"

    def test_a_fix_moves_the_trailing_window_before_the_weekly_mean(self, tmp_path, monkeypatch):
        """The property the whole split exists for."""
        self._hist(tmp_path, monkeypatch, ["7/14"] * 40 + ["14/14"] * 5)
        out = trend.harness_trailing(windows=(5, 50))
        assert out[5]["mean"] > out[50]["mean"]

    def test_runs_are_ordered_by_time_not_file_order(self, tmp_path, monkeypatch):
        """A trailing window keyed on file order would be wrong the moment two
        processes append out of sequence."""
        p = tmp_path / "h.jsonl"
        p.write_text("\n".join([
            json.dumps({"timestamp": "2026-08-28T23:00:00+00:00", "score": "14/14", "pass": True}),
            json.dumps({"timestamp": "2026-08-28T01:00:00+00:00", "score": "7/14", "pass": False}),
        ]), encoding="utf-8")
        monkeypatch.setattr(trend, "HARNESS_HISTORY", p)
        out = trend.harness_trailing(windows=(1,))
        assert out[1]["mean"] == pytest.approx(1.0), "newest run is the 23:00 one"

    def test_missing_history_is_empty_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(trend, "HARNESS_HISTORY", tmp_path / "nope.jsonl")
        assert trend.harness_trailing() == {}

    def test_render_leads_with_current_state(self, tmp_path, monkeypatch):
        self._hist(tmp_path, monkeypatch, ["14/14"] * 5)
        out = trend.render(trend.build(2))
        assert "HARNESS NOW" in out
        assert out.index("HARNESS NOW") < out.index("HARNESS BY WEEK"), (
            "the lagging weekly figure must not be the first number CC sees")
