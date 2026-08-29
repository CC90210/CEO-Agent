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


def _sandbox_repo(tmp_path: Path) -> Path:
    """A throwaway repo with an `origin` and a populated node_modules.

    NEVER the operator's checkout. The first version of this test ran
    prepare/teardown against ~/APPS/oasis-command-center, and on 2026-08-28 a
    deliberate mutation — swapping the unlink for shutil.rmtree, to prove the
    guard above catches it — was executed by that test against the real
    directory and emptied 491 packages out of it.

    The guard was correct and the mutation check was the right instinct. The
    defect was the blast radius: an end-to-end test whose fixture is production.
    A destructive failure mode must be exercised somewhere it can only destroy
    the fixture.
    """
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, timeout=120)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, timeout=120)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(work), "config", key, value], check=True, timeout=60)
    (work / "app.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True, timeout=60)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "init"], check=True, timeout=120)
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"],
                   check=True, timeout=120)
    packages = work / "node_modules" / "react"
    packages.mkdir(parents=True)
    (packages / "index.js").write_text("module.exports = 1", encoding="utf-8")
    return work


def test_prepare_and_teardown_leave_no_worktree_behind(tmp_path):
    """End to end on a sandbox repo: build a worktree for a remote branch, tear
    it down, and prove both the worktree list AND the linked directory's
    CONTENTS are exactly where they started."""
    repo_dir = _sandbox_repo(tmp_path)

    def _list():
        r = subprocess.run(["git", "worktree", "list"], cwd=str(repo_dir),
                           capture_output=True, text=True, timeout=120)
        return sorted(line.split()[0] for line in r.stdout.splitlines() if line.strip())

    before = _list()
    work, err, cleanup = review_fix.prepare_pr_checkout(repo_dir, "main")
    if err:
        pytest.fail(f"prepare failed on a sandbox repo: {err}")
    try:
        assert work is not None and work.exists()
        assert str(work) not in before, "a NEW worktree, not the caller's"
        assert (work / "app.txt").read_text(encoding="utf-8") == "hello", (
            "the worktree must hold the branch's content")
    finally:
        review_fix.teardown_pr_checkout(repo_dir, cleanup)

    assert _list() == before, "teardown must restore the worktree list exactly"
    # CONTENTS, not existence. `.is_dir()` is true of a directory that has just
    # been emptied — which is precisely how the real deletion went unnoticed.
    assert (repo_dir / "node_modules" / "react" / "index.js").read_text(
        encoding="utf-8") == "module.exports = 1", (
        "the linked directory's contents must survive teardown")


def test_no_test_in_this_file_touches_a_real_checkout():
    """The rule that keeps the above true.

    Every path this file operates on must come from tmp_path. A future test that
    reaches for ~/APPS to be 'more realistic' re-arms a destructive failure mode
    against production, which is what happened once already."""
    src = Path(__file__).read_text(encoding="utf-8")
    body = src.split("def test_no_test_in_this_file_touches_a_real_checkout")[0]
    for marker in ('"APPS"', "APPS /", 'Path.home() / "APPS'):
        assert marker not in body, (
            f"a test in this file reaches into a real checkout ({marker})")


# ── sweeping what a killed run left behind ───────────────────────────────────

def test_sweep_only_touches_this_repos_worktrees(tmp_path, monkeypatch):
    """teardown runs in a `finally`, which covers an exception and not a
    SIGKILL — and this fixer is spawned by a cron with a hard timeout, so being
    killed mid-run is routine. Three full checkouts accumulated within an hour
    of the worktree path shipping. The sweep is bounded by NAME so it can never
    reach a directory belonging to something else."""
    root = tmp_path / "wt"
    root.mkdir()
    monkeypatch.setattr(review_fix, "WORKTREE_ROOT", root)

    mine = root / "myrepo-old-branch"
    theirs = root / "someone-elses-tool-cache"
    for d in (mine, theirs):
        d.mkdir()
        (d / "f.txt").write_text("x", encoding="utf-8")

    seen = []
    monkeypatch.setattr(review_fix, "run",
                        lambda cmd, cwd, **kw: (seen.append(cmd), (1, "", "not a working tree"))[1])
    review_fix.sweep_stale_worktrees(tmp_path / "myrepo", max_age_h=0)

    swept = [c[-1] for c in seen if "remove" in c]
    assert any("myrepo-old-branch" in s for s in swept)
    assert not any("someone-elses" in s for s in swept), (
        "the sweep must be confined to this repo's own leftovers")
    assert theirs.exists()


