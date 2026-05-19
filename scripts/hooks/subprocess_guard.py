"""PreToolUse hook — blocks Edit/Write/MultiEdit/NotebookEdit that
introduces a `subprocess.{Popen,run,...}` call without `creationflags=`.

Why this guard exists
---------------------
Every recurring "terminal window popped up" incident has the same root
cause: a `subprocess` call inside a background daemon (PM2-managed,
scheduler-managed, bridge-spawned, hook-driven) that omits
`creationflags=CREATE_NO_WINDOW`. When a pythonw parent spawns a
console-subsystem child without the flag, Windows allocates a fresh
console — the pop-up.

scripts/audit_no_visible_subprocess.py finds the violations in the
repo. This hook prevents NEW ones from being introduced via agent
edits — the regression-prevention half of the safety net.

Modes (env var `EMPIRE_HOOK_SUBPROCESS_GUARD`):
  enforce          → exit 2 with diff'd violation; agent must add flag
                    or import safe_run before retrying
  report (default) → log to state/subprocess_guard.log, allow edit
  off              → pass through

What counts as a violation
--------------------------
  * `subprocess.{Popen,run,call,check_call,check_output}(...)` in the
    NEW content where the call lacks `creationflags=` AND is not gated
    behind an `if os.name != "nt":` / `if sys.platform != "win32":` guard.
  * Calls to `safe_run` / `safe_popen` / `safe_daemon_popen` from
    `_subprocess_helpers` are ALWAYS allowed.
  * Files in `tmp/`, `_archive/`, `.venv/`, `tests/` are exempt.
  * Lines annotated with `# noqa: SUBPROCESS` are exempt.

Bypass marker for deliberate operator-facing CLIs
-------------------------------------------------
If a subprocess call is intentionally console-visible (e.g., a tool CC
runs interactively from the cockpit terminal), annotate the line with
`# noqa: SUBPROCESS` and the guard will not flag it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.hook_runtime import (  # noqa: E402
    log_jsonl,
    mode_from_env,
    read_hook_input,
    state_log_path,
)

LOG_PATH = state_log_path("subprocess_guard")

SUBPROCESS_CALLS = {"Popen", "run", "call", "check_call", "check_output"}
SAFE_WRAPPERS = {"safe_run", "safe_popen", "safe_daemon_popen"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Path segments that exempt a file from this guard.
EXEMPT_PATH_SEGMENTS = {".venv", "tmp", "out", "dist", "build", "_archive",
                        ".next", "node_modules", "__pycache__", "tests"}


def _is_exempt_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    try:
        rel = Path(file_path).resolve().relative_to(PROJECT_ROOT)
    except (ValueError, OSError):
        # Path outside repo or weird path — exempt (not our concern)
        return True
    parts = rel.parts
    return any(part in EXEMPT_PATH_SEGMENTS for part in parts)


def _is_python_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    return file_path.endswith(".py") or file_path.endswith(".pyw")


def _is_posix_guard(stmt: ast.AST) -> bool:
    """True if `stmt` is `if sys.platform != "win32":` or
    `if os.name != "nt":` — guard means the body is POSIX-only."""
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
                if isinstance(op, ast.NotEq) and isinstance(comparator, ast.Constant):
                    if comparator.value in ("win32", "nt"):
                        return True
                if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant):
                    if comparator.value in ("darwin", "linux", "posix"):
                        return True
    return False


def _call_target(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "subprocess" and func.attr in SUBPROCESS_CALLS:
            return f"subprocess.{func.attr}"
    if isinstance(func, ast.Name) and func.id in SAFE_WRAPPERS:
        return func.id
    return None


def _has_creationflags(call: ast.Call) -> bool:
    return any(kw.arg == "creationflags" for kw in call.keywords)


def _has_noqa(source_lines: list[str], lineno: int) -> bool:
    if 1 <= lineno <= len(source_lines):
        line = source_lines[lineno - 1]
        if "noqa: SUBPROCESS" in line or "noqa:SUBPROCESS" in line:
            return True
    return False


def _find_violations(source: str) -> list[dict]:
    """Return list of {line, call, snippet} for unflagged subprocess calls
    in `source`. Skips POSIX-only branches and noqa-annotated lines."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Don't block on syntax errors — the user is mid-edit. Other
        # tools will catch the syntax problem.
        return []

    source_lines = source.splitlines()
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    def is_posix_only(node: ast.AST) -> bool:
        cur = node
        while id(cur) in parents:
            parent = parents[id(cur)]
            if isinstance(parent, ast.If) and _is_posix_guard(parent):
                if cur in parent.body:
                    return True
            cur = parent
        return False

    violations: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _call_target(node)
        if target is None or target in SAFE_WRAPPERS:
            continue
        if is_posix_only(node):
            continue
        if _has_creationflags(node):
            continue
        if _has_noqa(source_lines, node.lineno):
            continue
        snippet = source_lines[node.lineno - 1].strip() if 0 < node.lineno <= len(source_lines) else ""
        violations.append({"line": node.lineno, "call": target, "snippet": snippet[:160]})
    return violations


