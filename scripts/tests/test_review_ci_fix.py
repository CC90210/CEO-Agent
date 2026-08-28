"""Red CI is now diagnosed from the job log, and rule 5 is finally enforced.

Two changes, one theme — the fixer used to trust a description of reality
instead of reading it.

  * A `failing_check` finding was escalated on sight as "not auto-fixable from a
    review comment". True, and beside the point: the comment is not the
    evidence, the job log is, and `gh` can fetch it. On the live queue of
    2026-08-28, six of the eight PRs that survive the recency bound carry a red
    check and nothing but LOW review threads — escalate-on-sight meant the loop
    touched nothing on six of eight.
  * "Never edit database/, .github/workflows/, send_gateway.py …" was rule 5 of
    the model's prompt and nothing else. A prompt is a request. Whether those
    paths were edited is now checked against what the edit ACTUALLY changed,
    before anything is committed — which matters far more once a red BUILD is
    being fixed, since the cause of one lives in a workflow file often enough.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import review_fix  # noqa: E402
import review_harvest  # noqa: E402


def _log(*lines: str) -> str:
    """Shape a runner log the way `gh run view --log-failed` emits it."""
    return "\n".join(
        f"build\tUNKNOWN STEP\t2026-08-28T04:09:{i:02d}.4140881Z {line}"
        for i, line in enumerate(lines))


# ── reading the log ──────────────────────────────────────────────────────────

def test_distil_keeps_the_failure_and_drops_the_runner_chatter():
    raw = _log(
        "##[group]Operating System",
        "Ubuntu",
        "##[endgroup]",
        "[command]/usr/bin/git version",
        "Download action repository 'actions/checkout@v4'",
        "FAILED in tests/founder-meeting-calendar.test.ts (exit 1)",
        "13 of 188 passed before it.",
        "##[error]Process completed with exit code 1.",
    )
    out = review_fix.distil_ci_log(raw)

    assert "founder-meeting-calendar.test.ts" in out, "the failure must survive"
    assert "##[error]" in out
    assert "Download action repository" not in out, "runner chatter is noise"
    assert "[command]/usr/bin/git" not in out
    assert "2026-08-28T04:09" not in out, "timestamps and the job/step prefix are stripped"


def test_distil_anchors_on_the_LAST_error():
    """A build prints its failure at the end; an earlier ##[error] is usually the
    same failure reported by an inner tool."""
    raw = _log(
        "##[error]an early warning nobody cares about",
        *[f"filler line {i}" for i in range(400)],
        "TypeError: cannot read property 'id' of undefined",
        "##[error]Process completed with exit code 1.",
    )
    out = review_fix.distil_ci_log(raw)
    assert "TypeError" in out
    assert "an early warning" not in out, "anchored on the last error, not the first"


def test_distil_falls_back_to_the_tail_when_there_is_no_error_marker():
    """A timeout or a killed runner never emits ##[error]. Returning nothing
    there would silently turn a red build into 'no readable output' and escalate
    a case the log could have explained."""
    raw = _log(*[f"line {i}" for i in range(300)], "The job running has exceeded the maximum")
    out = review_fix.distil_ci_log(raw)
    assert "exceeded the maximum" in out
    assert "line 299" in out


def test_distil_is_bounded():
    raw = _log(*[f"x{i} " + "y" * 200 for i in range(500)], "##[error]boom")
    assert len(review_fix.distil_ci_log(raw)) <= review_fix.CI_CONTEXT_CHARS


def test_distil_of_an_empty_log_is_empty_not_a_crash():
    assert review_fix.distil_ci_log("") == ""
    assert review_fix.distil_ci_log("   \n  \n") == ""


def test_a_check_with_no_run_url_reports_why(monkeypatch):
    """Unreadable still escalates. What changed is that UNREAD is no longer the
    same as unreadable — so the reason has to be specific."""
    log, err = review_fix.ci_failure_context("CC90210/x", "Check 'build' is fail.")
    assert log == ""
    assert "no run URL" in err


def test_a_run_that_cannot_be_fetched_escalates_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(review_fix, "gh", lambda *_a, **_kw: (1, "", "gh: not authenticated"))
    log, err = review_fix.ci_failure_context(
        "CC90210/x", "https://github.com/CC90210/x/actions/runs/123/job/456")
    assert log == ""
    assert "123" in err and "not authenticated" in err


def test_run_url_is_parsed_with_and_without_the_job_segment():
    assert review_fix.RUN_URL_RE.search(
        "see https://github.com/o/r/actions/runs/33140933390").group(1) == "33140933390"
    assert review_fix.RUN_URL_RE.search(
        "https://github.com/o/r/actions/runs/999/job/111").group(1) == "999"


# ── rule 5, enforced on what actually changed ────────────────────────────────

def test_forbidden_edits_uses_the_harvesters_definition():
    """One definition of dangerous. A second copy in the fixer would drift from
    the rule the harvester flags on, and the drift would be invisible until
    something got pushed."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert "is_dangerous" in src, "must import the harvester's predicate"
    assert "DANGER_PATHS = " not in src, "must not carry its own copy of the pattern"