def test_purge_refuses_anything_it_cannot_fully_inspect(tmp_path, monkeypatch):
    """os.walk SWALLOWS scandir errors unless handed onerror, so a directory
    that cannot even be listed was walked past and the answer came back 'no
    links here, safe to delete'. The entries most likely to hide something are
    exactly the ones that cannot be read. Found live: a locked .pytest_cache
    inside an orphaned worktree."""
    import os as _os
    root = tmp_path / "wt"
    (root / "victim" / "locked").mkdir(parents=True)
    monkeypatch.setattr(review_fix, "WORKTREE_ROOT", root)

    real_walk = _os.walk

    def _walk(path, followlinks=False, onerror=None):
        for entry in real_walk(path, followlinks=followlinks, onerror=onerror):
            yield entry
        if onerror:
            onerror(PermissionError(13, "Access is denied"))

    monkeypatch.setattr(review_fix.os, "walk", _walk)

    assert review_fix._has_reparse_point(root / "victim") is True
    assert review_fix._purge_orphan_tree(root / "victim") is False
    assert (root / "victim").exists(), "an uninspectable tree must survive"


def test_purge_refuses_a_path_outside_the_worktree_root(tmp_path, monkeypatch):
    """The one containment rule. A recursive delete is allowed here and nowhere
    else in this file, so the boundary is checked rather than assumed."""
    root = tmp_path / "wt"
    root.mkdir()
    monkeypatch.setattr(review_fix, "WORKTREE_ROOT", root)

    outsider = tmp_path / "someones_repo"
    (outsider / "src").mkdir(parents=True)
    (outsider / "src" / "keep.py").write_text("1", encoding="utf-8")

    assert review_fix._purge_orphan_tree(outsider) is False
    assert review_fix._purge_orphan_tree(root / "a" / "b") is False, "not a direct child"
    assert (outsider / "src" / "keep.py").exists()


def test_teardown_does_not_prune_after_a_failed_removal():
    """Pruning after a failed removal is what MANUFACTURES orphans: git forgets
    the registration, the directory survives, and no git command can reach it
    again. Asserted on the source — provoking it for real means deliberately
    creating an unremovable worktree."""
    src = Path(review_fix.__file__).read_text(encoding="utf-8")
    fn = src.split("def teardown_pr_checkout")[1].split("\ndef ")[0]
    assert "stuck" in fn
    prune_at = fn.index('"prune"')
    assert "if not stuck:" in fn[:prune_at], "prune must be guarded by a clean removal"
    assert "file=sys.stderr" in fn, "a failed removal must be said out loud"


def test_an_undeletable_leftover_does_not_wedge_the_branch(tmp_path, monkeypatch):
    """One ACL-locked .pytest_cache made `git worktree add` fail with "already
    exists" — permanently, for that branch, on every subsequent pass. Found by
    running the fixer for real, not by reading it.

    A leftover the fixer cannot delete is a disk problem. Refusing to work on
    that branch ever again is an outage.
    """
    repo_dir = _sandbox_repo(tmp_path)
    root = tmp_path / "wt"
    root.mkdir()
    monkeypatch.setattr(review_fix, "WORKTREE_ROOT", root)

    # An undeletable squatter on the name prepare_pr_checkout wants.
    squatter = root / f"{repo_dir.name}-main"
    squatter.mkdir()
    (squatter / "keep.txt").write_text("locked", encoding="utf-8")
    monkeypatch.setattr(review_fix, "_purge_orphan_tree", lambda _p: False)

    work, err, cleanup = review_fix.prepare_pr_checkout(repo_dir, "main")
    try:
        assert err is None, f"an undeletable leftover must not be fatal: {err}"
        assert work is not None and work.exists()
        assert work != squatter, "must not reuse a tree it could not clear"
        assert (work / "app.txt").read_text(encoding="utf-8") == "hello"
    finally:
        review_fix.teardown_pr_checkout(repo_dir, cleanup)

    assert squatter.exists(), "the squatter is left alone, not force-deleted"
