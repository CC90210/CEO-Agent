"""What the scheduler RECORDS about the jobs it runs.

Two defects, one root cause: the scheduler executed 33 automations and kept
almost nothing about them.

  DURATION — nothing measured how long any automation takes. cron_jobs has no
    duration column and the scheduler timed only its own loop, so "which
    automation is eating the machine" was unanswerable. On a box where every
    subprocess pays AV-inflated spawn cost (a bare `python -c pass` measures
    3.7s) that is the question most likely to matter, and three separate
    timeout bugs in one week were diagnosed by hand-timing things that should
    already have been on record. The first record written after the fix caught
    the inbound sweep at 301.6s against a 300s kill.

  LEGIBILITY — the stored result was `out[-1][:200]`: the last line of stdout,
    sliced. For a script printing pretty JSON the last line is `}`, so
    "Bravo - Cross-Agent Review Scan" stored `]` and "Daily Memory Index
    Rebuild" stored `}` as their entire recorded outcome, and both scored as
    healthy because neither starts with ERROR. Three more rows sat exactly on
    the 200-char boundary with the cut landing inside the JSON, removing the
    escalation reasons — the only part worth keeping.

Tags: #testing #observability #cron
Related: [[brain/AUTOMATIONS]] | [[brain/DATA_LIFECYCLE]]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scheduler as sch  # noqa: E402


# ------------------------------------------------------------- legibility ---

def test_pretty_json_is_summarized_not_reduced_to_a_brace():
    """The exact shape of both OPAQUE rows."""
    out = sch.summarize_stdout('{\n  "reds": 0,\n  "yellows": 2,\n  "checks": [1, 2, 3]\n}')
    assert out not in ("}", "]"), "still storing a bare closing brace"
    assert "reds=0" in out and "yellows=2" in out


def test_a_json_list_does_not_store_a_bare_bracket():
    out = sch.summarize_stdout('[\n  {"a": 1},\n  {"b": 2}\n]')
    assert out != "]"
    assert "2 item(s)" in out


def test_a_trailing_brace_after_real_output_is_skipped():
    """Not JSON overall, so the line scan runs — and must skip punctuation-only
    lines rather than reporting the last one blindly."""
    assert sch.summarize_stdout("Done. 3 scored, 0 failed.\n}") == "Done. 3 scored, 0 failed."


def test_truncation_announces_itself():
    """A silent cut at exactly the limit is indistinguishable from a complete
    short result. That is how three jobs' escalation reasons were lost while
    their rows read as healthy."""
    out = sch.summarize_stdout("z" * 400)
    assert len(out) <= sch.RESULT_LIMIT
    assert "cut" in out, "truncated result gives no sign it was truncated"


def test_a_summary_never_lands_on_the_slice_signature():
    """harness_eval flags a stored result that is JSON-shaped, unparseable and
    exactly a slice length. A summary must not reproduce that signature: it is
    either valid on its own terms or it says it was cut."""
    for raw in ('{"report": [{"reason": "' + "x" * 600 + '"}], "reds": 1}',
                "[" + ", ".join(f'{{"i": {i}}}' for i in range(200)) + "]"):
        out = sch.summarize_stdout(raw)
        assert len(out) <= sch.RESULT_LIMIT
        if out[:1] in "{[":
            json.loads(out)  # raises if we stored an unparseable fragment


def test_empty_output_is_ok_not_empty():
    assert sch.summarize_stdout("") == "ok"
    assert sch.summarize_stdout("   \n  \n") == "ok"


def test_the_result_limit_is_shared_not_re_typed():
    """Four hand-rolled copies of `[:200]` is how the rule drifted in the first
    place. One constant, and no literal 200 left in the extraction path."""
    import ast
    import inspect
    import textwrap

    # AST, not a substring scan: the docstrings deliberately quote the old
    # `[:200]` slice, and a test that cannot tell prose from code would force
    # the history out of the file to stay green.
    for fn in (sch.summarize_stdout, sch._clip_result, sch._summarize_json):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and n.value == 200]
        assert not literals, f"{fn.__name__} hardcodes 200 instead of RESULT_LIMIT"


# ---------------------------------------------------------------- duration ---

def test_a_timing_record_is_appended_per_job(tmp_path, monkeypatch):
    monkeypatch.setattr(sch, "TIMINGS_PATH", tmp_path / "cron_timings.jsonl")
    sch._record_job_timing("Inbound Email Sweep", "email_inbox_check", 301.63, "ok")
    rec = json.loads((tmp_path / "cron_timings.jsonl").read_text(encoding="utf-8").strip())
    assert rec["job"] == "Inbound Email Sweep"
    assert rec["action_type"] == "email_inbox_check"
    assert rec["seconds"] == 301.6
    assert rec["ok"] is True
    assert rec["ts"].endswith("+00:00"), "timestamps must be UTC-explicit"


def test_the_verdict_is_stored_not_the_payload(tmp_path, monkeypatch):
    """last_result can carry an entire harness scoreboard. This file is read for
    timing; storing the payload would make it unreadable and unbounded."""
    monkeypatch.setattr(sch, "TIMINGS_PATH", tmp_path / "t.jsonl")
    sch._record_job_timing("X", "script_run", 1.0, "ERROR: script_run exit 1: boom " + "d" * 5000)
    rec = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").strip())
    assert rec["ok"] is False
    assert len(json.dumps(rec)) < 300


def test_failure_classification_matches_the_stored_result(tmp_path, monkeypatch):
    monkeypatch.setattr(sch, "TIMINGS_PATH", tmp_path / "t.jsonl")
    for result, expected in (("ok", True), ("nothing queued", True),
                             ("ERROR: exit 3221225480", False),
                             ("FAILED (timeout after 300s)", False)):
        sch._record_job_timing("J", "script_run", 1.0, result)
    rows = [json.loads(x) for x in
            (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["ok"] for r in rows] == [True, True, False, False]


def test_recording_never_raises_into_the_job(tmp_path, monkeypatch):
    """Telemetry that can break a cron run is worse than no telemetry. Point it
    at a path that cannot be created and the job must still proceed."""
    monkeypatch.setattr(sch, "TIMINGS_PATH", tmp_path / "t.jsonl" / "nested.jsonl")
    sch._record_job_timing("J", "script_run", 1.0, "ok")  # must not raise


def test_the_file_is_trimmed_so_it_cannot_grow_without_bound(tmp_path, monkeypatch):
    """state/*.log rotation does not cover .jsonl — see brain/DATA_LIFECYCLE.md.
    Written with 3x the keep count so the trim must actually fire."""
    path = tmp_path / "t.jsonl"
    monkeypatch.setattr(sch, "TIMINGS_PATH", path)
    monkeypatch.setattr(sch, "TIMINGS_KEEP", 50)
    for i in range(300):
        sch._record_job_timing(f"job-{i}", "script_run", 1.0, "ok")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 300
    # The newest record must survive the trim — a trim that keeps the head
    # instead of the tail silently freezes the metric.
    assert json.loads(lines[-1])["job"] == "job-299"
