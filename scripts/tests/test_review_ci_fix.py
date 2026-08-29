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


def test_forbidden_edits_agrees_with_the_harvester_on_every_path():
    """Behavioural version of the above: whatever the harvester calls dangerous,
    the fixer refuses to push. Asserted by running both, so it holds even if
    somebody reintroduces a private pattern the source scan does not name."""
    paths = [".github/workflows/ci.yml", "database/x.sql", "migrations/y.sql",
             "scripts/lib/send_gateway.py", "scripts/state/secret_guard.py",
             "app/(dash)/page.tsx", "lib/drips/executor.ts", "README.md",
             "scripts/stripe_tool.py", "components/Button.tsx"]
    refused = set(review_fix.forbidden_edits(paths))
    flagged = {p for p in paths if review_harvest.is_dangerous(p)}
    assert refused == flagged, f"fixer and harvester disagree: {refused ^ flagged}"
    assert flagged, "the fixture must contain at least one dangerous path"


def test_forbidden_edits_catches_the_paths_the_prompt_only_asked_about():
    got = review_fix.forbidden_edits([
        "app/lib/thing.ts",
        ".github/workflows/build.yml",
        "database/turso_migrations/bravo__099_x.sql",
        "scripts/lib/send_gateway.py",
    ])
    assert "app/lib/thing.ts" not in got
    assert ".github/workflows/build.yml" in got
    assert "database/turso_migrations/bravo__099_x.sql" in got
    assert "scripts/lib/send_gateway.py" in got


def test_changed_paths_against_a_real_repo(tmp_path):
    """Driven by REAL git, because the bug this replaces was invisible to a mock.

    The old implementation sliced `line[3:]` off `git status --porcelain` to
    skip the status field. Correct against the raw command — and wrong here,
    because run() returns `stdout.strip()`, which eats the leading space of the
    FIRST line only. `docs/coordination/tools/agent_genome.py` came back as
    `ocs/...`, matched no allowlist, and the PR-diff bound rejected the model's
    correct fix as out-of-bounds on every single run.

    The unit test that was supposed to cover this passed a fixture with no
    leading space to lose. A mock cannot reproduce a defect that lives in the
    seam between two real commands, so this one uses both.
    """
    import subprocess as sp
    sp.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=120)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
        sp.run(["git", "-C", str(tmp_path), "config", key, value], check=True, timeout=60)

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.py").write_text("one\n", encoding="utf-8")
    (tmp_path / "zeta.py").write_text("two\n", encoding="utf-8")
    sp.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, timeout=60)
    sp.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True, timeout=120)

    (tmp_path / "docs" / "alpha.py").write_text("one changed\n", encoding="utf-8")   # modified
    (tmp_path / "brand_new.py").write_text("three\n", encoding="utf-8")              # untracked

    got = review_fix._changed_paths(tmp_path)

    assert "docs/alpha.py" in got, (
        f"the first path must not lose a character — got {got}")
    assert "brand_new.py" in got, "untracked files are edits too"
    assert not any(p.startswith("ocs/") for p in got), "prefix truncation is back"


def test_forbidden_edits_judges_a_renames_destination(tmp_path):
    """A rename INTO a forbidden path must be caught on where the file landed."""
    import subprocess as sp
    sp.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=120)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
        sp.run(["git", "-C", str(tmp_path), "config", key, value], check=True, timeout=60)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.ts").write_text("x\n", encoding="utf-8")
    sp.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, timeout=60)
    sp.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True, timeout=120)

    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "app" / "a.ts").rename(tmp_path / ".github" / "workflows" / "b.yml")

    got = review_fix._changed_paths(tmp_path)
    assert ".github/workflows/b.yml" in got, f"destination must appear: {got}"
    assert review_fix.forbidden_edits(got) == [".github/workflows/b.yml"]


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
    # Sliced to the end of the branch, not a fixed character count — the block
    # grew and a [:700] window silently stopped covering the assertion.
    block = src.split("off_limits = forbidden_edits")[1].split("return out")[0]
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
    assert "_apply_edit(finding, repo_dir, branch, prompt, out, allowed)" in src
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


