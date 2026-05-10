"""Shared boilerplate for V6.0 PreToolUse / PostToolUse hooks.

Every hook does three things:
  1. Read JSON from stdin (the Claude Code tool invocation payload)
  2. Resolve its mode from an env var (enforce/report/off)
  3. Log structured JSONL to state/<hook>.log

This module is the single source of truth for those three operations.
Hook scripts stay thin — they encode policy, not plumbing.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"

VALID_MODES = ("enforce", "report", "off")


def read_hook_input() -> dict[str, Any]:
    """Return the parsed PreToolUse / PostToolUse JSON payload, or empty dict.

    Returns {} when there's no stdin (interactive run, malformed JSON, etc.)
    so callers can short-circuit cleanly.
    """
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def mode_from_env(name: str, default: str = "report") -> str:
    """Resolve a hook's enforcement mode from `EMPIRE_HOOK_*` env var.

    Falls back to `default` if unset or invalid. Always lowercased.
    """
    raw = os.environ.get(name, default)
    if raw is None:
        return default
    val = raw.strip().lower()
    return val if val in VALID_MODES else default


def log_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a JSONL audit record. Best-effort — never raises.

    Auto-stamps `ts` if the caller didn't.
    """
    record.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def state_log_path(hook_name: str) -> Path:
    """Canonical audit log path for a given hook (e.g., `state/exec_guard.log`)."""
    return STATE_DIR / f"{hook_name}.log"
