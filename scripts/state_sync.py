"""
State Sync — Single-Write Protocol for Fragmented Memory
Syncs a key observation/update across all 3 active memory layers simultaneously:
  1. brain/STATE.md  — heartbeat timestamp + last result
  2. memory/SESSION_LOG.md — append session entry
  3. scripts/mem0_tool.py  — semantic memory (add observation)

Usage:
  python scripts/state_sync.py --note "Semi-auto outreach: 3 leads sent to Telegram"
  python scripts/state_sync.py --heartbeat          # Just refresh timestamp
  python scripts/state_sync.py --status "✅ LIVE"   # Update tool status in STATE
  python scripts/state_sync.py --note "..." --mem0  # Also write to semantic memory

This is the MANDATORY end-of-session sync. Run it after every meaningful change.
One command → three memory layers updated. No more fragmentation.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / "brain" / "STATE.md"
SESSION_LOG = PROJECT_ROOT / "memory" / "SESSION_LOG.md"


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def update_state_heartbeat(note: str):
    """Update the Last Heartbeat section in STATE.md."""
    content = STATE_FILE.read_text(encoding="utf-8")

    new_heartbeat = (
        f"## Last Heartbeat\n\n"
        f"- **Date:** {now_str()}\n"
        f"- **Agent:** BRAVO via Claude Code (Sonnet 4.6)\n"
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


def append_session_log(note: str):
    """Append a compact entry to SESSION_LOG.md."""
    entry = (
        f"\n### {now_str()} — Auto-sync\n"
        f"**Agent:** BRAVO state_sync\n"
        f"**Note:** {note}\n"
    )
    content = SESSION_LOG.read_text(encoding="utf-8")
    # Insert after the header block (before first ### entry)
    insert_at = content.find("\n### ")
    if insert_at == -1:
        SESSION_LOG.write_text(content.rstrip() + entry + "\n", encoding="utf-8")
    else:
        SESSION_LOG.write_text(content[:insert_at] + entry + content[insert_at:], encoding="utf-8")
    return True


def sync_mem0(note: str):
    """Add observation to semantic memory via mem0_tool.py."""
    python = sys.executable
    result = subprocess.run(
        [python, str(PROJECT_ROOT / "scripts" / "mem0_tool.py"), "add",
         f"[state_sync] {note}", "--user", "bravo"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=30
    )
    return result.returncode == 0


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="State sync — single write to all memory layers")
    parser.add_argument("--note", "-n", default="", help="Observation to sync across all memory layers")
    parser.add_argument("--heartbeat", action="store_true", help="Just refresh the STATE.md heartbeat timestamp")
    parser.add_argument("--mem0", action="store_true", help="Also write to semantic memory (mem0)")
    args = parser.parse_args()

    note = args.note.strip() if args.note else "Session sync."

    results = {}

    # 1. STATE.md heartbeat
    try:
        update_state_heartbeat(note)
        results["STATE.md"] = "✅"
    except Exception as e:
        results["STATE.md"] = f"❌ {e}"

    # 2. SESSION_LOG.md (skip for --heartbeat only)
    if not args.heartbeat:
        try:
            append_session_log(note)
            results["SESSION_LOG.md"] = "✅"
        except Exception as e:
            results["SESSION_LOG.md"] = f"❌ {e}"

    # 3. mem0 semantic memory (opt-in via --mem0)
    if args.mem0:
        try:
            ok = sync_mem0(note)
            results["mem0"] = "✅" if ok else "⚠️ mem0 write failed"
        except Exception as e:
            results["mem0"] = f"❌ {e}"

    summary = " | ".join(f"{k}: {v}" for k, v in results.items())
    print(f"[state_sync] {summary}")
    print(f"[state_sync] Note: {note}")


if __name__ == "__main__":
    main()