def test_dangerous_is_checked_before_the_kind_routes_anywhere():
    """A failing_check carries no path today, so is_dangerous never fires on
    one — which is exactly the condition under which an ordering bug stays
    invisible until the harvester starts attaching a path to them."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    fn = src.split("def fix_one(finding")[1].split("\ndef ")[0]
    assert fn.index('finding.get("dangerous")') < fn.index('"failing_check"'), (
        "the dangerous escalation must precede the kind routing")


def test_a_dangerous_failing_check_escalates_rather_than_being_fixed(monkeypatch):
    """Behavioural companion to the ordering assertion above."""
    called = []
    monkeypatch.setattr(review_fix, "fix_failing_check",
                        lambda *a, **kw: called.append(1))
    out = review_fix.fix_one(
        {"thread_id": "t", "kind": "failing_check", "severity": "high",
         "dangerous": True, "path": ".github/workflows/ci.yml"},
        Path("."), "some-branch", dry_run=True)
    assert out["status"] == "escalated"
    assert not called, "a dangerous finding must never reach the fixer"


# ── the PR's own diff is the edit boundary ───────────────────────────────────
#
# Codex adversarial review, 2026-08-28, [high]: fix_failing_check hands an
# attacker-controlled build log to a model holding Read/Edit/Write over the whole
# checkout, and the only deterministic gate afterwards was forbidden_edits —
# which blocks migrations, CI, secrets and money paths and says nothing about the
# other several thousand files. A PR failing CI on purpose, with output shaped
# like repair instructions, could steer an edit into any ordinary production
# file; if the suite still passed it was committed and pushed.

def test_edits_outside_the_prs_own_diff_are_refused():
    allowed = frozenset({"app/lib/thing.ts", "tests/thing.test.ts"})
    changed = ["app/lib/thing.ts", "tests/thing.test.ts",
               "lib/auth/session.ts"]            # the injection's real target
    assert review_fix.edits_outside(changed, allowed) == ["lib/auth/session.ts"]


def test_an_edit_confined_to_the_pr_is_allowed():
    assert review_fix.edits_outside(["app/lib/thing.ts"],
                                    frozenset({"app/lib/thing.ts"})) == []


def test_an_unfetchable_pr_file_list_bounds_nothing_so_nothing_is_edited(monkeypatch):
    """Fail closed. Without the PR's diff there is no boundary to enforce, and an
    unbounded autonomous edit is worse than a missed fix."""
    monkeypatch.setattr(review_fix, "gh", lambda *_a, **_kw: (1, "", "gh: API rate limit"))
    allowed, err = review_fix.pr_changed_paths("CC90210/x", 1)
    assert allowed == frozenset()
    assert "could not list" in err and "rate limit" in err

    monkeypatch.setattr(review_fix, "gh", lambda *_a, **_kw: (0, "   \n  ", ""))
    allowed, err = review_fix.pr_changed_paths("CC90210/x", 1)
    assert allowed == frozenset() and err


def test_the_allowlist_is_fetched_before_any_checkout_is_built():
    """An unbounded edit is not worth building a worktree for, and the gate must
    not sit downstream of work that can fail for unrelated reasons."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    main = src.split("def main() -> None:")[1]
    assert main.index("pr_changed_paths(") < main.index("prepare_pr_checkout(")
    assert 'blocked("unbounded_edit"' in main


def test_both_bounds_are_applied_together_before_the_commit():
    """forbidden paths AND outside-the-PR, checked on what actually changed, and
    both before anything is committed."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    chain = src.split("def _apply_edit")[1].split("\ndef ")[0]
    assert "forbidden_edits(model_changed) + edits_outside(model_changed, allowed)" in chain
    assert chain.index("edits_outside(") < chain.index('"commit"')


def test_the_boundary_reaches_the_ci_path_not_only_review_threads():
    """The CI path is the one with fully attacker-controlled input, so it is the
    one that must not be able to skip the allowlist."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    ci = src.split("def fix_failing_check")[1].split("\ndef ")[0]
    assert "allowed" in ci.split("_apply_edit(")[1][:80], (
        "fix_failing_check must pass the allowlist through")
    assert src.count("_apply_edit(finding, repo_dir, branch, prompt, out, allowed)") == 2



def test_a_new_file_left_by_a_reverted_fix_is_named_not_deleted():
    """A pathspec revert restores tracked files and leaves NEW ones behind.

    In a worktree run that residue dies with the worktree; when the operator's
    own checkout is already on the PR branch it stays in their tree. Deleting
    files is not this process's call — but a silent leftover is how an injected
    file gets committed later by a human who never knew it appeared.
    """
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    chain = src.split("def _apply_edit")[1].split("\ndef ")[0]
    block = chain.split("off_limits = forbidden_edits")[1]
    assert "residue" in block
    assert "NOT auto-removed" in block
    assert "clean" not in block, "must not wipe untracked files — that is not ours to do"


