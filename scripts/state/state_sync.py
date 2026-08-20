"""
State Sync — Single-Write Protocol for Fragmented Memory.

Behavior is gated by `EMPIRE_V6_MODE` (env var, falls back to .env.agents):
  - off              → V5.5 path only: flat-file writes to STATE.md + SESSION_LOG.md.
  - shadow (default) → V5.5 path runs first, then state_manager.py mirrors the same
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
  python scripts/state/state_sync.py --note "..." --domain marketing  # Also ping Maven/Atlas (CC 2026-08-01)

This is the MANDATORY end-of-session sync.
"""

from __future__ import annotations

import argparse
import json
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
from lib.timeutil import age_days  # noqa: E402

PROJECT_ROOT = _SCRIPTS.parent
STATE_FILE = PROJECT_ROOT / "brain" / "STATE.md"
SESSION_LOG = PROJECT_ROOT / "memory" / "SESSION_LOG.md"
DEFAULT_V6_MODE = "shadow"

_FRONTMATTER_BLOCK = re.compile(
    r"---[ \t]*\r?\n(?P<body>.*?)^---[ \t]*(?:\r?\n|\Z)",
    flags=re.DOTALL | re.MULTILINE,
)


def _resolve_v6_mode(cli_override: str | None) -> str:
    """Pick the V6 mode from --mode > env > .env.agents > tracked default.

    `shadow` is intentionally runtime-neutral. Claude injects the setting from
    `.claude/settings.json`, but Codex/OpenCode do not; falling back to `off`
    made identical end-of-session commands update different state layers.
    """
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
                    return (line.split("=", 1)[1].strip().strip('"').strip("'").lower()
                            or DEFAULT_V6_MODE)
        except OSError:
            pass
    return DEFAULT_V6_MODE

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


def normalize_session_log_frontmatter(content: str, updated_date: str) -> tuple[str, int]:
    """Return SESSION_LOG content with exactly one leading frontmatter block.

    Only consecutive YAML blocks at the start of the file are collapsed. The
    first block remains authoritative, its metadata is preserved, and only its
    ``last_updated`` value is refreshed. Every session entry remains present.

    Returns ``(normalized_content, duplicate_blocks_removed)``.
    """
    newline = "\r\n" if "\r\n" in content else "\n"
    bom = "\ufeff" if content.startswith("\ufeff") else ""
    cursor = len(bom)
    bodies: list[str] = []

    while True:
        match = _FRONTMATTER_BLOCK.match(content, cursor)
        if not match:
            break
        bodies.append(match.group("body"))
        cursor = match.end()

        # Tolerate blank lines between accidentally repeated blocks, but keep
        # that whitespace when the next thing is a real session entry.
        gap = re.match(r"(?:[ \t]*\r?\n)*", content[cursor:])
        candidate = cursor + (gap.end() if gap else 0)
        if _FRONTMATTER_BLOCK.match(content, candidate):
            cursor = candidate

    if bodies:
        metadata = bodies[0].splitlines()
    else:
        metadata = ["tags: [daily]", "freshness_threshold_days: 14"]
        cursor = len(bom)

    refreshed = False
    for index, line in enumerate(metadata):
        if re.match(r"^\s*last_updated\s*:", line):
            prefix = line[:len(line) - len(line.lstrip())]
            metadata[index] = f"{prefix}last_updated: {updated_date}"
            refreshed = True
            break
    if not refreshed:
        metadata.append(f"last_updated: {updated_date}")

    frontmatter = (
        f"{bom}---{newline}"
        + newline.join(metadata)
        + f"{newline}---{newline}"
    )
    return frontmatter + content[cursor:], max(0, len(bodies) - 1)


