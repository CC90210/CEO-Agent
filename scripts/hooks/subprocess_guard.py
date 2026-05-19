"""PreToolUse hook — blocks Edit/Write/MultiEdit that introduces a
`subprocess.{Popen,run,...}` call without `creationflags=`.

Why this guard exists
---------------------
Every recurring "terminal window popped up" incident has the same root
cause: a `subprocess` call inside a background daemon (PM2-managed,
scheduler-managed, bridge-spawned, hook-driven) that omits
`creationflags=CREATE_NO_WINDOW`. When a pythonw parent spawns a
console-subsystem child without the flag, Windows allocates a fresh
console — the pop-up.

`scripts/audit_no_visible_subprocess.py` finds the violations in the
repo. This hook prevents NEW ones from being introduced via agent
edits — the regression-prevention half of the safety net. Both share
the canonical AST predicate in `scripts/lib/subprocess_ast.py`.

Modes (env var `EMPIRE_HOOK_SUBPROCESS_GUARD`):
  enforce          → exit 2 with diff'd violation; agent must add flag
                    or import safe_run before retrying
  report (default) → log to state/subprocess_guard.log, allow edit
  off              → pass through

Bypass marker
-------------
If a subprocess call is intentionally console-visible (an operator-facing
CLI CC runs interactively from the cockpit terminal), annotate the line
with `# noqa: SUBPROCESS` and the guard will not flag it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.hook_runtime import (  # noqa: E402
    log_jsonl,
    mode_from_env,
    read_hook_input,
    state_log_path,
)
from lib.subprocess_ast import find_violations  # noqa: E402

LOG_PATH = state_log_path("subprocess_guard")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Path segments that exempt a file from this guard.
EXEMPT_PATH_SEGMENTS = {".venv", "tmp", "out", "dist", "build", "_archive",
                        ".next", "node_modules", "__pycache__", "tests"}

# Specific files that legitimately call subprocess.* with creationflags
# injected at runtime via **kwargs — AST can't see the merge.
EXEMPT_FILES = {
    "scripts/_subprocess_helpers.py",
    "bravo_cli/_subprocess_helpers.py",
    "scripts/audit_no_visible_subprocess.py",
    "scripts/hooks/subprocess_guard.py",
}


def _is_exempt_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    try:
        rel = Path(file_path).resolve().relative_to(PROJECT_ROOT)
    except (ValueError, OSError):
        # Path outside repo or weird path — exempt (not our concern)
        return True
    parts = rel.parts
    if any(part in EXEMPT_PATH_SEGMENTS for part in parts):
        return True
    return "/".join(parts) in EXEMPT_FILES


def _is_python_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    return file_path.endswith(".py") or file_path.endswith(".pyw")


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

    violations = find_violations(new_content)
    if not violations:
        return 0

    # Compare against the EXISTING file's violations — only block if the
    # edit ADDS new ones. Otherwise a cleanup edit that touches a file
    # with pre-existing violations would be unfairly blocked.
    try:
        existing = Path(file_path).read_text(encoding="utf-8") if file_path else ""
    except (OSError, UnicodeDecodeError):
        existing = ""
    existing_violations = find_violations(existing) if existing else []
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
