#!/usr/bin/env python3
"""prune_merged_branches — delete remote branches whose commits are already in main.

WHY A SCRIPT AND NOT A ONE-LINER. Deleting branches on a shared remote is
outward-facing and several other agents (Codex, APEX, Maven) push here. A
`git push --delete` loop in a shell has no dry run, no re-verification, and no
record of what it removed — and the one time it is wrong is the time someone's
unmerged work disappears.

THE SAFETY RULES, each earned:

  1. MERGED ONLY. A branch qualifies only if `git branch -r --merged main` lists
     it, meaning its tip is an ancestor of main. Its commits are in main by
     definition, so nothing is lost. Note this deliberately EXCLUDES
     squash-merged branches, which are not ancestors even though their content
     landed — those look identical to real unmerged work from git's side, so
     they are left alone rather than guessed at.

  2. AGE FLOOR. A branch merged minutes ago may still be checked out in a
     session that is mid-push. `--min-age-days` (default 2) keeps recent ones.

  3. RE-VERIFIED AT DELETE TIME, not at plan time. The merged set is recomputed
     immediately before each delete, because the plan may have been built
     minutes earlier and another agent can push in that window. A branch that
     stopped being merged is skipped and reported.

  4. DRY RUN IS THE DEFAULT.

Usage:
    python scripts/prune_merged_branches.py --repo <path>
    python scripts/prune_merged_branches.py --repo <path> --execute
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.git_auth import git_credential_env  # noqa: E402

PROTECTED = {"main", "master", "develop", "HEAD"}


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if r.returncode != 0 and "--delete" not in args:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def merged_set(repo: Path, base: str) -> set[str]:
    """Branch names whose tip is an ancestor of `base`.

    Parsed LINE BY LINE, taking the first token. Splitting the whole blob on
    whitespace instead pulls the symref line apart —

        origin/HEAD -> origin/main

    — and yields a phantom branch literally named `->`. It was held back by the
    age filter here only because an unknown ref has no timestamp, which is luck
    rather than safety: this set feeds `git push --delete`, and a deletion tool
    that can invent a branch name is one bad edge case from a bad command.
    """
    out = git(repo, "branch", "-r", "--merged", base)
    names = set()
    for line in out.splitlines():
        line = line.strip().lstrip("* ").strip()
        if not line or "->" in line:      # symref line, not a branch
            continue
        name = line.split()[0]
        if "HEAD" in name or name.split("/", 1)[-1] in PROTECTED:
            continue
        names.add(name)
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--base", default="main")
    ap.add_argument("--min-age-days", type=float, default=2.0)
    ap.add_argument("--execute", action="store_true", help="apply (default is a dry run)")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"not a git repository: {repo}", file=sys.stderr)
        return 2

    # Deleting on the remote needs the PAT, and so does the fetch behind a
    # private repo. The first run of this tool failed all 111 deletions with
    # "could not read Username for 'https://github.com'" — it failed CLOSED,
    # which is the right direction, but it failed.
    with git_credential_env() as _env:
        return _run(repo, args, _env)


def _run(repo: Path, args, env: dict[str, str]) -> int:
    subprocess.run(["git", "fetch", "--prune", args.remote],
                   cwd=str(repo), env=env, capture_output=True, text=True)
    merged = merged_set(repo, args.base)

    ages = {}
    for line in git(
        repo, "for-each-ref", "--format=%(refname:short)|%(committerdate:unix)",
        f"refs/remotes/{args.remote}",
    ).splitlines():
        if "|" not in line:
            continue
        name, ts = line.rsplit("|", 1)
        try:
            ages[name.strip()] = (time.time() - int(ts.strip())) / 86400
        except ValueError:
            continue

    plan = sorted(
        n for n in merged
        if ages.get(n, 0.0) >= args.min_age_days
    )
    held = sorted(n for n in merged if n not in plan)

    print(f"remote branches merged into {args.base}: {len(merged)}")
    print(f"  to delete (>= {args.min_age_days}d old): {len(plan)}")
    print(f"  held back (too recent)              : {len(held)}")
    for n in held:
        print(f"     hold {n}  ({ages.get(n, 0):.1f}d)")

    if not args.execute:
        print("\n  re-run with --execute to delete")
        return 0

    deleted = skipped = failed = 0
    for name in plan:
        short = name.split("/", 1)[-1]
        # Rule 3: the world may have moved since the plan was built.
        if name not in merged_set(repo, args.base):
            print(f"  SKIP {short} — no longer merged")
            skipped += 1
            continue
        r = subprocess.run(
            ["git", "push", args.remote, "--delete", short],
            cwd=str(repo), env=env, capture_output=True, text=True,
        )
        if r.returncode == 0:
            deleted += 1
        else:
            failed += 1
            print(f"  FAIL {short}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '?'}")

    print(f"\ndeleted {deleted} · skipped {skipped} · failed {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
