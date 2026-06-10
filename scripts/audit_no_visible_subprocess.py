"""Audit every Python file in the repo for subprocess calls that could
spawn a visible console window on Windows.

Why this exists
---------------
Every recurring "terminal window popped up" incident has the same root
cause: a `subprocess.Popen(...)` or `subprocess.run(...)` inside a
background daemon (PM2-managed, scheduler-managed, bridge-spawned,
n8n-triggered, hook-driven) that is missing `creationflags=CREATE_NO_WINDOW`.

Parent is `pythonw.exe` (no console). When it spawns a console-subsystem
child (`python.exe`, `cmd.exe`, `node.exe`, anything via shell=True)
without CREATE_NO_WINDOW, Windows allocates a fresh console — the pop-up.

What this script flags
----------------------
Any unflagged `subprocess.{Popen,run,call,check_call,check_output}` call
that is NOT inside a POSIX-only branch and NOT annotated `# noqa: SUBPROCESS`.
See `scripts/lib/subprocess_ast.py` for the canonical predicate.

Exit codes
----------
  0 — zero violations
  1 — at least one violation found

Usage
-----
  python scripts/audit_no_visible_subprocess.py           # full repo
  python scripts/audit_no_visible_subprocess.py --json    # machine-readable
  python scripts/audit_no_visible_subprocess.py path/file # single file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.subprocess_ast import find_violations  # noqa: E402

# Path-prefix excludes (relative to repo root). Files under these
# trees are NEVER flagged.
EXCLUDED_DIRS = {
    ".venv", ".git", "node_modules", "tmp", "out", "dist", "build",
    "_archive", ".next", ".cache", ".pytest_cache", "__pycache__",
    "tests",  # test subprocess calls are not production code (V7 audit-trustworthiness)
}

# Per-file excludes — modules that legitimately call subprocess.* with
# creationflags injected at runtime via **kwargs, where AST can't see it.
EXCLUDED_FILES = {
    # The wrapper modules themselves call subprocess.run/Popen with
    # **kwargs that the caller passes in. The AST can't see the dynamic
    # creationflags merge, so exclude them.
    "scripts/_subprocess_helpers.py",
    "scripts/lib/subprocess_helpers.py",
    "bravo_cli/_subprocess_helpers.py",
    # The audit + guard scripts walk for subprocess calls as
    # AST patterns; their own internal calls would be flagged.
    "scripts/audit_no_visible_subprocess.py",
    "scripts/hooks/subprocess_guard.py",
    # V7 audit-trustworthiness (2026-06-10): both set creationflags the AST can't see —
    # retriever_postedit builds them via a runtime **kwargs dict; _claude_auth's call is
    # Darwin-gated (os.uname().sysname) and unreachable on Windows. Exempting these so the
    # audit returns 0 production violations and a future REAL one is unmissable.
    "scripts/retriever_postedit.py",
    "bravo_cli/_claude_auth.py",
}


def audit_file(path: Path) -> list[dict]:
    """Return a list of violation dicts for `path`. Empty list = clean.

    Each dict includes `file` (repo-relative path) on top of the
    line/col/call/snippet shape from `find_violations`."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    violations = find_violations(source)
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    return [{**v, "file": rel} for v in violations]


def _is_excluded(path: Path) -> bool:
    try:
        rel = path.relative_to(REPO_ROOT).parts
    except ValueError:
        return True
    if any(part in EXCLUDED_DIRS for part in rel):
        return True
    rel_str = "/".join(rel)
    return rel_str in EXCLUDED_FILES


def walk_repo(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file() and root.suffix in (".py", ".pyw"):
            yield root
            continue
        for path in root.rglob("*.py"):
            if not _is_excluded(path):
                yield path
        for path in root.rglob("*.pyw"):
            if not _is_excluded(path):
                yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files or directories to audit (default: repo root)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="only print summary line")
    args = parser.parse_args()

    if args.paths:
        roots = [Path(p).resolve() for p in args.paths]
    else:
        roots = [REPO_ROOT / "scripts", REPO_ROOT / "bravo_cli", REPO_ROOT / "agents"]
        roots = [r for r in roots if r.exists()]

    all_violations: list[dict] = []
    files_audited = 0
    for path in walk_repo(roots):
        files_audited += 1
        all_violations.extend(audit_file(path))

    if args.json:
        print(json.dumps({
            "files_audited": files_audited,
            "violations": all_violations,
            "violation_count": len(all_violations),
        }, indent=2))
        return 1 if all_violations else 0

    if not args.quiet:
        for v in all_violations:
            print(f"{v['file']}:{v['line']} — {v['call']}() missing creationflags")
            print(f"    {v['snippet']}")

    print(f"\n[audit] files={files_audited} violations={len(all_violations)}")
    if all_violations:
        print("[audit] FAIL — migrate calls to safe_run/safe_popen from _subprocess_helpers")
        print("[audit]        or add `creationflags=WINDOWLESS_FLAGS` to each call site")
        print("[audit]        or annotate the line with `# noqa: SUBPROCESS` if deliberate")
        return 1
    print("[audit] OK — no subprocess pop-up risks detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
