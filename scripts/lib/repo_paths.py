"""repo_paths — repo/path resolution and glob coverage. NO database, NO heavy imports.

This module exists for one reason: scripts/state/coord_guard.py runs on EVERY
Edit/Write, and the first version imported coord_claim, which imports db_turso,
which opens a Turso connection at import time. Measured cost: 4-5 SECONDS per
edit, even when the answer came from a local cache and no query was needed.

A guard that adds four seconds to every keystroke-level edit gets switched off,
and a switched-off guard is exactly the failure this whole subsystem exists to
correct. So the hot path — "which repo is this file in, and does any cached
lease glob cover it" — lives here, depends on nothing but stdlib and `git`, and
the DB module is imported only on a genuine cache miss.

coord_claim.py re-exports these so there is one definition, not two that drift.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path

# Windows: keep `git` from flashing a console when called from a pythonw hook.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_root_cache: dict[str, Path | None] = {}


def repo_root(start: str | Path | None = None) -> Path | None:
    """Git toplevel containing `start`, or None. Memoised per directory — a hook
    run resolves the same handful of directories repeatedly."""
    start = Path(start or Path.cwd())
    probe = start if start.is_dir() else start.parent
    key = str(probe)
    if key in _root_cache:
        return _root_cache[key]
    result: Path | None = None
    try:
        out = subprocess.run(
            ["git", "-C", key, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW,
        )
        if out.returncode == 0:
            result = Path(out.stdout.strip())
    except Exception:  # noqa: BLE001
        result = None
    _root_cache[key] = result
    return result


def repo_slug(root: Path) -> str:
    """Canonical repo identity = toplevel directory name.

    Deliberately NOT the git remote: a repo can have several remotes, a fork has
    a different one, and APEX's clone of a shared repo must resolve to the SAME
    slug as CC's — otherwise the two agents claim in different namespaces and
    the entire mechanism silently no-ops while appearing to work.
    """
    return root.name


def resolve(path: str | Path) -> tuple[str, str] | None:
    """Absolute-or-relative path -> (repo_slug, repo-relative POSIX path)."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        p = Path(os.path.normpath(str(p)))
    except Exception:  # noqa: BLE001
        return None
    root = repo_root(p)
    if root is None:
        return None
    try:
        rel = p.relative_to(root)
    except ValueError:
        try:
            rel = p.resolve().relative_to(root.resolve())
        except Exception:  # noqa: BLE001
            return None
    return repo_slug(root), rel.as_posix()


def covers(path_glob: str, candidate: str) -> bool:
    """Does a held lease's path_glob cover a candidate repo-relative path?"""
    if path_glob == candidate:
        return True
    if fnmatch.fnmatch(candidate, path_glob):
        return True
    # A directory claim covers everything beneath it: "lib/drips" -> "lib/drips/x.ts"
    if not any(ch in path_glob for ch in "*?["):
        if candidate.startswith(path_glob.rstrip("/") + "/"):
            return True
    return False