def test_forbidden_edits_agrees_with_the_harvester_on_every_path(monkeypatch, tmp_path):
    """Behavioural version of the above: whatever the harvester calls dangerous,
    the fixer refuses to push. Asserted by running both, so it holds even if
    somebody reintroduces a private pattern the source scan does not name."""
    paths = [".github/workflows/ci.yml", "database/x.sql", "migrations/y.sql",
             "scripts/lib/send_gateway.py", "scripts/state/secret_guard.py",
             "app/(dash)/page.tsx", "lib/drips/executor.ts", "README.md",
             "scripts/stripe_tool.py", "components/Button.tsx"]
    monkeypatch.setattr(review_fix, "run",
                        lambda *_a, **_kw: (0, "\n".join(f" M {p}" for p in paths), ""))
    refused = set(review_fix.forbidden_edits(tmp_path))
    flagged = {p for p in paths if review_harvest.is_dangerous(p)}
    assert refused == flagged, f"fixer and harvester disagree: {refused ^ flagged}"
    assert flagged, "the fixture must contain at least one dangerous path"


def test_forbidden_edits_catches_the_paths_the_prompt_only_asked_about(monkeypatch, tmp_path):
    changed = [
        " M app/lib/thing.ts",
        " M .github/workflows/build.yml",
        "?? database/turso_migrations/bravo__099_x.sql",
        " M scripts/lib/send_gateway.py",
    ]
    monkeypatch.setattr(review_fix, "run",
                        lambda *_a, **_kw: (0, "\n".join(changed), ""))
    got = review_fix.forbidden_edits(tmp_path)
    assert "app/lib/thing.ts" not in got
    assert ".github/workflows/build.yml" in got
    assert "database/turso_migrations/bravo__099_x.sql" in got
    assert "scripts/lib/send_gateway.py" in got


def test_forbidden_edits_reads_the_destination_of_a_rename(monkeypatch, tmp_path):
    """`R  a.ts -> .github/workflows/b.yml` must be judged on where the file
    LANDED. Judging the source path would wave the rename straight through."""
    monkeypatch.setattr(review_fix, "run",
                        lambda *_a, **_kw: (0, 'R  app/a.ts -> .github/workflows/b.yml', ""))
    assert review_fix.forbidden_edits(tmp_path) == [".github/workflows/b.yml"]


def test_the_forbidden_check_runs_before_the_commit():
    """Order is the whole guarantee. Checking after the commit would leave the
    fixer one push away from shipping a migration."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    chain = src.split("def _apply_edit")[1].split("\ndef ")[0]
    assert chain.index("forbidden_edits(") < chain.index('"commit"'), (
        "forbidden-path check must precede the commit")
    assert chain.index("forbidden_edits(") < chain.index('"push"')


def test_a_forbidden_edit_is_preserved_not_destroyed():
    """Same rule as a test-failure revert: reverting is fine, losing the work is
    not (Codex P1, 2026-07-30)."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    block = src.split("off_limits = forbidden_edits")[1][:700]
    assert "_save_patch" in block, "save the diff before reverting it"
    assert "escalated" in block


# ── the safety chain has exactly one implementation ─────────────────────────

def test_both_fix_paths_go_through_the_same_safety_chain():
    """baseline → edit → changed? → forbidden? → tests → commit → push exists
    once. A CI-specific copy is how one of those steps goes missing for one
    kind of finding only."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    calls = src.count("spawn_claude_editor(prompt, repo_dir)")
    assert calls == 1, f"the editor is spawned in exactly one place, found {calls}"
    assert src.count('run(["git", "commit"') == 1
    assert "_apply_edit(finding, repo_dir, branch, prompt, out)" in src
    ci = src.split("def fix_failing_check")[1].split("\ndef ")[0]
    assert "_apply_edit(" in ci, "the CI path must not hand-roll the chain"


def test_failing_checks_are_no_longer_hardcoded_escalations():
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert 'not auto-fixable from a\n' not in src
    main = src.split("def main() -> None:")[1]
    assert '"status": "escalated"' not in main, (
        "main must not pre-decide a finding's outcome; fix_one does")
    assert "fix_failing_check" in src.split("def fix_one")[1]


def test_red_builds_are_worked_before_style_nits():
    """--max bounds the pass. A chatty PR would otherwise spend the whole budget
    on LOW review threads while the branch stays red."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert "(failing + threads)[:args.max]" in src


def test_ci_prompt_frames_the_log_as_untrusted():
    """A build log contains arbitrary third-party output — including anything a
    dependency chose to print. It is evidence, never instructions."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    ci = src.split("def fix_failing_check")[1].split("\ndef ")[0]
    assert "UNTRUSTED" in ci
    assert "never" in ci and "instructions" in ci


def test_dangerous_predicate_still_covers_what_this_test_assumes():
    """If DANGER_PATHS ever narrows, the assertions above quietly stop meaning
    anything. Pin the inputs they depend on."""
    for path in (".github/workflows/build.yml", "database/migrate.sql",
                 "scripts/lib/send_gateway.py", "scripts/state/exec_guard.py"):
        assert review_harvest.is_dangerous(path), path
    for path in ("app/page.tsx", "scripts/review_loop.py"):
        assert not review_harvest.is_dangerous(path), path
