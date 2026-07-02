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


def _baseline_paths() -> set[str]:
    """Paths already dirty at session start (written by scripts/hooks/session_start.py).

    Files in this set were NOT changed by any sub-agent this session — they were
    dirty before the session began. Excluding them is what stops the gate from
    nagging about pre-existing working-tree state (the 2026-07-02 incident, where
    that false nag pressured a read-only agent into a destructive `git checkout ..
    && rm -rf` cleanup). Missing/unreadable baseline → empty set → fall back to
    reporting all dirty files (still advisory, never destructive)."""
    try:
        with GIT_BASELINE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return set(data.get("dirty_paths", []))
    except Exception:
        return set()


def _changed_files() -> list[str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, creationflags=WINDOWLESS_FLAGS,
        )
    except Exception:
        return []
    baseline = _baseline_paths()
    files = []
    for ln in r.stdout.splitlines():
        path = ln[3:].strip().strip('"')
        if not path or path.lower().endswith(IGNORE_SUFFIXES):
            continue
        if path in baseline:
            continue  # dirty before the session began — not this session's work
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
