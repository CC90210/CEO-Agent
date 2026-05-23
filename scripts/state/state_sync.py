"""
State Sync — Single-Write Protocol for Fragmented Memory.

Behavior is gated by `EMPIRE_V6_MODE` (env var, falls back to .env.agents):
  - off    (default) → V5.5 path only: flat-file writes to STATE.md + SESSION_LOG.md.
  - shadow           → V5.5 path runs first, then state_manager.py mirrors the same
                       write into state/empire_state.db (best-effort, never fails the sync).
                       Use for the V6.0 soak period to prove DB parity with no risk.
  - on               → DB is source of truth: state_manager.py writes the row,
                       export_markdown() regenerates the markdown mirrors.
                       The V5.5 flat-file path is skipped entirely.

Usage (CLI surface preserved across modes):
  python scripts/state/state_sync.py --note "Semi-auto outreach: 3 leads sent to Telegram"
  python scripts/state/state_sync.py --heartbeat          # Just refresh timestamp
  python scripts/state/state_sync.py --note "..." --mem0  # Also write to semantic memory
  python scripts/state/state_sync.py --note "..." --mode shadow  # Override env var ad-hoc

This is the MANDATORY end-of-session sync.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# After the 2026-05 scripts/ reorg, this file lives under scripts/state/ but
# still imports flat-layout siblings (_subprocess_helpers from scripts/,
# agent_heartbeat from scripts/core/). Inject both onto sys.path so the
# script works as a CLI entry point regardless of where it's invoked from.
_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent.parent
for _p in (_SCRIPTS, _SCRIPTS / "core", _SCRIPTS / "state"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _subprocess_helpers import WINDOWLESS_FLAGS  # noqa: E402

PROJECT_ROOT = _SCRIPTS.parent
STATE_FILE = PROJECT_ROOT / "brain" / "STATE.md"
SESSION_LOG = PROJECT_ROOT / "memory" / "SESSION_LOG.md"


def _resolve_v6_mode(cli_override: str | None) -> str:
    """Pick the V6 mode from --mode > env > .env.agents > 'off'."""
    if cli_override:
        return cli_override.lower()
    env = os.environ.get("EMPIRE_V6_MODE")
    if env:
        return env.lower()
    env_file = PROJECT_ROOT / ".env.agents"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("EMPIRE_V6_MODE="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'").lower() or "off"
        except OSError:
            pass
    return "off"

# Force UTF-8 stdout/stderr on Windows so emoji status glyphs (✅ ❌ ⚠️)
# don't crash the "MANDATORY end-of-session sync" with UnicodeEncodeError
# under cp1252. Cheap to do, safe on every platform.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_agent_label(agent_name: str = "bravo") -> str:
    """Return the agent label for heartbeat entries.

    Reads from .agents/config.toml if present, else CLAUDE_MODEL env var,
    else a neutral fallback. Never hardcodes a model version.
    """
    normalized = (agent_name or "bravo").lower().strip()
    label_override = os.environ.get("BRAVO_AGENT_LABEL")
    if label_override:
        return label_override
    if normalized != "bravo":
        return f"{normalized.upper()} via state_sync"
    config_path = PROJECT_ROOT / ".agents" / "config.toml"
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("model"):
                    # e.g. model = "claude-opus-4-6[1m]"
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return f"BRAVO via Claude Code ({val})"
        except Exception:
            pass
    return "BRAVO via Claude Code"


def update_state_heartbeat(note: str, agent_name: str = "bravo"):
    """Update the Last Heartbeat section in STATE.md."""
    content = STATE_FILE.read_text(encoding="utf-8")

    new_heartbeat = (
        f"## Last Heartbeat\n\n"
        f"- **Date:** {now_str()}\n"
        f"- **Agent:** {get_agent_label(agent_name)}\n"
        f"- **Result:** {note}\n\n"
        f"*Last updated: {now_str()}*"
    )

    # Replace existing heartbeat block
    pattern = r"## Last Heartbeat\n.*?\*Last updated:.*?\*"
    updated = re.sub(pattern, new_heartbeat, content, flags=re.DOTALL)

    if updated == content:
        # Append if pattern not found
        updated = content.rstrip() + "\n\n" + new_heartbeat + "\n"

    STATE_FILE.write_text(updated, encoding="utf-8")
    return True


def append_session_log(note: str, agent_name: str = "bravo") -> str:
    """Append a compact entry to SESSION_LOG.md.

    Dedupe guard: if the most recent Auto-sync entry (same day, same note)
    matches, skip the append and return "deduped". This prevents the
    fragmentation CC has seen when state_sync is called multiple times
    from cron or parallel sessions with the same note.
    """
    today = now_str()
    agent_label = (agent_name or "bravo").upper()
    entry = (
        f"\n### {today} — Auto-sync\n"
        f"**Agent:** {agent_label} state_sync\n"
        f"**Note:** {note}\n"
    )
    content = SESSION_LOG.read_text(encoding="utf-8")

    # Dedupe: scan the first ~3 existing entries; if one matches date+note exactly, skip.
    # This is cheap and handles the "scheduler calls me every cron tick with same note" case.
    dedupe_marker = f"### {today} — Auto-sync"
    note_marker = f"**Note:** {note}"
    recent_block_end = content.find("\n### ", content.find("\n### ") + 1)  # end of first entry
    recent_block = content[: recent_block_end if recent_block_end > 0 else len(content)]
    if dedupe_marker in recent_block and note_marker in recent_block:
        return "deduped"

    # Insert after the header block (before first ### entry)
    insert_at = content.find("\n### ")
    if insert_at == -1:
        SESSION_LOG.write_text(content.rstrip() + entry + "\n", encoding="utf-8")
    else:
        SESSION_LOG.write_text(content[:insert_at] + entry + content[insert_at:], encoding="utf-8")
    return "appended"


def sync_mem0(note: str):
    """Add observation to semantic memory via mem0_tool.py."""
    python = sys.executable
    result = subprocess.run(
        [python, str(PROJECT_ROOT / "scripts" / "mem0_tool.py"), "add",
         f"[state_sync] {note}", "--user", "bravo"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=30
    , creationflags=WINDOWLESS_FLAGS)
    return result.returncode == 0


# ── Main ───────────────────────────────────────────────────────────────────────

def _v6_write(mode: str, note: str, agent_name: str, results: dict, heartbeat_only: bool) -> None:
    """Mirror the sync into state/empire_state.db. Best-effort; never raises."""
    if mode == "off":
        return
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from state_manager import (
            heartbeat as sm_heartbeat,
            append_session_log as sm_append,
            export_markdown as sm_export,
        )
    except Exception as e:  # noqa: BLE001
        results["state_manager"] = f"⚠️ import failed: {e}"
        return
    try:
        sm_heartbeat(agent=agent_name, status="working", focus=note)
        if not heartbeat_only:
            sm_append(note=note, agent=agent_name)
        if mode == "on":
            sm_export()
        results["state_manager"] = f"✅ ({mode})"
    except Exception as e:  # noqa: BLE001
        results["state_manager"] = f"⚠️ {e}"


def main():
    parser = argparse.ArgumentParser(description="State sync — single write to all memory layers")
    parser.add_argument("--note", "-n", default="", help="Observation to sync across all memory layers")
    parser.add_argument("--heartbeat", action="store_true", help="Just refresh the STATE.md heartbeat timestamp")
    parser.add_argument("--mem0", action="store_true", help="Also write to semantic memory (mem0)")
    parser.add_argument(
        "--agent",
        default=os.environ.get("STATE_SYNC_AGENT", "bravo"),
        choices=["bravo", "atlas", "maven", "hermes", "codex", "aura"],
        help="Agent to mark live in agent_state_snapshot (default: bravo)",
    )
    parser.add_argument(
        "--mode",
        default=None,
        choices=["off", "shadow", "on"],
        help="Override EMPIRE_V6_MODE for this invocation",
    )
    args = parser.parse_args()

    note = args.note.strip() if args.note else "Session sync."
    agent_name = args.agent.lower().strip()
    v6_mode = _resolve_v6_mode(args.mode)

    results = {"v6_mode": v6_mode}

    # V5.5 flat-file path runs in 'off' and 'shadow' modes only.
    if v6_mode in ("off", "shadow"):
        try:
            update_state_heartbeat(note, agent_name)
            results["STATE.md"] = "✅"
        except Exception as e:
            results["STATE.md"] = f"❌ {e}"

        if not args.heartbeat:
            try:
                action = append_session_log(note, agent_name)
                results["SESSION_LOG.md"] = "✅ (deduped)" if action == "deduped" else "✅"
            except Exception as e:
                results["SESSION_LOG.md"] = f"❌ {e}"

    # V6.0 DB path runs in 'shadow' and 'on' modes.
    _v6_write(v6_mode, note, agent_name, results, args.heartbeat)

    if args.mem0:
        try:
            ok = sync_mem0(note)
            results["mem0"] = "✅" if ok else "⚠️ mem0 write failed"
        except Exception as e:
            results["mem0"] = f"❌ {e}"

    # Supabase agent_state_snapshot mirror.
    # In shadow/on modes, state_manager.heartbeat() already pushed it as part
    # of its single-writer contract. Only fire the standalone path in 'off'
    # mode where state_manager wasn't called.
    if v6_mode == "off":
        try:
            from agent_heartbeat import heartbeat
            ok = heartbeat(agent_name, working_memory={"last_note": note[:200]})
            results["heartbeat"] = "✅" if ok else "⚠️ heartbeat skipped"
        except Exception as e:
            results["heartbeat"] = f"❌ {e}"

    summary = " | ".join(f"{k}: {v}" for k, v in results.items())
    print(f"[state_sync] {summary}")
    print(f"[state_sync] Note: {note}")


if __name__ == "__main__":
    main()
