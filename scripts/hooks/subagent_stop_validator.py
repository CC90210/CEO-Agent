"""SubagentStop hook — the Validator auto-gate.

The `validator` sub-agent (.claude/agents/validator.md) is documented as MANDATORY after
any sub-agent that modified files, but it had ZERO auto-callers — "infrastructure without
callers is vapor." This hook gives it one: when a sub-agent finishes and the working tree
has changed files, it reminds the orchestrator to run the Validator before surfacing the
result to CC, and records a durable pending-validation marker.

A hook cannot spawn a Task sub-agent itself, so this is an enforced REMINDER (report-mode),
matching scripts/hooks/anti_pattern_hook.py. It NEVER blocks the subagent from stopping.

Output contract (Claude Code SubagentStop hook):
    {"hookSpecificOutput": {"hookEventName": "SubagentStop", "additionalContext": "<reminder>"}}

Mode via EMPIRE_HOOK_VALIDATOR (default "report"): report = remind+log; off = pass-through.
Wired in .claude/settings.local.json SubagentStop matcher. Fast-fails to exit 0 on any error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "scripts" / "_subprocess_helpers.py").exists():
    _p = _p.parent
sys.path.insert(0, str(_p / "scripts"))
try:
    from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402
except Exception:
    WINDOWLESS_FLAGS = 0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / "state" / "validator_pending.jsonl"
GIT_BASELINE_PATH = PROJECT_ROOT / "state" / "session_git_baseline.json"
IGNORE_SUFFIXES = (".png", ".jpeg", ".jpg", ".log", ".jsonl")


def _baseline_map() -> dict[str, str]:
    """path -> 2-char porcelain status code, as of session start (written by
    scripts/hooks/session_start.py).

    A file is "this session's work" if it is NOT in this map OR its status code
    changed since boot. Excluding same-status pre-existing dirt is what stops the
    gate from nagging about a tree that was already dirty (the 2026-07-02 incident,
    where that false nag pressured a read-only agent into a destructive
    `git checkout .. && rm -rf` cleanup). Tracking the status code (not just the
    path) also catches a sub-agent editing an already-dirty file into a new state
    (Codex audit P2). Missing/unreadable baseline → empty map → report all dirty
    files (still advisory, never destructive)."""
    try:
        with GIT_BASELINE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data.get("dirty"), dict):
            return data["dirty"]
        # back-compat: old baselines stored only a path list (unknown codes)
        return {p: "" for p in data.get("dirty_paths", [])}
    except Exception:
        return {}


def _changed_files() -> list[str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, creationflags=WINDOWLESS_FLAGS,
        )
    except Exception:
        return []
    baseline = _baseline_map()
    files = []
    for ln in r.stdout.splitlines():
        code = ln[:2]
        path = ln[3:].strip().strip('"')
        if not path or path.lower().endswith(IGNORE_SUFFIXES):
            continue
        # New path, OR same path at a different status than baseline = changed
        # this session. Same path at same status (or legacy baseline with an
        # unknown "" code) = pre-existing → skip.
        if path in baseline and baseline[path] in (code, ""):
            continue
        files.append(path)
    return files


def main() -> int:
    mode = os.environ.get("EMPIRE_HOOK_VALIDATOR", "report").strip().lower()
    if mode == "off":
        return 0
    try:
        json.load(sys.stdin)  # consume the event payload (not otherwise needed)
    except Exception:
        pass

    changed = _changed_files()
    if not changed:
        return 0  # nothing to validate — silent

    sample = changed[:8]
    reminder = (
        "⚠ VALIDATOR GATE: a sub-agent just finished and "
        f"{len(changed)} file(s) changed DURING this session (e.g. {', '.join(sample)}). Per the "
        "orchestration decision table (brain/ORCHESTRATION_DECISION_TABLE.md §B), spawn the "
        "`validator` sub-agent (Task tool, subagent_type: validator) to verify the diff against "
        "the task's success criteria BEFORE surfacing this to CC. Score <70 → re-run, don't surface. "
        "This is an ADVISORY reminder, not a blocker: do NOT modify or revert the working tree, "
        "`git checkout`/`git restore`/`rm` files, or 'clean up' to satisfy this gate — that is "
        "destructive and out of scope. If you have no Task tool or are a read-only agent, ignore "
        "this gate entirely and just return your findings."
    )
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"changed_count": len(changed), "sample": sample}) + "\n")
    except Exception:
        pass

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop",
            "additionalContext": reminder,
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never block on hook failure
