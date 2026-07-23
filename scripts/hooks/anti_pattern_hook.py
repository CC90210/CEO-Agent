"""PreToolUse hook — scans the about-to-execute Bash command against a list
of regex anti-patterns derived from logged mistakes. Pure regex, zero LLM
cost, fires per-tool-use in <50ms.

Patterns live in `memory/ANTI_PATTERNS.json` so they can grow without
editing settings.local.json. Each entry: {pattern, message, tag}.

Outputs a Claude Code hook decision JSON:
  - {decision: "allow"} (default — silent pass)
  - {decision: "allow", reason: "..."} (warn but allow — patterns flagged)
  - {decision: "block", reason: "..."} (only for explicit `block: true`)

Reads stdin (CLAUDE_TOOL_INPUT). Writes JSON to stdout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERNS_FILE = REPO_ROOT / "memory" / "ANTI_PATTERNS.json"


def load_patterns() -> list[dict]:
    if not PATTERNS_FILE.exists():
        return []
    try:
        return json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"decision": "allow"}))
        return 0

    # PreToolUse payload schema is {"tool_name": ..., "tool_input": {"command"/"script": ...}}.
    # (The old code read payload["command"] / payload["input"]["command"], which never
    #  exist in Claude Code's schema — so the hook silently allowed everything. Caught by
    #  APEX 2026-07-20; aligned here with exec_guard/secret_guard's reader.)
    tool_input = payload.get("tool_input", {}) or {}
    cmd = tool_input.get("command", "") or tool_input.get("script", "")
    if not cmd:
        print(json.dumps({"decision": "allow"}))
        return 0

    patterns = load_patterns()
    matches = []
    blocking = False
    for entry in patterns:
        pat = entry.get("pattern")
        if not pat:
            continue
        try:
            if re.search(pat, cmd, flags=re.IGNORECASE):
                matches.append(entry)
                if entry.get("block"):
                    blocking = True
        except re.error:
            continue

    if not matches:
        print(json.dumps({"decision": "allow"}))
        return 0

    msgs = []
    for m in matches:
        tag = m.get("tag", "")
        msg = m.get("message", "anti-pattern detected")
        msgs.append(f"[{tag}] {msg}" if tag else msg)
    reason = "ANTI-PATTERN: " + " | ".join(msgs)
    decision = "block" if blocking else "allow"
    print(json.dumps({"decision": decision, "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
