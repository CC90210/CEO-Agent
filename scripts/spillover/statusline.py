#!/usr/bin/env python3
"""statusline.py - Claude Code status line for Claude Spillover (CONTRACT section 12).

Claude Code pipes a JSON document to stdin on every status-line refresh. This
prints ONE line built from it and from HOME_DIR/state/state.json:

  Opus 5 | 5h 72% reset 14:10 | 7d 41% | direct
  FALLBACK (GPT) until 14:10
  limit hit - fallback DOWN until 14:10

Fields read from stdin (all optional): model.display_name / model.id, and
rate_limits.five_hour / rate_limits.seven_day -> used_percentage, resets_at
(epoch seconds, epoch ms, or ISO 8601).

No network, no subprocess, stdlib only. It never raises and always exits 0, so a
bad payload or a missing state file can only make the line shorter. Launch it with
`python -S`: the venv's site import costs ~2 s. HOME_DIR is %LOCALAPPDATA%\\bravo-spillover
(Windows) or ~/Library/Application Support/bravo-spillover (macOS); the env var
BRAVO_SPILLOVER_HOME overrides it (tests).
"""
from __future__ import annotations

import json
import os
import sys
import time

MAX_INPUT_BYTES = 1_000_000


def home_dir() -> str:
    override = os.environ.get("BRAVO_SPILLOVER_HOME")
    if override:
        return override
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "bravo-spillover")
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "bravo-spillover")


def _get(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _epoch(value) -> float | None:
    """Seconds since the epoch from a number (s or ms) or an ISO 8601 string."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        secs = float(value)
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            secs = float(text)
        except ValueError:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
    else:
        return None
    if secs > 1e11:  # milliseconds
        secs /= 1000.0
    return secs if secs > 0 else None


def _clock(epoch: float, now: float) -> str:
    """Local HH:MM, with the weekday when the time is not today."""
    when, today = time.localtime(epoch), time.localtime(now)
    fmt = "%H:%M" if when[:3] == today[:3] else "%a %H:%M"
    return time.strftime(fmt, when)


def _pct(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN
        return None
    return max(0, min(999, int(round(num))))


def read_state(path: str | None = None) -> dict | None:
    """None when there is no state file; {} when it exists but cannot be read."""
    path = path or os.path.join(home_dir(), "state", "state.json")
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_INPUT_BYTES)
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def render(payload: dict, state: dict | None, now: float) -> str:
    if state:
        limit = state.get("limit") if isinstance(state.get("limit"), dict) else {}
        reset = _epoch(limit.get("reset_at"))
        if state.get("mode") == "spilling" and (reset is None or reset > now):
            until = f" until {_clock(reset, now)}" if reset else ""
            if _get(state, "fallback", "healthy") is False:
                return f"limit hit - fallback DOWN{until}"
            return f"FALLBACK (GPT){until}"

    model = _get(payload, "model", "display_name") or _get(payload, "model", "id") or "Claude"
    parts = [str(model)[:40]]

    five = _pct(_get(payload, "rate_limits", "five_hour", "used_percentage"))
    if five is not None:
        seg = f"5h {five}%"
        reset5 = _epoch(_get(payload, "rate_limits", "five_hour", "resets_at"))
        if reset5 and reset5 > now:
            seg += f" reset {_clock(reset5, now)}"
        parts.append(seg)
    seven = _pct(_get(payload, "rate_limits", "seven_day", "used_percentage"))
    if seven is not None:
        parts.append(f"7d {seven}%")

    if state is not None:
        if not state:
            parts.append("proxy ?")
        else:
            cfg = state.get("config_mode")
            if cfg == "passthrough":
                parts.append("passthrough")
            elif cfg == "observe":
                parts.append("direct (observe)")
            else:
                parts.append("direct")
    return " | ".join(parts)


def _read_payload() -> dict:
    stdin = sys.stdin
    if stdin is None or stdin.isatty():
        return {}
    raw = stdin.buffer.read(MAX_INPUT_BYTES)
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    try:
        line = render(_read_payload(), read_state(), time.time())
    except BaseException:  # noqa: BLE001 - a status line must never crash the UI
        line = "Claude"
    try:
        sys.stdout.write(line.encode("ascii", "replace").decode("ascii") + "\n")
        sys.stdout.flush()
    except BaseException:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
