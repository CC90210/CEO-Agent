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
A "violation" is any of:
  1. `subprocess.Popen(...)` missing a `creationflags=` keyword AND not
     gated behind `if sys.platform != "win32":` / `if os.name != "nt":`.
  2. `subprocess.run/call/check_call/check_output(...)` with the same shape.
  3. `subprocess.run(..., shell=True, ...)` missing creationflags — this
     allocates cmd.exe and is the WORST offender because every shell-true
     call from a daemon is a guaranteed pop-up.

Allowed forms (NOT flagged)
---------------------------
  - Calls that include `creationflags=` (any value — we trust the author)
  - Calls to `safe_run` / `safe_popen` / `safe_daemon_popen` from
    `_subprocess_helpers` (the canonical wrappers)
  - Calls inside `tests/`, `_archive/`, `.venv/`, `tmp/`, `node_modules/`
  - Calls inside an explicit `if sys.platform != "win32":` or
    `if os.name != "nt":` block (POSIX-only code)
  - Calls inside `# noqa: SUBPROCESS` annotated blocks (deliberate
    operator-facing CLIs)

Exit codes
----------
  0 — zero violations
  1 — at least one violation found (prints file:line — snippet for each)

Usage
-----
  python scripts/audit_no_visible_subprocess.py           # full repo
  python scripts/audit_no_visible_subprocess.py --json    # machine-readable
  python scripts/audit_no_visible_subprocess.py path/file # single file
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

SUBPROCESS_CALLS = {"Popen", "run", "call", "check_call", "check_output"}

# Whitelisted call targets that already enforce CREATE_NO_WINDOW.
SAFE_WRAPPERS = {"safe_run", "safe_popen", "safe_daemon_popen"}

# Path-prefix excludes (relative to repo root). Files under these
# trees are NEVER flagged.
EXCLUDED_DIRS = {
    ".venv", ".git", "node_modules", "tmp", "out", "dist", "build",
    "_archive", ".next", ".cache", ".pytest_cache", "__pycache__",
}

# Per-file excludes — operator-facing CLIs where a visible window is
# the intended UX (e.g., interactive tools CC runs from the cockpit).
EXCLUDED_FILES = {
    # The wrapper modules themselves call subprocess.run/Popen and
    # rely on **kwargs to inject creationflags at runtime; AST can't
    # see that, so exclude them.
    "scripts/_subprocess_helpers.py",
    "bravo_cli/_subprocess_helpers.py",
    # The audit + guard scripts walk for subprocess calls as STRING /
    # AST matches; their own internal calls would be flagged otherwise.
    "scripts/audit_no_visible_subprocess.py",
    "scripts/hooks/subprocess_guard.py",
}


def _is_posix_guard(stmt: ast.AST) -> bool:
    """True if `stmt` is `if sys.platform != "win32":` or
    `if os.name != "nt":` or `if sys.platform in (...)` etc — any guard
    that means the body runs on POSIX only."""
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    # sys.platform != "win32"
    if isinstance(test, ast.Compare):
        left = test.left
        if (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and ((left.value.id == "sys" and left.attr == "platform")
                 or (left.value.id == "os" and left.attr == "name"))
        ):
            for op, comparator in zip(test.ops, test.comparators):
                if isinstance(op, ast.NotEq) and isinstance(comparator, ast.Constant):
                    if comparator.value in ("win32", "nt"):
                        return True
                if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant):
                    # `if sys.platform == "darwin":` — also POSIX
                    if comparator.value in ("darwin", "linux", "posix"):
                        return True
    return False


def _is_windows_guard(stmt: ast.AST) -> bool:
    """True if `stmt` is a Windows-specific guard whose body should
    contain creationflags — but if not flagged, the inner call IS
    a violation (Windows path missing the flag)."""
    if not isinstance(stmt, ast.If):
        return False
    test = stmt.test
    if isinstance(test, ast.Compare):
        left = test.left
        if (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and ((left.value.id == "sys" and left.attr == "platform")
                 or (left.value.id == "os" and left.attr == "name"))
        ):
            for op, comparator in zip(test.ops, test.comparators):
                if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant):
                    if comparator.value in ("win32", "nt"):
                        return True
    return False


def _call_target(call: ast.Call) -> str | None:
    """Return 'subprocess.Popen' / 'subprocess.run' / 'safe_run' / etc.
    or None if the call isn't one we care about."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "subprocess" and func.attr in SUBPROCESS_CALLS:
            return f"subprocess.{func.attr}"
    if isinstance(func, ast.Name) and func.id in SAFE_WRAPPERS:
        return func.id
    return None


def _has_creationflags(call: ast.Call) -> bool:
    return any(kw.arg == "creationflags" for kw in call.keywords)


def _has_noqa_marker(source_lines: list[str], lineno: int) -> bool:
    """True if the line (or one immediately above) carries a
    `# noqa: SUBPROCESS` annotation."""
    if 1 <= lineno <= len(source_lines):
        line = source_lines[lineno - 1]
        if "noqa: SUBPROCESS" in line or "noqa:SUBPROCESS" in line:
            return True
    if 1 <= lineno - 1 <= len(source_lines):
        prev = source_lines[lineno - 2]
        if "noqa: SUBPROCESS" in prev or "noqa:SUBPROCESS" in prev:
            return True
    return False


def _iter_calls_with_context(tree: ast.Module):
    """Yield (call_node, posix_only) for every Call in the tree, where
    posix_only is True if the call is inside an `if sys.platform != win32:`
    style guard."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    def is_posix_only(node: ast.AST) -> bool:
        # walk up; if any enclosing `If` is a POSIX guard and node is
        # in the body (not orelse), this call is POSIX-only.
        cur = node
        while id(cur) in parents:
            parent = parents[id(cur)]
            if isinstance(parent, ast.If):
                if _is_posix_guard(parent):
                    # Confirm we are in `body`, not `orelse`
                    if cur in parent.body:
                        return True
            cur = parent
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node, is_posix_only(node)


def audit_file(path: Path) -> list[dict]:
    """Return a list of violation dicts for `path`. Empty list = clean."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    violations: list[dict] = []
    for call, posix_only in _iter_calls_with_context(tree):
        target = _call_target(call)
        if target is None:
            continue
        if target in SAFE_WRAPPERS:
            continue
        if posix_only:
            continue
        if _has_creationflags(call):
            continue
        if _has_noqa_marker(source_lines, call.lineno):
            continue
        snippet = source_lines[call.lineno - 1].strip() if 0 < call.lineno <= len(source_lines) else ""
        violations.append({
            "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "line": call.lineno,
            "col": call.col_offset,
            "call": target,
            "snippet": snippet[:160],
        })
    return violations


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).parts
    if any(part in EXCLUDED_DIRS for part in rel):
        return True
    rel_str = "/".join(rel)
    if rel_str in EXCLUDED_FILES:
        return True
    return False


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