# ── the residue the fixer's own test run leaves ──────────────────────────────

def test_the_test_runs_own_residue_is_not_judged_as_a_model_edit():
    """THE BLOCKER. oasis-command-center tracks
    tests/__pycache__/test_harness_canonical.cpython-312-pytest-9.0.3.pyc in git.
    The baseline suite rewrites it, so the PR-diff bound found an out-of-bounds
    path on EVERY attempt and the run escalated before reaching `git commit`.
    Three correct fixes to the exact file the CI log named are sitting in
    tmp/review_rejected_patches/ because of it.

    A guard that rejects the thing it exists to protect is worse than no guard —
    it fails silently and looks careful doing it.
    """
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    chain = src.split("def _apply_edit")[1].split("\ndef ")[0]

    assert "test_residue = set(_changed_paths(repo_dir))" in chain, (
        "the baseline run's own output must be snapshotted")
    assert chain.index("test_residue = set(") < chain.index("model_changed ="), (
        "the snapshot must be taken BEFORE the model edits anything")
    assert "if p not in test_residue" in chain
    # Every downstream judgement reads model_changed, never the raw tree.
    # Sliced from the line AFTER the definition, since the definition itself is
    # the one legitimate _changed_paths call down here.
    lines = chain.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.strip().startswith("model_changed ="))
    after = "\n".join(lines[i + 1:])
    assert "_changed_paths(repo_dir)" not in after, (
        "nothing below the definition may re-read the tree — that is the bug")


def test_the_test_child_is_told_not_to_write_build_output():
    """Belt to the braces: stop the residue existing rather than only excusing
    it. .pytest_cache in a throwaway worktree also outlives the run as an
    ACL-locked orphan that git can no longer remove."""
    assert review_fix.TEST_CHILD_ENV["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "no:cacheprovider" in review_fix.TEST_CHILD_ENV["PYTEST_ADDOPTS"]
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert src.count("env_extra=TEST_CHILD_ENV") == 2, (
        "both the baseline and the post-edit run must carry it")


def test_the_fixer_proves_a_fix_with_the_suite_ci_actually_runs():
    """oasis-command-center has NO `test` script and 250-plus TypeScript tests.
    The old inference matched its `tests/` directory and ran pytest, 'proving' a
    TypeScript fix with three Python lockstep assertions — and rewriting a
    tracked .pyc while it did. ci.yml runs `npm run test:sunbiz`, which is the
    same suite whose failure the fixer reads."""
    oasis = Path.home() / "APPS" / "oasis-command-center"
    if not oasis.exists():
        import pytest as _pytest
        _pytest.skip("needs the oasis-command-center checkout")
    assert review_fix.detect_test_cmd(oasis) == ["npm", "run", "test:sunbiz"]


def test_a_tests_directory_is_not_evidence_of_pytest(tmp_path):
    """A repo can have a tests/ folder full of TypeScript. Requiring real
    test_*.py files is what stops the fixer running the wrong suite and
    believing the result."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "thing.test.ts").write_text("x", encoding="utf-8")
    assert review_fix.detect_test_cmd(tmp_path) is None

    (tmp_path / "tests" / "test_real.py").write_text("def test_x(): pass", encoding="utf-8")
    cmd = review_fix.detect_test_cmd(tmp_path)
    assert cmd and "pytest" in cmd and "no:cacheprovider" in cmd


def test_nothing_is_built_until_there_is_work():
    """The worktree block used to sit ABOVE the `if not todo` return, so a pass
    with nothing to do built a checkout and returned past the `finally` that
    tears it down. Eight leaked worktrees (~479 MB) accumulated that way, every
    one of them from a pass that did nothing.

    An early return is exactly where a `finally` does not save you.
    """
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    main = src.split("def main() -> None:")[1]
    assert main.index("if not todo:") < main.index("prepare_pr_checkout("), (
        "the worktree must be built only after there is work to do")
    assert main.index("if not todo:") < main.index("pr_changed_paths("), (
        "do not even ask GitHub for the PR's files when there is nothing to fix")
    # and the teardown must still be in a finally
    assert "finally:" in main and main.index("finally:") < main.index("teardown_pr_checkout(")
