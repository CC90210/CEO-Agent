"""SessionStart hook — injects state + inbox + staleness report.

Fired by Claude Code at the start of every new session. Reads stdin (session
metadata from CC), runs three fast Python lookups in parallel-ish, and emits
a single JSON block via additionalContext so the agent boots with current
state instead of having to ask "what's my status?"

Output contract (Claude Code SessionStart hook):
    {
      "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "<markdown block>"
      }
    }

Fast-fails on error — never blocks session startup. Worst case: empty context.
Logs to state/session_start.log for observability.

Wired in .claude/settings.local.json SessionStart matcher.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
_p = Path(__file__).resolve()
while _p.parent != _p and not (_p / "scripts" / "_subprocess_helpers.py").exists():
    _p = _p.parent
sys.path.insert(0, str(_p / "scripts"))
from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "state"
LOG_PATH = STATE_DIR / "session_start.log"
GIT_BASELINE_PATH = STATE_DIR / "session_git_baseline.json"
TIMEOUT_SEC = 3


def _resolve_py() -> str:
    """Console python with the repo's deps. Prefer the venv (system python may lack
    them); avoid windowless pythonw (unreliable stdout capture). On macOS bare
    `python` often doesn't exist — using the venv python3 keeps SessionStart working."""
    venv = PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
    if venv.exists():
        return str(venv)
    exe = sys.executable or ""
    if exe and Path(exe).name.lower().startswith("pythonw"):
        sib = Path(exe).with_name(Path(exe).name.lower().replace("pythonw", "python"))
        if sib.exists():
            return str(sib)
    return exe or ("python" if os.name == "nt" else "python3")


PY = _resolve_py()


