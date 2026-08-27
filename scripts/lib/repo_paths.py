"""repo_paths — repo/path resolution and glob coverage. NO database, NO subprocess.

This module exists for two reasons, both learned the hard way.

1. SPEED. scripts/state/coord_guard.py runs on EVERY Edit/Write. Its first
   version imported coord_claim, which imports db_turso, which opens a Turso
   connection at import time: 4-5 SECONDS per edit, even on a cache hit. A guard
   that slow gets switched off, and a switched-off guard is the failure this
   whole subsystem exists to correct.

2. WORKTREES. The slug was originally the top-level directory name, taken from
   `git rev-parse --show-toplevel`. APEX (Adon's agent) reported on 2026-08-27
   that its machine holds **85 checkouts of oasis-command-center**, nearly all
   linked worktrees. `--show-toplevel` returns the WORKTREE path, so those 85
   checkouts produced 85 different slugs, of which exactly one matched Bravo's.
   Leases would be written, acquire would report success, conflicts would return
   empty, and NOTHING would be protected for 84 of 85 working directories —
   while both agents believed there was a gate. Reproduced locally before
   accepting the report: a `git worktree add` of this very repo resolved to
   'wt-probe' instead of 'Business-Empire-Agent'.

   The slug is now derived from `remote.origin.url`, resolved through the
   worktree's commondir, per the algorithm in APEX's contract §3.1. That is
   agreed on both sides — it MUST NOT be changed unilaterally.

Reading git's plumbing files directly also removed the last subprocess from the
hot path, so this is faster than the version it replaced.
"""
from __future__ import annotations

import fnmatch
import os
import posixpath
import re
import sys
from pathlib import Path

_root_cache: dict[str, tuple[Path, Path] | None] = {}
_slug_cache: dict[str, str] = {}

# `url = git@github.com:CC90210/oasis-command-center.git` and the https/ssh forms.
_URL_RE = re.compile(r"^\s*url\s*=\s*(.+?)\s*$", re.M)
_ORIGIN_RE = re.compile(r'^\s*\[remote\s+"origin"\]\s*$', re.M)


def _find_dot_git(start: Path) -> Path | None:
    """Nearest ancestor containing a `.git` entry (file or directory)."""
    probe = start if start.is_dir() else start.parent
    for d in [probe, *probe.parents]:
        if (d / ".git").exists():
            return d
    return None


def _worktree_and_common(start: Path) -> tuple[Path, Path] | None:
    """(worktree_root, common_git_dir) — APEX contract §3.1 steps 1-2.

    A linked worktree's `.git` is a FILE containing `gitdir: <path>`; that dir
    holds a `commondir` file pointing back at the main repo's .git. Resolving it
    is what makes every worktree of a repo agree on one identity.
    """
    key = str(start)
    if key in _root_cache:
        return _root_cache[key]

    result: tuple[Path, Path] | None = None
    worktree = _find_dot_git(start)
    if worktree is not None:
        dot_git = worktree / ".git"
        try:
            if dot_git.is_dir():
                result = (worktree, dot_git)
            else:
                text = dot_git.read_text(encoding="utf-8", errors="ignore").strip()
                gitdir = text.partition("gitdir:")[2].strip() if "gitdir:" in text else ""
                if gitdir:
                    gd = Path(gitdir)
                    if not gd.is_absolute():
                        gd = (dot_git.parent / gd)
                    gd = Path(os.path.normpath(str(gd)))
                    common = gd / "commondir"
                    if common.exists():
                        rel = common.read_text(encoding="utf-8", errors="ignore").strip()
                        cd = Path(rel)
                        if not cd.is_absolute():
                            cd = gd / cd
                        result = (worktree, Path(os.path.normpath(str(cd))))
                    else:
                        result = (worktree, gd)
        except Exception:  # noqa: BLE001
            result = (worktree, worktree / ".git")

    _root_cache[key] = result
    return result


def _origin_url(common_dir: Path) -> str | None:
    """The [remote "origin"] url from a git config, without invoking git."""
    cfg = common_dir / "config"
    try:
        text = cfg.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return None
    m = _ORIGIN_RE.search(text)
    if not m:
        return None
    # the url belongs to the first key line after the [remote "origin"] header
    section = text[m.end():]
    nxt = re.search(r"^\s*\[", section, re.M)
    if nxt:
        section = section[:nxt.start()]
    u = _URL_RE.search(section)
    return u.group(1) if u else None


def slug_from_url(url: str) -> str:
    """Last path segment, `.git` stripped, lowercased — contract §3.1 step 4.

    Handles https, ssh://, and the scp-like `git@host:owner/repo.git` form,
    where the separator before the path is a colon rather than a slash.
    """
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    tail = u.rsplit("/", 1)[-1]
    if ":" in tail:            # git@github.com:owner/repo -> repo
        tail = tail.rsplit(":", 1)[-1]
    return tail.lower()


def repo_root(start: str | Path | None = None) -> Path | None:
    """The WORKTREE root containing `start` (where repo-relative paths anchor)."""
    pair = _worktree_and_common(Path(start or Path.cwd()))
    return pair[0] if pair else None


def repo_slug(root: Path) -> str:
    """Canonical repo identity, shared by every worktree of the same remote.

    Falls back to the directory name only when there is no origin remote, and
    SAYS SO on stderr — contract §3.1 step 5. A silent fallback here is a silent
    divergence between the two agents, which is the whole bug this replaced.
    """
    key = str(root)
    if key in _slug_cache:
        return _slug_cache[key]
    slug = None
    pair = _worktree_and_common(root)
    if pair:
        url = _origin_url(pair[1])
        if url:
            slug = slug_from_url(url)
    if slug is None:
        slug = root.name.lower()
        print(f"[repo_paths] WARN no origin remote for {root} — falling back to "
              f"directory name {slug!r}. A peer resolving this repo by its remote "
              f"will NOT match; leases here protect nothing.", file=sys.stderr)
    _slug_cache[key] = slug
    return slug


