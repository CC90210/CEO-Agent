"""PreToolUse hook — blocks edits / shell-redirects on auto-generated state mirrors.

`memory/SESSION_LOG.md` is rendered from `state/empire_state.db` between
AUTO-GENERATED markers. Direct mutations get clobbered on the next
`state_manager.py export`. This guard makes the failure loud instead of
silent — for both IDE Edit/Write tool calls AND shell redirects/pipes
(Codex caught the shell bypass: `echo "..." > memory/SESSION_LOG.md`
slipped past the IDE-only guard).

Modes (env var `EMPIRE_HOOK_STATE_GUARD`):
  enforce → exit 2 to block
  report  → log a would-be block, allow
  off     → pass through (default until V6.0 cutover)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Put scripts/ (the parent of state/) on the path so `import lib.hook_runtime`
# resolves. The previous .parent pointed at state/ itself → ModuleNotFoundError →
# the hook failed OPEN (never enforced or logged). Mirrors the secret_guard.py fix.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.hook_runtime import (  # noqa: E402
    PROJECT_ROOT,
    log_jsonl,
    mode_from_env,
    read_hook_input,
    state_log_path,
)

LOG_PATH = state_log_path("state_guard")

# Files owned by state_manager.py — direct edits will be clobbered.
# Listed as POSIX-relative paths; the path-comparator and the shell-pattern
# detector both consume this set. We anchor on the FULL relative path,
# not the basename, so a homonym like `backups/SESSION_LOG.md` doesn't
# get caught in the net.
PROTECTED_PATHS = {
    "memory/SESSION_LOG.md",
}


REASON_TEMPLATE = (
    "BLOCKED by state_guard: '{path}' is auto-generated from state/empire_state.db.\n"
    "Mutate the database instead:\n"
    "  python scripts/state/state_manager.py log --note \"...\"\n"
    "  python scripts/state/state_manager.py task add --bucket TODAY --title \"...\"\n"
    "  python scripts/state/state_manager.py heartbeat --status working\n"
    "Then run `python scripts/state/state_manager.py export` to regenerate the mirror."
)


def _is_protected(target: str | None) -> bool:
    if not target:
        return False
    try:
        p = Path(target).resolve()
        rel = p.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    return rel in PROTECTED_PATHS


def _bash_targets_protected(cmd: str) -> str | None:
    """Return the protected path if `cmd` mutates one, else None.

    The match is anchored on the FULL relative path (e.g. `memory/SESSION_LOG.md`),
    not just the basename — so a homonym like `backups/SESSION_LOG.md` does NOT
    trigger the guard. This was a Codex follow-up: basename matching was too
    aggressive, blocking legitimate writes to like-named files in unrelated
    directories.

    Checked patterns (only when the protected path literally appears in the cmd):
      - shell redirect:  > path  / >> path
      - tee:             tee [-a] path
      - cp / mv / rsync: cp X path / mv X path / rsync X path
      - sed -i:          sed -i ... path
      - dd:              dd of=path
      - python -c open:  python -c "...open('path','w'..."
    """
    if not cmd:
        return None
    # Normalize backslash variants once so the substring screen is OS-agnostic.
    cmd_unix = cmd.replace("\\", "/")
    for protected in PROTECTED_PATHS:
        # Substring screen — the FULL relative path must appear in the cmd.
        if protected not in cmd_unix:
            continue
        # Path token for write-context regex checks: allow optional drive
        # letter, leading slash, ./, or arbitrary prefix DIRECTORY segments
        # before the protected path. Backslash normalization above means we
        # only match against the forward-slash form.
        path_re = rf"(?:[A-Za-z]:)?/?(?:\./)?(?:[\w./-]+/)?{re.escape(protected)}\b"
        if re.search(rf">>?\s*{path_re}", cmd_unix):
            return protected
        if re.search(rf"\btee\b(?:\s+-[aA])*\s+{path_re}", cmd_unix):
            return protected
        if re.search(rf"\b(?:cp|mv|rsync|install)\b[^|;&]*\s{path_re}", cmd_unix):
            return protected
        if re.search(rf"\bsed\b\s+(?:-[a-zA-Z]*i[a-zA-Z]*|--in-place\S*)[^|;&]*\b{path_re}", cmd_unix):
            return protected
        if re.search(rf"\bdd\b[^|;&]*\bof=\s*{path_re}", cmd_unix):
            return protected
        if re.search(rf"""\bpython3?\b\s+-c\s+["'][^"']*open\(\s*['"]{path_re}['"]\s*,\s*['"][wa]""", cmd_unix):
            return protected
        # truncate -s N path  → resizes the file; -s 0 zeroes it.
        if re.search(rf"\btruncate\b[^|;&]*\s{path_re}", cmd_unix):
            return protected
        # ln -sf <src> <protected>  → overwrites the file with a symlink.
        # The protected path must be the LAST arg (ln's destination).
        if re.search(rf"\bln\b\s+(?:-[a-zA-Z]*[fs][a-zA-Z]*\s+)+[^|;&]*\s{path_re}\s*(?:$|[|;&])", cmd_unix):
            return protected
    return None


def main() -> int:
    mode = mode_from_env("EMPIRE_HOOK_STATE_GUARD", default="report")
    if mode == "off":
        return 0

    payload = read_hook_input()
    if not payload:
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    target: str | None = None

    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        candidate = tool_input.get("file_path")
        if _is_protected(candidate):
            target = candidate
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        hit = _bash_targets_protected(cmd)
        if hit:
            target = hit  # basename — sufficient for the error message

    if not target:
        return 0

    if mode == "enforce":
        log_jsonl(LOG_PATH, {
            "decision": "blocked",
            "tool": tool_name,
            "path": target,
            "command": (tool_input.get("command") or "")[:500] if tool_name == "Bash" else None,
        })
        sys.stderr.write(REASON_TEMPLATE.format(path=target) + "\n")
        return 2

    log_jsonl(LOG_PATH, {
        "decision": "would-block",
        "tool": tool_name,
        "path": target,
        "command": (tool_input.get("command") or "")[:500] if tool_name == "Bash" else None,
    })
    sys.stderr.write(f"[state_guard report-mode] would block: {target}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
