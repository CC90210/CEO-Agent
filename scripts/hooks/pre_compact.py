"""PreCompact hook — re-inject identity + active tasks before compaction.

Claude Code fires PreCompact when the conversation is about to be summarized.
Without this hook, the agent loses CLAUDE.md principles, identity values, and
current task focus after compression. This hook re-injects a compact version
so the post-compression agent picks up where the pre-compression one left off.

Output contract (Claude Code PreCompact hook):
    {
      "hookSpecificOutput": {
        "hookEventName": "PreCompact",
        "additionalContext": "<markdown block>"
      }
    }

Wired in .claude/settings.local.json PreCompact matcher.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
LOG_PATH = STATE_DIR / "pre_compact.log"

SOUL_HEAD_LINES = 40
ACTIVE_TASKS_MAX_BYTES = 2000
DECISIONS_TAIL_LINES = 30


def _log(payload: dict) -> None:
    try:
        STATE_DIR.mkdir(exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _read_head(path: Path, n: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readline() for _ in range(n)).rstrip()
    except OSError:
        return ""


def _read_tail_bytes(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(data) <= max_bytes:
        return data.rstrip()
    return ("...\n" + data[-max_bytes:]).rstrip()


def _recent_decisions(path: Path, n_lines: int) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n_lines:]).rstrip()


def main() -> int:
    try:
        _ = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        pass

    soul = _read_head(PROJECT_ROOT / "brain" / "SOUL.md", SOUL_HEAD_LINES)
    active = _read_tail_bytes(PROJECT_ROOT / "memory" / "ACTIVE_TASKS.md", ACTIVE_TASKS_MAX_BYTES)
    decisions = _recent_decisions(PROJECT_ROOT / "memory" / "DECISIONS.md", DECISIONS_TAIL_LINES)

    parts: list[str] = []
    parts.append(
        "## Identity (post-compact re-injection)\n"
        "You are Bravo, CC's Lead Architect. Compaction just ran — these are the invariants you must carry through. "
        "Full rules in CLAUDE.md, but do not re-load files unless needed."
    )
    if soul:
        parts.append(f"### Soul (brain/SOUL.md, first {SOUL_HEAD_LINES} lines)\n```\n{soul}\n```")
    if active:
        parts.append(f"### Active Tasks (memory/ACTIVE_TASKS.md tail)\n```\n{active}\n```")
    if decisions:
        parts.append(f"### Recent Decisions (memory/DECISIONS.md tail)\n```\n{decisions}\n```")

    context = "\n\n".join(parts)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    _log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "soul_chars": len(soul),
        "active_chars": len(active),
        "decisions_chars": len(decisions),
    })
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        _log({"ts": datetime.now(timezone.utc).isoformat(), "status": "error", "error": str(e)})
        print(json.dumps({}))
        raise SystemExit(0)