def resolve(path: str | Path) -> tuple[str, str] | None:
    """Absolute-or-relative path -> (repo_slug, repo-relative POSIX path)."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        p = Path(os.path.normpath(str(p)))
    except Exception:  # noqa: BLE001
        return None
    pair = _worktree_and_common(p)
    if pair is None:
        return None
    worktree = pair[0]
    try:
        rel = p.relative_to(worktree)
    except ValueError:
        try:
            rel = p.resolve().relative_to(worktree.resolve())
        except Exception:  # noqa: BLE001
            return None
    return repo_slug(worktree), rel.as_posix()


def covers(path_glob: str, candidate: str) -> bool:
    """Does a held lease's path_glob cover a candidate repo-relative path?

    Contract §3.2, agreed with APEX: exact, then glob, then directory prefix.

    The glob step deliberately OVER-matches. Python's fnmatch lets a single `*`
    cross `/`; shell and git globs stop at the separator. Rather than pick one
    and hope both agents chose the same, we accept a hit under EITHER. The
    asymmetry justifies it: over-matching costs one "go find other work",
    under-matching costs clobbering a peer's live edit.
    """
    g = (path_glob or "").strip().rstrip("/")
    f = (candidate or "").strip()
    while f.startswith("./"):
        f = f[2:]
    if not g or not f:
        return False

    if g == f:
        return True

    if any(ch in g for ch in "*?["):
        if fnmatch.fnmatch(f, g):          # separator-crossing `*`
            return True
        if posixpath.normpath(g) == posixpath.normpath(f):
            return True
        # separator-respecting pass: `**` still crosses, a lone `*` does not
        if _strict_glob(g, f):
            return True
        # `lib/**` must also cover `lib/a.ts`, not just `lib/a/b.ts`
        if g.endswith("/**") and (f == g[:-3] or f.startswith(g[:-3] + "/")):
            return True
        return False

    return f.startswith(g + "/")           # directory prefix, NOT bare startswith


def _seg_may_match(a: str, b: str) -> bool:
    """Could these two SEGMENT patterns match a common string?

    Conservative on purpose: any wildcard on either side is treated as "yes".
    Deciding exact regular-language intersection is possible but the asymmetry
    does not justify it — over-detecting costs one "go find other work",
    under-detecting costs clobbering a peer's live edit.
    """
    if a == b:
        return True
    if a == "*" or b == "*":
        return True
    if any(ch in a for ch in "*?[") or any(ch in b for ch in "*?["):
        return True
    return False


def intersects(a: str, b: str) -> bool:
    """Do two path GLOBS have any path in common?

    Found by Codex on APEX's implementation 2026-08-27 and confirmed identical
    here: `covers()` answers "does this pattern match that literal path", so two
    patterns that overlap without either matching the other AS A STRING slip
    through completely. `lib/*/x.ts` and `lib/a/**` both cover `lib/a/x.ts`, yet
    covers() is False in both directions — so two agents could hold overlapping
    glob claims and neither conflict check would fire.

    This matters because glob claims are the ones we actively encourage
    (`services/leadgen/**`), so the blind spot sits exactly where the biggest
    claims are.
    """
    pa = [s for s in (a or "").strip().rstrip("/").split("/") if s]
    pb = [s for s in (b or "").strip().rstrip("/").split("/") if s]

    def walk(i: int, j: int) -> bool:
        while i < len(pa) and j < len(pb):
            sa, sb = pa[i], pb[j]
            if sa == "**" or sb == "**":
                # `**` consumes any number of segments on its side; try every split.
                if sa == "**":
                    if i + 1 == len(pa):
                        return True
                    for skip in range(j, len(pb) + 1):
                        if walk(i + 1, skip):
                            return True
                    return False
                if j + 1 == len(pb):
                    return True
                for skip in range(i, len(pa) + 1):
                    if walk(skip, j + 1):
                        return True
                return False
            if not _seg_may_match(sa, sb):
                return False
            i += 1
            j += 1
        # One side ran out. A trailing `**` on the other still intersects
        # (it can match zero segments); anything else means different depths.
        if i == len(pa) and j == len(pb):
            return True
        rest = pa[i:] if j == len(pb) else pb[j:]
        return rest == ["**"]

    return walk(0, 0)


def overlaps(claim: str, candidate: str) -> bool:
    """The conflict predicate: does a held claim collide with a candidate path
    OR candidate glob? Literal candidates go through covers(); glob candidates
    need the two-way intersection test above."""
    if covers(claim, candidate):
        return True
    if any(ch in (candidate or "") for ch in "*?["):
        return covers(candidate, claim) or intersects(claim, candidate)
    return False


def _strict_glob(pattern: str, path: str) -> bool:
    """Segment-wise match where `*` does not cross `/` but `**` does."""
    pat_parts = pattern.split("/")
    path_parts = path.split("/")

    def walk(pi: int, si: int) -> bool:
        while pi < len(pat_parts):
            token = pat_parts[pi]
            if token == "**":
                if pi + 1 == len(pat_parts):
                    return True
                for skip in range(si, len(path_parts) + 1):
                    if walk(pi + 1, skip):
                        return True
                return False
            if si >= len(path_parts):
                return False
            if not fnmatch.fnmatch(path_parts[si], token):
                return False
            pi += 1
            si += 1
        return si == len(path_parts)

    return walk(0, 0)
