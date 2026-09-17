"""A failing `script_run` job must leave a dump. Until 2026-09-13 it could not.

The scheduler has two paths that spawn a child. run_script() persisted a
failure dump at both of its failure exits; run_script_action() — the handler
the dispatcher routes `action_type: script_run` to — persisted nothing at all.

Every cron job failing in the days before 2026-09-13 is a script_run job:
Marketing Publish Drain (exit 3221225480), Weekly Event Bus Retention (killed
at its 900s wall), Library Post Linker (exit 1) and Bravo — Nightly Harness
Eval (exit 1). Four jobs, dozens of failures, a combined zero bytes of evidence
on disk — while failure_dump_hint() pointed whoever was debugging at
tmp/cron_failures/ for a file that was never going to be written for that job.

These tests pin the fix where the bug actually lived. persist_failure() was
never broken; nothing on this path called it. So the assertions are about the
CALL — both branches, the full stderr surviving, and the pointer still being
readable after the clip into cron_jobs.last_result.

Tags: #testing #cron #observability #regression
Related: [[brain/AUTOMATIONS]] | [[brain/DATA_LIFECYCLE]]
"""

from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scheduler as sch  # noqa: E402


@pytest.fixture
def dump_dir(tmp_path, monkeypatch):
    """Point dumps away from the real tmp/cron_failures/.

    Load-bearing, not tidiness: harness_eval.check_no_recent_cron_failure_dumps
    counts every *.log in that directory under 24h old. A test that wrote there
    would turn the nightly harness red — manufacturing the exact failure this
    change set exists to make legible.
    """
    d = tmp_path / "cron_failures"
    monkeypatch.setattr(sch, "FAILURE_DUMP_DIR", d)
    return d


@pytest.fixture
def failing_script():
    """A real child that fails the way the real ones do: a long stderr whose
    interesting frame sits below every upstream truncation point."""
    rel = "tmp/_dump_probe_failing.py"
    path = sch.PROJECT_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import sys\n"
        "sys.stdout.write('PROBE_STDOUT_MARKER\\n')\n"
        "sys.stderr.write('PROBE_STDERR_HEAD\\n')\n"
        "sys.stderr.write('q' * 3000 + '\\n')\n"
        "sys.stderr.write('PROBE_FRAME_BELOW_THE_CUT\\n')\n"
        "sys.exit(7)\n",
        encoding="utf-8",
    )
    try:
        yield rel
    finally:
        path.unlink(missing_ok=True)


# ------------------------------------------------------- the two branches ---

def test_a_non_zero_script_run_writes_a_dump(dump_dir, failing_script):
    """The Library Post Linker / Marketing Publish Drain shape: a plain
    non-zero exit. Before the fix this produced no file at all."""
    result = sch.run_script_action({"script": failing_script})

    dumps = list(dump_dir.glob("*.log"))
    assert len(dumps) == 1, f"exit 7 left no dump — result was: {result}"

    body = dumps[0].read_text(encoding="utf-8")
    assert "exit code : 7" in body
    assert "PROBE_STDERR_HEAD" in body
    assert "PROBE_STDOUT_MARKER" in body, (
        "stdout was dropped; a child that prints context then dies loses it")
    assert "_dump_probe_failing.py" in body, "the command line is not recorded"
    assert dumps[0].name in result, "the caller is never told the dump exists"


def test_the_frame_below_every_truncation_survives(dump_dir, failing_script):
    """The whole reason persist_failure exists. last_result caps at 500, the
    log line at 200, `err` at 300 — the 2026-07-29 SSLKEYLOGFILE root cause was
    below all three and therefore existed nowhere on disk for 25 hours."""
    sch.run_script_action({"script": failing_script})
    body = next(iter(dump_dir.glob("*.log"))).read_text(encoding="utf-8")

    assert "PROBE_FRAME_BELOW_THE_CUT" in body, "stderr was truncated on its way to disk"
    assert body.count("q") >= 3000, "the full stderr did not reach the dump"


