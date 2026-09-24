"""deploy/build --dir: only a git worktree of the app's own repo may be built."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "integrations" / "wrangler_tool.py"
SPEC = importlib.util.spec_from_file_location("wrangler_tool_dir_override_test", MODULE_PATH)
assert SPEC and SPEC.loader
wrangler_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrangler_tool)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def repo_with_worktree(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    _git("init", "-q", cwd=app)
    (app / "a.txt").write_text("x", encoding="utf-8")
    _git("add", "a.txt", cwd=app)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init", cwd=app)
    worktree = tmp_path / "snapshot"
    _git("worktree", "add", "-q", "--detach", str(worktree), "HEAD", cwd=app)
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    _git("init", "-q", cwd=stranger)
    registry = {"apps": {"demo": {"dir": str(app)}}}
    yield registry, app, worktree, stranger
    wrangler_tool._DIR_OVERRIDE.clear()


def test_no_dir_builds_the_registered_checkout(repo_with_worktree):
    registry, app, _, _ = repo_with_worktree
    wrangler_tool._set_dir_override(registry, "demo", None)
    assert wrangler_tool._app(registry, "demo")["path"] == app


def test_a_worktree_of_the_same_repo_is_built(repo_with_worktree):
    registry, _, worktree, _ = repo_with_worktree
    wrangler_tool._set_dir_override(registry, "demo", str(worktree))
    assert wrangler_tool._app(registry, "demo")["path"] == worktree.resolve()


def test_an_unrelated_repo_is_refused(repo_with_worktree):
    registry, app, _, stranger = repo_with_worktree
    with pytest.raises(RuntimeError, match="is not a git worktree of"):
        wrangler_tool._set_dir_override(registry, "demo", str(stranger))
    assert wrangler_tool._app(registry, "demo")["path"] == app


def test_a_plain_folder_is_refused(repo_with_worktree, tmp_path):
    registry, _, _, _ = repo_with_worktree
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(RuntimeError, match="is not a git worktree of"):
        wrangler_tool._set_dir_override(registry, "demo", str(plain))