def _new_content_for_tool(tool_name: str, tool_input: dict, file_path: str | None) -> str | None:
    """Resolve the post-edit source content for the file. For Write the
    full new content is in `content`. For Edit we approximate by reading
    the current file and applying the change in-memory."""
    if tool_name == "Write":
        return tool_input.get("content")

    if tool_name == "Edit":
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if old is None or new is None or not file_path:
            return None
        try:
            current = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        if tool_input.get("replace_all"):
            return current.replace(old, new)
        # Single-replacement Edit
        return current.replace(old, new, 1)

    if tool_name == "MultiEdit":
        if not file_path:
            return None
        try:
            current = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        for edit in tool_input.get("edits") or []:
            old = edit.get("old_string")
            new = edit.get("new_string")
            if old is None or new is None:
                continue
            if edit.get("replace_all"):
                current = current.replace(old, new)
            else:
                current = current.replace(old, new, 1)
        return current

    return None


REASON_TEMPLATE = (
    "BLOCKED by subprocess_guard: the edit would introduce a subprocess\n"
    "call on Windows without `creationflags=CREATE_NO_WINDOW`. This\n"
    "spawns a visible terminal window every time the call fires.\n\n"
    "Violations in the new content:\n"
    "{violations}\n\n"
    "Fix options:\n"
    "  1. Import the canonical wrapper and use it:\n"
    "       from _subprocess_helpers import safe_run, safe_popen\n"
    "       safe_run([...], capture_output=True)\n"
    "  2. Add the flag directly:\n"
    "       from _subprocess_helpers import WINDOWLESS_FLAGS\n"
    "       subprocess.run([...], creationflags=WINDOWLESS_FLAGS)\n"
    "  3. Operator-facing CLI where a visible window is wanted? Annotate:\n"
    "       subprocess.run(...)  # noqa: SUBPROCESS\n\n"
    "Run `python scripts/audit_no_visible_subprocess.py` to verify the\n"
    "repo stays clean."
)


def main() -> int:
    mode = mode_from_env("EMPIRE_HOOK_SUBPROCESS_GUARD", default="report")
    if mode == "off":
        return 0

    payload = read_hook_input()
    if not payload:
        return 0

    tool_name = payload.get("tool_name")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not _is_python_file(file_path):
        return 0
    if _is_exempt_path(file_path):
        return 0

    new_content = _new_content_for_tool(tool_name, tool_input, file_path)
    if new_content is None:
        return 0

    violations = _find_violations(new_content)
    if not violations:
        return 0

    # Compare against the EXISTING file's violations — only block if the
    # edit ADDS new ones. Otherwise a clean-up edit that touches a file
    # with pre-existing violations would be blocked unfairly.
    try:
        existing = Path(file_path).read_text(encoding="utf-8") if file_path else ""
    except (OSError, UnicodeDecodeError):
        existing = ""
    existing_violations = _find_violations(existing) if existing else []
    existing_keys = {(v["call"], v["snippet"]) for v in existing_violations}
    new_violations = [v for v in violations if (v["call"], v["snippet"]) not in existing_keys]
    if not new_violations:
        return 0

    bullets = "\n".join(
        f"  line {v['line']}: {v['call']}() — {v['snippet']}"
        for v in new_violations
    )
    reason = REASON_TEMPLATE.format(violations=bullets)

    log_record = {
        "tool": tool_name,
        "file": file_path,
        "new_violations": new_violations,
        "decision": "blocked" if mode == "enforce" else "would-block",
    }
    log_jsonl(LOG_PATH, log_record)

    if mode == "enforce":
        sys.stderr.write(reason + "\n")
        return 2

    sys.stderr.write(
        f"[subprocess_guard report-mode] would block {len(new_violations)} "
        f"new subprocess violation(s) in {file_path}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
