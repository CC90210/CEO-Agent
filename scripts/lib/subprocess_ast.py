"""Shared AST helpers for the subprocess-popup audit + PreToolUse guard.

Both `scripts/audit_no_visible_subprocess.py` and
`scripts/hooks/subprocess_guard.py` walk Python source looking for the
same anti-pattern: `subprocess.{Popen,run,...}` without
`creationflags=`. This module owns the AST plumbing — the audit owns
"scan the repo, exit 1 on violations" and the guard owns "block an
agent edit that introduces one." They share the predicate.

Public surface
--------------
- SUBPROCESS_CALLS       — set of attr names we treat as risky
- SAFE_WRAPPERS          — names that are always allowed
- find_violations(source, source_lines=None) → list[Violation]

Each Violation is a dict: {line, col, call, snippet}.
"""

from __future__ import annotations

import ast
from typing import TypedDict

# subprocess.* call attribute names we consider risky on Windows
SUBPROCESS_CALLS: frozenset[str] = frozenset(
    {"Popen", "run", "call", "check_call", "check_output"}
)

# Whitelisted function names — these wrappers force creationflags
# internally, so callers don't need to set it explicitly.
SAFE_WRAPPERS: frozenset[str] = frozenset(
    {"safe_run", "safe_popen", "safe_daemon_popen"}
)


class Violation(TypedDict):
    line: int
    col: int
    call: str
    snippet: str


def _is_posix_guard(node: ast.If) -> bool:
    """True if `node` is an `if` whose body runs ONLY on POSIX.

    Recognized shapes:
      if sys.platform != "win32":
      if os.name != "nt":
      if sys.platform == "darwin":
      if sys.platform == "linux":
      if sys.platform == "posix":
    """
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    left = test.left
    if not (
        isinstance(left, ast.Attribute)
        and isinstance(left.value, ast.Name)
        and (
            (left.value.id == "sys" and left.attr == "platform")
            or (left.value.id == "os" and left.attr == "name")
        )
    ):
        return False
    for op, cmp in zip(test.ops, test.comparators):
        if not isinstance(cmp, ast.Constant):
            continue
        if isinstance(op, ast.NotEq) and cmp.value in ("win32", "nt"):
            return True
        if isinstance(op, ast.Eq) and cmp.value in ("darwin", "linux", "posix"):
            return True
    return False


def _is_windows_positive_guard(node: ast.If) -> bool:
    """True if `node` is `if sys.platform == "win32":` or `if os.name == "nt":`.
    Used to detect the `orelse` branch — that's the POSIX side."""
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    left = test.left
    if not (
        isinstance(left, ast.Attribute)
        and isinstance(left.value, ast.Name)
        and (
            (left.value.id == "sys" and left.attr == "platform")
            or (left.value.id == "os" and left.attr == "name")
        )
    ):
        return False
    for op, cmp in zip(test.ops, test.comparators):
        if isinstance(op, ast.Eq) and isinstance(cmp, ast.Constant):
            if cmp.value in ("win32", "nt"):
                return True
    return False


def call_target(call: ast.Call) -> str | None:
    """Return the canonical name of the call's target:
      'subprocess.Popen' / 'subprocess.run' / … if the call is one of
      the SUBPROCESS_CALLS,
      'safe_run' / 'safe_popen' / 'safe_daemon_popen' if it's a wrapper,
      or None if we don't care about this call.
    """
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "subprocess" and func.attr in SUBPROCESS_CALLS:
            return f"subprocess.{func.attr}"
    if isinstance(func, ast.Name) and func.id in SAFE_WRAPPERS:
        return func.id
    return None


def has_creationflags(call: ast.Call) -> bool:
    """True if the call explicitly sets a `creationflags=...` keyword arg.
    We trust the author's intent regardless of the value."""
    return any(kw.arg == "creationflags" for kw in call.keywords)


def has_noqa(source_lines: list[str], lineno: int) -> bool:
    """True if the line at `lineno` (1-indexed) has a `# noqa: SUBPROCESS`
    annotation, or the line immediately above does (for cases where the
    annotation precedes a multi-line call)."""
    if 1 <= lineno <= len(source_lines):
        line = source_lines[lineno - 1]
        if "noqa: SUBPROCESS" in line or "noqa:SUBPROCESS" in line:
            return True
    if 1 <= lineno - 1 <= len(source_lines):
        prev = source_lines[lineno - 2]
        if "noqa: SUBPROCESS" in prev or "noqa:SUBPROCESS" in prev:
            return True
    return False


def _walk_with_parents(tree: ast.Module):
    """Yield (node, parents-map) — used so callers can answer 'is this
    node inside a POSIX guard?' by walking up the AST."""
    parents: dict[int, ast.AST] = {}
    for n in ast.walk(tree):
        for child in ast.iter_child_nodes(n):
            parents[id(child)] = n
    return parents


def _is_posix_only(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    """True if `node` lives inside a POSIX-only branch — either the body
    of `if sys.platform != 'win32':` (and similar) OR the `orelse` of an
    `if os.name == 'nt':`-style guard."""
    cur = node
    while id(cur) in parents:
        parent = parents[id(cur)]
        if isinstance(parent, ast.If):
            if _is_posix_guard(parent) and cur in parent.body:
                return True
            if _is_windows_positive_guard(parent) and cur in parent.orelse:
                return True
        cur = parent
    return False


def find_violations(
    source: str, source_lines: list[str] | None = None
) -> list[Violation]:
    """Return all unflagged subprocess violations in `source`.

    A violation is a `subprocess.{Popen,run,...}` call that:
      - lacks `creationflags=`,
      - is NOT in a POSIX-only branch,
      - is NOT inside a `safe_*` wrapper alias,
      - is NOT annotated with `# noqa: SUBPROCESS`.

    Returns empty list on SyntaxError (caller is likely mid-edit).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    if source_lines is None:
        source_lines = source.splitlines()

    parents = _walk_with_parents(tree)
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = call_target(node)
        if target is None or target in SAFE_WRAPPERS:
            continue
        if has_creationflags(node):
            continue
        if _is_posix_only(node, parents):
            continue
        if has_noqa(source_lines, node.lineno):
            continue
        snippet = ""
        if 0 < node.lineno <= len(source_lines):
            snippet = source_lines[node.lineno - 1].strip()[:160]
        violations.append({
            "line": node.lineno,
            "col": node.col_offset,
            "call": target,
            "snippet": snippet,
        })
    return violations


__all__ = [
    "SUBPROCESS_CALLS",
    "SAFE_WRAPPERS",
    "Violation",
    "call_target",
    "has_creationflags",
    "has_noqa",
    "find_violations",
]