def repair_session_log_frontmatter(path: Path | None = None) -> tuple[int, int]:
    """Atomically repair repeated SESSION_LOG frontmatter without adding state.

    Returns ``(duplicate_blocks_removed, session_entries_preserved)``. This is
    intentionally separate from a normal state sync so an operator can repair
    structure first, verify entry counts, and only then resume dual writes.
    """
    target = path or SESSION_LOG
    original = target.read_text(encoding="utf-8")
    entry_count = len(re.findall(r"(?m)^###\s+", original))
    normalized, removed = normalize_session_log_frontmatter(original, now_str())
    if normalized != original:
        temporary = target.with_suffix(target.suffix + ".repair.tmp")
        temporary.write_text(normalized, encoding="utf-8")
        temporary.replace(target)
    preserved = len(re.findall(r"(?m)^###\s+", normalized))
    if preserved != entry_count:
        raise RuntimeError(
            f"SESSION_LOG repair changed entry count ({entry_count} -> {preserved})"
        )
    return removed, preserved


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
                if line.startswith("model") and "=" in line:
                    # e.g.  model = "claude-fable-5"   # Lead (Bravo)
                    # Extract the quoted value WITHOUT the trailing inline comment.
                    # The old code (.strip('"')) left the "# Lead architect ..."
                    # comment attached, which corrupted the STATE.md Agent line
                    # (2026-07-02 incident, see memory/MISTAKES.md).
                    rhs = line.split("=", 1)[1].strip()
                    if rhs[:1] in ("\"", "'"):
                        q = rhs[0]
                        end = rhs.find(q, 1)
                        val = rhs[1:end] if end != -1 else rhs[1:]
                    else:
                        val = rhs.split("#", 1)[0].strip()
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
    original = SESSION_LOG.read_text(encoding="utf-8")
    content, _removed_frontmatter = normalize_session_log_frontmatter(original, today)

    # Dedupe: scan the first ~3 existing entries; if one matches date+note exactly, skip.
    # This is cheap and handles the "scheduler calls me every cron tick with same note" case.
    dedupe_marker = f"### {today} — Auto-sync"
    note_marker = f"**Note:** {note}"
    recent_block_end = content.find("\n### ", content.find("\n### ") + 1)  # end of first entry
    recent_block = content[: recent_block_end if recent_block_end > 0 else len(content)]
    if dedupe_marker in recent_block and note_marker in recent_block:
        if content != original:
            SESSION_LOG.write_text(content, encoding="utf-8")
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
        [python, str(PROJECT_ROOT / "scripts" / "integrations" / "mem0_tool.py"), "add",
         f"[state_sync] {note}", "--user", "bravo"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=30
    , creationflags=WINDOWLESS_FLAGS)
    return result.returncode == 0


def sync_domain_ping(note: str, domain: str) -> bool:
    """Fire a cross-agent domain ping (CC directive 2026-08-01) so the peer
    owning `domain` (marketing→Maven, finance→Atlas, ops→broadcast) resumes
    with awareness of what Bravo changed. Uses the sync note as the summary."""
    python = sys.executable
    result = subprocess.run(
        [python, str(PROJECT_ROOT / "scripts" / "core" / "cross_agent_ping.py"),
         "--domain", domain, "--summary", note],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60
    , creationflags=WINDOWLESS_FLAGS)
    if result.returncode != 0 and result.stderr:
        print(f"[state_sync] domain ping stderr: {result.stderr.strip()[:300]}", file=sys.stderr)
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


PULSE_STALE_DAYS = 7
_PULSE_SCRIPT = Path(__file__).resolve().parents[1] / "pulse_publish.py"


PULSE_PATH = Path(__file__).resolve().parents[2] / "data" / "pulse" / "ceo_pulse.json"