def _log(payload: dict) -> None:
    try:
        STATE_DIR.mkdir(exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _run(cmd: list[str], timeout: int = TIMEOUT_SEC) -> str | None:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
            errors="replace",
         creationflags=WINDOWLESS_FLAGS)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def _run_raw(cmd: list[str], timeout: int = TIMEOUT_SEC) -> str | None:
    """Like _run, but WITHOUT stripping — for output parsed by column.

    `_run` returns `stdout.strip()`, which is right for the scalar values it is
    otherwise used for and fatally wrong for `git status --porcelain`: the strip
    eats the leading space of the FIRST line only, so a ` M brain/CAPABILITIES.md`
    line was read as `M brain/CAPABILITIES.md` and `ln[3:]` returned
    `rain/CAPABILITIES.md`.

    That truncated path went into the session baseline, so the SubagentStop gate
    saw the REAL `brain/CAPABILITIES.md` as new-this-session and nagged about a
    file that was already dirty at boot — which is the failure mode the baseline
    exists to prevent, and which on 2026-07-02 pressured a read-only agent into
    destructive remediation.

    Found 2026-08-29 in the live baseline (`rain/CAPABILITIES.md`), after the
    identical defect was fixed in review_fix.py an hour earlier. Same bug, second
    file: a fix applied where it was noticed rather than to the class.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            encoding="utf-8",
            errors="replace",
            creationflags=WINDOWLESS_FLAGS)
        if result.returncode != 0:
            return None
        return result.stdout or None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def _state_summary() -> str:
    raw = _run([PY, "scripts/state/state_manager.py", "status"])
    if not raw:
        return ""
    lines = raw.splitlines()[:12]
    return "\n".join(lines)


def _inbox_summary() -> str:
    raw = _run([PY, "scripts/core/agent_inbox.py", "list", "--to", "bravo", "--json"])
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ""
    msgs = data if isinstance(data, list) else data.get("messages", [])
    if not msgs:
        return "(inbox empty)"
    urgent = [m for m in msgs if m.get("priority") in ("urgent", "high")]
    show = urgent[:3] if urgent else msgs[:3]
    out = [f"{len(msgs)} unread ({len(urgent)} urgent/high):"]
    for m in show:
        sender = m.get("from", "?")
        subj = m.get("subject", "(no subject)")[:60]
        prio = m.get("priority", "normal")
        out.append(f"  - [{prio}] {sender}: {subj}")
    return "\n".join(out)


def _rotate_logs_if_needed() -> None:
    """Fire-and-forget. rotate_logs.py is idempotent (12h stamp) and silent if no rotation."""
    _run([PY, "scripts/hooks/rotate_logs.py"], timeout=5)


def _staleness_summary() -> str:
    raw = _run([PY, "scripts/core/memory_aging.py", "stale", "--days", "7", "--json"])
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ""
    items = data if isinstance(data, list) else data.get("stale", []) or data.get("entries", [])
    if not items:
        return "(no stale entries)"
    return f"{len(items)} memory files stale (>7 days). Run `memory_aging.py stale` for details."


def _parity_summary() -> str:
    """Self-announce machine-parity drift at boot (the 'automatic after pull' net).

    Runs the cheap --fast subset (hooks + global config, pure file reads). Prints
    one line iff this machine is NOT at parity, e.g. a fresh clone with no hooks
    installed. Fail-open: any error → silent.
    """
    raw = _run([PY, "scripts/machine_parity.py", "--check", "--fast", "--quiet"], timeout=5)
    return raw or ""


def _event_router_freshness() -> str:
    """Warn if the V6 Apex event_router cursor hasn't advanced in >7 days.

    Silent observability: if event-router stalls, no error fires — the queue
    just stops draining. This check surfaces that gap at SessionStart so the
    operator notices before the gap costs them anything. Returns "" on
    healthy cursor; a single-line warning string otherwise.
    """
    cursor = STATE_DIR / "event_router.cursor"
    if not cursor.exists():
        return ""
    try:
        age_days = (datetime.now(timezone.utc).timestamp() - cursor.stat().st_mtime) / 86400
    except OSError:
        return ""
    if age_days < 7:
        return ""
    return (
        f"event_router cursor idle {int(age_days)}d — last advance "
        f"{datetime.fromtimestamp(cursor.stat().st_mtime, tz=timezone.utc).date().isoformat()}. "
        f"`pm2 logs event-router` to investigate."
    )


def _write_git_baseline() -> None:
    """Snapshot the paths already dirty at session start.

    The SubagentStop validator gate reads this to distinguish files a sub-agent
    changed *during* the session from files that were already dirty when the
    session began. Without it, the gate nags (and once, pressured a read-only
    agent into destructive `git checkout`/`rm` remediation — 2026-07-02 incident,
    see memory/MISTAKES.md). Fail-open: any error leaves no baseline and the gate
    falls back to reporting all dirty files (advisory only, never destructive).
    """
    raw = _run_raw(["git", "status", "--porcelain"], timeout=5)
    # Map path -> 2-char porcelain status code. The validator gate flags a file
    # if it's new OR its status changed vs this baseline — so a sub-agent editing
    # a file that was ALREADY dirty at boot (status transition) is still caught,
    # while pre-existing dirt at the same status is ignored (Codex audit P2).
    dirty = {}
    if raw:
        for ln in raw.splitlines():
            if len(ln) < 4:
                continue          # not a `XY PATH` record
            code = ln[:2]
            p = ln[3:].strip().strip('"')
            if " -> " in p:       # rename: the destination is the live path
                p = p.split(" -> ", 1)[1].strip().strip('"')
            if p:
                dirty[p] = code
    try:
        STATE_DIR.mkdir(exist_ok=True)
        with GIT_BASELINE_PATH.open("w", encoding="utf-8") as f:
            json.dump({
                "ts": datetime.now(timezone.utc).isoformat(),
                "dirty": dirty,
                "dirty_paths": sorted(dirty),  # back-compat
            }, f)
    except Exception:
        pass


def main() -> int:
    try:
        _ = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        pass

    _write_git_baseline()
    _rotate_logs_if_needed()
    state = _state_summary()
    inbox = _inbox_summary()
    stale = _staleness_summary()
    router_idle = _event_router_freshness()
    parity = _parity_summary()

    parts: list[str] = []
    if parity:
        parts.append(f"## Machine Parity\n{parity}")
    if state:
        parts.append(f"## Current State\n```\n{state}\n```")
    if inbox:
        parts.append(f"## Agent Inbox (to: bravo)\n{inbox}")
    if stale:
        parts.append(f"## Memory Staleness\n{stale}")
    if router_idle:
        parts.append(f"## Event Router\n{router_idle}")

    if not parts:
        print(json.dumps({}))
        _log({"ts": datetime.now(timezone.utc).isoformat(), "status": "empty"})
        return 0

    context = "\n\n".join(parts)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    _log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "state_chars": len(state),
        "inbox_chars": len(inbox),
        "stale_chars": len(stale),
    })
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        _log({"ts": datetime.now(timezone.utc).isoformat(), "status": "error", "error": str(e)})
        print(json.dumps({}))
        raise SystemExit(0)
