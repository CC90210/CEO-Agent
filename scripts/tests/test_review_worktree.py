"""The fixer's isolated PR checkout — and the one way it could destroy real work.

review_fix builds a throwaway `git worktree` for the PR branch instead of
switching the operator's checkout (which is shared with APEX and usually holds
uncommitted work). To keep a per-finding `npm install` off the cron budget it
LINKS node_modules into that worktree rather than copying it.

That link is the hazard. `git worktree remove` walks into a junction and deletes
what it points at, so a teardown in the wrong order erases the operator's real
node_modules — the exact trapdoor recorded in
pattern_worktree_remove_follows_a_junction. These tests pin the ordering and,
more importantly, pin that unlinking never touches the target.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import review_fix  # noqa: E402


def test_unlinking_never_touches_the_target(tmp_path):
    """The whole safety property in one assertion.

    If this ever fails, somebody has replaced an unlink with a recursive delete
    and the next cron pass wipes ~/APPS/oasis-command-center/node_modules.
    """
    real = tmp_path / "node_modules"
    (real / "react").mkdir(parents=True)
    (real / "react" / "index.js").write_text("module.exports = 1", encoding="utf-8")

    link = tmp_path / "worktree" / "node_modules"
    link.parent.mkdir()
    if not review_fix._link_dir(real, link):
        pytest.skip("this platform/user cannot create directory links")

    assert (link / "react" / "index.js").exists(), "the link should resolve"

    review_fix._drop_link(link)

    assert not link.exists(), "the link must be gone"
    assert (real / "react" / "index.js").read_text(encoding="utf-8") == "module.exports = 1", (
        "THE TARGET MUST SURVIVE — unlinking followed the junction and deleted "
        "the operator's real node_modules")


def test_drop_link_is_a_noop_on_a_missing_path(tmp_path):
    review_fix._drop_link(tmp_path / "nope")          # must not raise


def test_drop_link_refuses_to_recurse_into_a_real_directory(tmp_path):
    """Defence in depth: even pointed at a REAL populated directory (not a link)
    it must not delete contents. rmdir fails on a non-empty dir; that failure is
    swallowed on purpose, because destroying data is the worse outcome."""
    real = tmp_path / "node_modules"
    (real / "left").mkdir(parents=True)
    (real / "left" / "keep.txt").write_text("x", encoding="utf-8")

    review_fix._drop_link(real)

    assert (real / "left" / "keep.txt").exists(), "a real directory must be left alone"


def test_teardown_removes_links_before_the_worktree():
    """Ordering is the safety property, not an optimisation.

    Asserted on the source because the failure mode is destructive: a test that
    provoked the wrong order to observe it would be a test that deletes real
    directories when it regresses.
    """
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    fn = src.split("def teardown_pr_checkout")[1].split("\ndef ")[0]
    i_link = fn.index('kind == "link"')
    i_wt = fn.index('kind == "worktree"')
    assert i_link < i_wt, "links must be dropped before any worktree removal"
    assert "_drop_link(path / name)" in fn, (
        "the worktree branch must also unlink defensively before removing")
    assert "rmtree" not in fn, "teardown must never recursively delete"


def test_the_fixer_never_switches_the_operator_checkout():
    """A branch switch in the shared checkout is the thing this design exists to
    avoid. If a branch checkout appears in review_fix, the isolation is gone."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert '"switch"' not in src
    # Reverting the working tree with a pathspec is allowed and used; checking
    # out a BRANCH is not.
    for line in src.splitlines():
        if '"checkout"' in line:
            assert '"--"' in line, f"branch checkout in the shared repo: {line.strip()}"


def test_worktree_is_created_outside_every_repo():
    """A worktree inside the repo it belongs to shows up in that repo's status,
    its test globs and its build output."""
    root = review_fix.WORKTREE_ROOT
    assert not (root / ".git").exists()
    assert str(root).startswith(str(Path.home())), "worktrees live under the user's home"
    for repo_dir in review_fix.REPO_PATHS.values():
        assert not str(root).startswith(str(repo_dir)), (
            f"worktree root {root} is inside the repo {repo_dir}")


def test_worktree_add_is_detached():
    """The branch may already be checked out in one of the eight existing
    worktrees; `git worktree add` refuses a branch that is. Detached HEAD never
    contends, and the push is `HEAD:branch` regardless."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    add_call = src.split('"worktree", "add"')[1][:200]
    assert "--detach" in add_call, "worktree add must be --detach"


def test_push_is_still_branch_scoped_and_never_forced():
    """The isolation change must not have widened what the fixer may push."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    assert '"push", "origin", f"HEAD:{branch}"' in src
    # Scoped to push lines: `worktree remove --force` is legitimate and is the
    # only other --force in the file.
    for line in src.splitlines():
        if '"push"' in line:
            assert "--force" not in line and '"-f"' not in line, (
                f"forced push: {line.strip()}")


@pytest.mark.skipif(not (Path.home() / "APPS" / "oasis-command-center" / ".git").exists(),
                    reason="needs the real oasis-command-center checkout")
def test_prepare_and_teardown_leave_no_worktree_behind():
    """End to end against the real repo: build a worktree for a real remote
    branch, tear it down, and prove `git worktree list` is back where it was."""
    repo_dir = Path.home() / "APPS" / "oasis-command-center"

    def _list():
        r = subprocess.run(["git", "worktree", "list"], cwd=str(repo_dir),
                           capture_output=True, text=True, timeout=120)
        return sorted(line.split()[0] for line in r.stdout.splitlines() if line.strip())

    before = _list()
    work, err, cleanup = review_fix.prepare_pr_checkout(repo_dir, "main")
    if err:
        pytest.skip(f"could not reach origin: {err}")
    try:
        assert work is not None and work.exists()
        assert str(work) not in before, "a NEW worktree, not the operator's"
    finally:
        review_fix.teardown_pr_checkout(repo_dir, cleanup)

    assert _list() == before, "teardown must restore the worktree list exactly"
    assert (repo_dir / "node_modules").is_dir(), "operator node_modules must survive"
