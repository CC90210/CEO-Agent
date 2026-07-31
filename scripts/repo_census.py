#!/usr/bin/env python3
"""Census every git repo AND worktree that an IDE could be counting.

WHY THIS EXISTS
---------------
2026-07-29: CC's IDE showed "1,671 changes" while `git status` in the repo said
0. It took four rounds of back-and-forth to find the cause, because every check
was run *inside the repo directory* and the culprit was somewhere else entirely:
a stale git worktree registered at `%TEMP%/bravo-outreach-alert-hotfix`. Windows
Temp cleanup had deleted its files; the registration survived, so git reported
1,671 tracked files as deleted — against the same `.git`, invisible to any
status check run from the repo root.

`git worktree list` was the command that answered it. This script makes that
one command, across every repo on the machine.

THREE NUMBERS THAT LOOK ALIKE AND ARE NOT
-----------------------------------------
  pending   uncommitted edits                     `git status`
  unpushed  committed, absent from every remote   `git branch -r --contains HEAD`
  unmerged  on a remote, invisible to the default branch

Only the first two are ever "work at risk". Conflating them is what produced a
false "everything is pushed" report earlier the same day: `git log @{u}..`
returns 0 when a branch has NO upstream — the command errors and the count reads
zero. This script never uses that shortcut.

USAGE
  python scripts/repo_census.py                 # everything under the user home
  python scripts/repo_census.py --root ~/APPS   # narrower sweep
  python scripts/repo_census.py --problems-only
  python scripts/repo_census.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Trees that are machinery, not work. They generate enormous phantom counts —
# the plugin cache alone carried ~81,000 pending files across throwaway clones.
NOISE_MARKERS = (
    "/node_modules/", "/.venv/", "/venv/",
    "/.claude/plugins/cache/",     # plugin install scratch, regenerable
    "/pytest-of-",                  # test fixtures
    "/AppData/Roaming/",
)


def run(args: list[str], cwd: Path) -> tuple[str, int]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
        return p.stdout.strip(), p.returncode
    except (OSError, subprocess.SubprocessError):
        return "", 1


def is_noise(path: Path) -> bool:
    rel = path.as_posix()
    return any(m in rel for m in NOISE_MARKERS)


def find_repos(root: Path) -> list[Path]:
    repos: list[Path] = []
    for gitdir in root.rglob(".git"):
        if is_noise(gitdir):
            continue
        repo = gitdir.parent
        if repo not in repos:
            repos.append(repo)
    return sorted(repos)


def survey(repo: Path) -> dict | None:
    branch, rc = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    if rc != 0 or not branch:
        return None

    status, _ = run(["git", "status", "--short"], repo)
    pending = len([ln for ln in status.splitlines() if ln.strip()])

    # NOT `git log @{u}..` — that silently reads 0 when no upstream is set.
    contains, _ = run(["git", "branch", "-r", "--contains", "HEAD"], repo)
    if contains.strip():
        unpushed = 0
    else:
        out, _ = run(["git", "log", "--oneline", "HEAD", "--not", "--remotes"], repo)
        unpushed = len(out.splitlines())

    default = "main"
    if not run(["git", "rev-parse", "--verify", "origin/main"], repo)[0]:
        default = "master"
    out, _ = run(["git", "log", "--oneline", f"origin/{default}..HEAD"], repo)
    unmerged = len(out.splitlines())

    # The blind spot that started all this.
    wt_out, _ = run(["git", "worktree", "list"], repo)
    worktrees = [ln.strip() for ln in wt_out.splitlines()[1:] if ln.strip()]
    stale: list[str] = []
    for line in worktrees:
        wt_path = Path(line.split()[0])
        if not wt_path.exists():
            stale.append(line + "   << DIRECTORY MISSING")
        elif "Temp" in wt_path.as_posix() or "tmp" in wt_path.as_posix():
            stale.append(line + "   << lives in a temp dir; will vanish on cleanup")

    return {
        "repo": repo.as_posix(),
        "branch": branch,
        "pending": pending,
        "unpushed": unpushed,
        "unmerged": unmerged,
        "worktrees": worktrees,
        "suspect_worktrees": stale,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path.home()), help="tree to sweep")
    ap.add_argument("--problems-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = [r for r in (survey(p) for p in find_repos(Path(args.root).expanduser())) if r]

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    problems = [r for r in rows if r["pending"] or r["unpushed"] or r["suspect_worktrees"]]
    shown = problems if args.problems_only else rows

    print(f"{'REPO':<54} {'BRANCH':<30} {'PEND':>5} {'UNPUSH':>7} {'UNMERGED':>9}")
    print("-" * 110)
    home = Path.home().as_posix()
    for r in shown:
        name = r["repo"].replace(home, "~")
        print(f"{name:<54} {r['branch']:<30} {r['pending']:>5} "
              f"{r['unpushed']:>7} {r['unmerged']:>9}")
        for s in r["suspect_worktrees"]:
            print(f"      !! {s}")
    print("-" * 110)

    stale_total = sum(len(r["suspect_worktrees"]) for r in rows)
    if stale_total:
        print(f"{stale_total} suspect worktree(s) — a stale one reports every tracked file "
              f"as deleted and is invisible to `git status` run from the repo root.")
    if problems:
        print(f"{len(problems)} repo(s) with pending edits or unpushed commits.")
    else:
        print("CLEAN: no pending edits, no unpushed commits, no suspect worktrees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