def _pulse_judgment_age_days(pulse: Path | None = None) -> float | None:
    """Days since ceo_pulse's JUDGMENT fields were written (its `updated_at`).

    Deliberately reads `updated_at`, not `mechanical_as_of`: the daily cron
    refreshes machine-knowable sections without moving `updated_at`, precisely so
    this number keeps telling the truth about strategy.
    """
    pulse = pulse or PULSE_PATH
    try:
        raw = json.loads(pulse.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return age_days(raw.get("updated_at"))


def warn_if_pulse_judgment_stale() -> None:
    age = _pulse_judgment_age_days()
    if age is None or age < PULSE_STALE_DAYS:
        return
    print(f"[state_sync] ⚠️  ceo_pulse judgment is {age:.0f}d old — Atlas pages CC "
          f"at 14d. If this session changed the plan, re-run with "
          f"--pulse-priority \"…\" --pulse-focus \"…\".", file=sys.stderr)


def write_pulse_judgment(priority: str | None, focus: str | None,
                         note: str | None) -> bool:
    """Hand the judgment fields to pulse_publish — the only blessed writer.

    Shells out rather than importing so the atomic-write, schema-validation and
    cross-agent-event behaviour stays in one place; a second in-process writer is
    how two versions of a schema start to drift.
    """
    cmd = [sys.executable, str(_PULSE_SCRIPT), "refresh"]
    if priority:
        cmd += ["--priority", priority]
    if focus:
        cmd += ["--focus", focus]
    if note:
        cmd += ["--session-note", note[:500]]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                          encoding="utf-8", errors="replace",
                          creationflags=WINDOWLESS_FLAGS)
    if proc.returncode != 0:
        print(f"[state_sync] pulse_publish failed (exit {proc.returncode}): "
              f"{(proc.stderr or proc.stdout or '').strip()[:300]}", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="State sync — single write to all memory layers")
    parser.add_argument("--note", "-n", default="", help="Observation to sync across all memory layers")
    parser.add_argument("--heartbeat", action="store_true", help="Just refresh the STATE.md heartbeat timestamp")
    parser.add_argument("--mem0", action="store_true", help="Also write to semantic memory (mem0)")
    parser.add_argument(
        "--repair-session-log-only",
        action="store_true",
        help="atomically collapse duplicate SESSION_LOG frontmatter and exit",
    )
    parser.add_argument(
        "--agent",
        default=os.environ.get("STATE_SYNC_AGENT", "bravo"),
        choices=["bravo", "atlas", "maven", "hermes", "codex", "aura", "lex"],
        help="Agent to mark live in agent_state_snapshot (default: bravo)",
    )
    parser.add_argument(
        "--mode",
        default=None,
        choices=["off", "shadow", "on"],
        help="Override EMPIRE_V6_MODE for this invocation",
    )
    parser.add_argument(
        "--domain",
        default=None,
        choices=["marketing", "finance", "ops"],
        help="Work touched a peer's domain — after the sync, ping Maven/Atlas "
             "via cross_agent_ping.py (CC directive 2026-08-01)",
    )
    # Pulse judgment fields (2026-08-03). The daily cron refreshes only what a
    # machine can know; strategy and priority are written HERE, at session end,
    # when Bravo actually has new judgment to record. Optional by design — a
    # session with nothing new to say must not rewrite the CEO's strategy, so
    # absent flags leave the pulse untouched.
    parser.add_argument("--pulse-priority", default=None,
                        help="This week's #1 priority → ceo_pulse strategy")
    parser.add_argument("--pulse-focus", default=None,
                        help="Current strategic focus → ceo_pulse strategy")
    parser.add_argument("--pulse-note", default=None,
                        help="Session note → ceo_pulse (defaults to --note when "
                             "another --pulse-* flag is given)")
    args = parser.parse_args()

    if args.repair_session_log_only:
        removed, preserved = repair_session_log_frontmatter()
        print(
            f"[state_sync] SESSION_LOG repaired: removed {removed} duplicate "
            f"frontmatter block(s); preserved {preserved} session entries"
        )
        return

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

    # Cross-agent domain ping (CC directive 2026-08-01). Optional — only fires
    # when --domain is passed; default behavior is unchanged. Best-effort:
    # cross_agent_ping.py itself fails loud (exit 1) when the write fails.
    if args.domain:
        try:
            ok = sync_domain_ping(note, args.domain)
            results["domain_ping"] = f"✅ ({args.domain})" if ok else f"⚠️ ping failed ({args.domain})"
        except Exception as e:
            results["domain_ping"] = f"❌ {e}"

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

    if args.pulse_priority or args.pulse_focus or args.pulse_note:
        try:
            ok = write_pulse_judgment(args.pulse_priority, args.pulse_focus,
                                      args.pulse_note or note)
            results["ceo_pulse"] = "✅" if ok else "⚠️ pulse write failed"
        except Exception as e:  # noqa: BLE001
            results["ceo_pulse"] = f"❌ {e}"

    summary = " | ".join(f"{k}: {v}" for k, v in results.items())
    print(f"[state_sync] {summary}")
    print(f"[state_sync] Note: {note}")

    # The nag CC should never have received from Atlas. Atlas pages CC when the
    # pulse passes 14 days; this fires at 7, on Bravo's own terminal, at the one
    # moment Bravo is already thinking about what the session changed. A warning
    # that reaches the agent who can fix it beats one that reaches the operator
    # who can only forward it.
    warn_if_pulse_judgment_stale()


if __name__ == "__main__":
    main()