def test_a_timed_out_script_run_writes_a_dump(dump_dir, failing_script, monkeypatch):
    """The Weekly Event Bus Retention shape: killed at the wall, no exit code,
    no traceback. Raised directly rather than hung for real — run_script_action
    clamps `timeout` to a 10s floor, so a genuine hang costs 10s of test time
    to exercise the identical branch.
    """
    def fake_run(cmd, **kwargs):
        raise sch.subprocess.TimeoutExpired(
            cmd, kwargs.get("timeout", 300),
            output="PARTIAL_STDOUT", stderr="PARTIAL_STDERR")

    monkeypatch.setattr(sch.subprocess, "run", fake_run)
    result = sch.run_script_action({"script": failing_script, "timeout": 900})

    dumps = list(dump_dir.glob("*.log"))
    assert len(dumps) == 1, f"timeout left no dump — result was: {result}"

    body = dumps[0].read_text(encoding="utf-8")
    assert "exit code : TIMEOUT" in body
    assert "PARTIAL_STDERR" in body and "PARTIAL_STDOUT" in body, (
        "what the child managed to emit before the kill is the only evidence "
        "a hang ever produces")
    assert "900s" in body, "the wall that killed it must be on record"
    assert dumps[0].name in result


def test_a_successful_script_run_writes_nothing(dump_dir):
    """A dump per run would bury the failures and permanently red the harness."""
    rel = "tmp/_dump_probe_ok.py"
    path = sch.PROJECT_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print('fine')\n", encoding="utf-8")
    try:
        sch.run_script_action({"script": rel})
    finally:
        path.unlink(missing_ok=True)

    assert not list(dump_dir.glob("*.log")), "a passing job wrote a failure dump"


# ------------------------------------------------------ the pointer's use ---

def test_the_dump_pointer_survives_the_clip_into_last_result(dump_dir, failing_script):
    """Why the hint goes BEFORE the error text rather than after it.

    The returned string is clipped to RESULT_LIMIT on its way into
    cron_jobs.last_result, and `err` alone is already 300 chars. A pointer
    appended at the end is a pointer that gets cut off — leaving an operator
    with a truncated error and no idea the full one is on disk.
    """
    result = sch.run_script_action({"script": failing_script})
    stored = sch._clip_result(result)
    dump_name = next(iter(dump_dir.glob("*.log"))).name

    assert dump_name in stored, (
        f"the pointer was clipped away; last_result would read: {stored!r}")


# ----------------------------------------------------- the regression pin ---

def test_both_failure_branches_still_call_persist_failure():
    """Structural, because the bug was structural.

    The defect was not a wrong value — it was a call that wasn't there, on a
    path nobody exercised. Asserting on behaviour alone lets the same omission
    return the moment someone restructures this function; this reads the AST so
    dropping either call fails loudly and names which branch went quiet.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(sch.run_script_action)))

    def persists(node) -> bool:
        return any(isinstance(n, ast.Call)
                   and getattr(n.func, "id", "") == "persist_failure"
                   for n in ast.walk(node))

    timeouts = [h for h in ast.walk(tree)
                if isinstance(h, ast.ExceptHandler)
                and h.type is not None
                and "TimeoutExpired" in ast.unparse(h.type)]
    assert timeouts, "run_script_action no longer handles TimeoutExpired"
    assert all(persists(h) for h in timeouts), (
        "the timeout branch stopped dumping — a hang leaves no traceback, so "
        "this branch is the ONLY evidence that class of failure ever produces")

    nonzero = [n for n in ast.walk(tree)
               if isinstance(n, ast.If) and "returncode" in ast.unparse(n.test)]
    assert nonzero, "run_script_action no longer checks returncode"
    assert all(persists(n) for n in nonzero), (
        "the non-zero-exit branch stopped dumping — this is the original "
        "2026-09-13 defect returning")
