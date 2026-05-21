"""Parse guard/error logs → surface recurring patterns → suggest MISTAKES.md entries.

Closes the production-error → knowledge-base feedback loop. Without this,
the same error fires for weeks before someone hand-writes a memory entry.
With this, recurring patterns surface automatically; the operator just has
to approve the suggested entry.

Inputs (JSONL):
    state/exec_guard.log
    state/secret_guard.log
    state/secret_access.log
    state/logs/*.log  (anything structured_log writes)

Grouping key: (module, error_type)
Threshold: same key appearing > 3 times in 24h, OR same key across multiple
           modules.

Usage:
    python scripts/core/error_knowledge_pipeline.py scan      # show groups
    python scripts/core/error_knowledge_pipeline.py suggest   # show MISTAKES templates (dry-run)
    python scripts/core/error_knowledge_pipeline.py apply     # append to MISTAKES.md (asks)

Dedup: scans MISTAKES.md for existing entries before suggesting. Same group
key never gets suggested twice.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
LOGS_DIR = STATE_DIR / "logs"
MISTAKES_PATH = PROJECT_ROOT / "memory" / "MISTAKES.md"

DEFAULT_LOG_FILES = [
    STATE_DIR / "exec_guard.log",
    STATE_DIR / "secret_guard.log",
    STATE_DIR / "secret_access.log",
]

DEFAULT_FREQUENCY_THRESHOLD = 3
DEFAULT_WINDOW_HOURS = 24


@dataclass
class ErrorGroup:
    """One (module, error_type) bucket of repeated events."""
    module: str
    error_type: str
    count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sample_message: str = ""
    contexts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.module}::{self.error_type}"


# ── Log parsing ─────────────────────────────────────────────────────────

def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield every JSON object in `path`. Skips malformed lines silently."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def _is_error_event(event: dict[str, Any]) -> bool:
    """A log line is an "error event" if its level is ERROR/CRITICAL, its
    status is fail/blocked, or it has an error_type/exception field."""
    level = str(event.get("level", "")).upper()
    if level in ("ERROR", "CRITICAL"):
        return True
    if event.get("status") in ("fail", "blocked", "denied", "refused"):
        return True
    if "error_type" in event or "exception" in event:
        return True
    return False


def _normalize_event(event: dict[str, Any], source: Path) -> dict[str, Any] | None:
    """Map a raw log line to {module, error_type, ts, message, context}."""
    if not _is_error_event(event):
        return None
    module = (
        event.get("module")
        or event.get("agent")
        or event.get("source")
        or source.stem
    )
    error_type = (
        event.get("error_type")
        or event.get("error")
        or event.get("status")
        or event.get("rule")
        or "unspecified"
    )
    ts = (
        event.get("timestamp")
        or event.get("ts")
        or event.get("time")
        or ""
    )
    message = event.get("message") or event.get("msg") or ""
    return {
        "module": str(module)[:50],
        "error_type": str(error_type)[:80],
        "ts": str(ts),
        "message": str(message)[:200],
        "context": event.get("context") or {k: v for k, v in event.items()
                                            if k not in ("level", "timestamp", "module", "message")},
    }


def parse_logs(paths: Iterable[Path] | None = None) -> list[ErrorGroup]:
    """Bucket every error event into ErrorGroup objects."""
    if paths is None:
        paths = list(DEFAULT_LOG_FILES)
        if LOGS_DIR.exists():
            paths.extend(LOGS_DIR.glob("*.log"))
    groups: dict[str, ErrorGroup] = {}
    for path in paths:
        for raw in _iter_jsonl(path):
            norm = _normalize_event(raw, path)
            if not norm:
                continue
            key = f"{norm['module']}::{norm['error_type']}"
            grp = groups.get(key) or ErrorGroup(module=norm["module"], error_type=norm["error_type"])
            if not grp.first_seen or norm["ts"] < grp.first_seen:
                grp.first_seen = norm["ts"]
            if norm["ts"] > grp.last_seen:
                grp.last_seen = norm["ts"]
            grp.count += 1
            if not grp.sample_message and norm["message"]:
                grp.sample_message = norm["message"]
            if len(grp.contexts) < 3:
                grp.contexts.append(norm["context"])
            groups[key] = grp
    return list(groups.values())


# ── Threshold filtering ─────────────────────────────────────────────────

def _within_window(ts: str, window_hours: int) -> bool:
    if not ts:
        return True  # missing timestamps don't disqualify
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - dt <= timedelta(hours=window_hours)


def filter_recurring(
    groups: list[ErrorGroup],
    threshold: int = DEFAULT_FREQUENCY_THRESHOLD,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> list[ErrorGroup]:
    """Keep groups that fired more than `threshold` times AND are recent."""
    return [
        g for g in groups
        if g.count > threshold and _within_window(g.last_seen, window_hours)
    ]


# ── Dedup against MISTAKES.md ───────────────────────────────────────────

_MISTAKE_KEY_RE = re.compile(
    r"<!--\s*key:\s*(?P<key>[^\s]+)\s*-->", re.IGNORECASE
)


def existing_mistake_keys(mistakes_path: Path | None = None) -> set[str]:
    path = mistakes_path or MISTAKES_PATH
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return {m.group("key") for m in _MISTAKE_KEY_RE.finditer(text)}


# ── Suggestion rendering ────────────────────────────────────────────────

def render_suggestion(group: ErrorGroup) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sample_ctx = group.contexts[0] if group.contexts else {}
    ctx_lines = "\n".join(f"  - `{k}`: {str(v)[:120]}" for k, v in sample_ctx.items())
    return (
        f"## [{group.error_type}] in {group.module} — {today}\n"
        f"<!-- key: {group.key} -->\n"
        f"- **Root cause:** {group.sample_message or '(extract from logs)'}\n"
        f"- **Frequency:** {group.count} occurrences (first {group.first_seen or '?'}, "
        f"last {group.last_seen or '?'})\n"
        f"- **Impact:** {group.module} subsystem; see context below for affected calls.\n"
        f"- **Prevention:** [TODO — operator to fill in once root cause confirmed]\n"
        f"- **Sample context:**\n"
        f"{ctx_lines if ctx_lines else '  (no structured context captured)'}\n"
        f"- **Status:** [PROBATIONARY]\n"
    )


# ── Command surface ─────────────────────────────────────────────────────

def cmd_scan(args: argparse.Namespace) -> int:
    groups = parse_logs()
    if args.json:
        print(json.dumps([
            {"module": g.module, "error_type": g.error_type, "count": g.count,
             "first_seen": g.first_seen, "last_seen": g.last_seen}
            for g in groups
        ], indent=2))
    else:
        for g in sorted(groups, key=lambda x: x.count, reverse=True):
            print(f"  {g.count:5d}  {g.module:25s} {g.error_type}")
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    groups = parse_logs()
    recurring = filter_recurring(groups, args.threshold, args.window_hours)
    known = existing_mistake_keys()
    new_groups = [g for g in recurring if g.key not in known]
    if not new_groups:
        print("(no new patterns above threshold; nothing to suggest)")
        return 0
    for g in new_groups:
        print(render_suggestion(g))
        print()
    if args.json:
        print(json.dumps({
            "new_count": len(new_groups),
            "deduped_against_existing": len(recurring) - len(new_groups),
        }))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    groups = parse_logs()
    recurring = filter_recurring(groups, args.threshold, args.window_hours)
    known = existing_mistake_keys()
    new_groups = [g for g in recurring if g.key not in known]
    if not new_groups:
        print("(no new patterns; MISTAKES.md unchanged)")
        return 0

    appended = ""
    for g in new_groups:
        appended += "\n---\n\n" + render_suggestion(g)

    if not args.yes:
        print("Would append the following to MISTAKES.md (re-run with --yes to apply):")
        print(appended)
        return 0

    MISTAKES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MISTAKES_PATH.open("a", encoding="utf-8") as f:
        f.write(appended)
    print(f"Appended {len(new_groups)} entries to {MISTAKES_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)

    s = sub.add_parser("scan", help="parse logs and show error groups")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("suggest", help="dry-run: print MISTAKES.md templates")
    s.add_argument("--threshold", type=int, default=DEFAULT_FREQUENCY_THRESHOLD)
    s.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_suggest)

    s = sub.add_parser("apply", help="append new patterns to MISTAKES.md")
    s.add_argument("--threshold", type=int, default=DEFAULT_FREQUENCY_THRESHOLD)
    s.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS)
    s.add_argument("--yes", action="store_true", help="skip preview, append immediately")
    s.set_defaults(func=cmd_apply)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
