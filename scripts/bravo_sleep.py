#!/usr/bin/env python3
"""
bravo_sleep — Nightly memory consolidation by an LLM judge.

What this fixes
---------------
`auto_dream.py` runs deterministic budget-capping at session end. If a session
dies abruptly (process kill, IDE crash, network blip), nothing gets written —
and lessons learned that day evaporate. CC's iron law ("never teach the same
lesson twice") gets quietly violated.

Sleep agent runs nightly on a cron, independent of any session. It reads the
last 24h of activity (session_log + git diffs), asks Haiku what should be
remembered as a new MISTAKE / PATTERN / DECISION, validates the response, and
appends structured entries to the right files with a git commit per entry.

Usage
-----
    python scripts/bravo_sleep.py run                  # full pass, write + commit
    python scripts/bravo_sleep.py run --dry-run        # show proposals, no writes
    python scripts/bravo_sleep.py run --window-hours 48 # widen the input window
    python scripts/bravo_sleep.py status               # print last run time

Design notes
------------
- Uses Claude Haiku (cheapest tier) — this is a nightly daemon, not a hot path
- Writes ONLY append-only entries — never edits existing content
- Each entry gets its own git commit so it's auditable + reversible
- A 7-day cooldown per (file, topic-hash) prevents the same lesson getting
  re-logged every night when no genuinely new activity has happened
- Refuses to run if `ANTHROPIC_API_KEY` is missing (fail closed)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DB = PROJECT_ROOT / "state" / "empire_state.db"
MEMORY_DIR = PROJECT_ROOT / "memory"
COOLDOWN_PATH = PROJECT_ROOT / "state" / "sleep_agent_cooldown.json"
LAST_RUN_PATH = PROJECT_ROOT / "state" / "sleep_agent_last_run.txt"

VALID_TARGETS = {"MISTAKES", "PATTERNS", "DECISIONS"}
COOLDOWN_DAYS = 7

PROMPT_TEMPLATE = """You are Bravo's sleep agent. You run nightly to consolidate what was learned.

Recent activity (last {hours}h):

## Session log entries
{session_log}

## Git commits
{git_log}

Your job: identify NEW lessons that should be persisted. Output ONLY a JSON
array of entries. Each entry has:
- "file": one of "MISTAKES" | "PATTERNS" | "DECISIONS"
- "title": short title (≤ 60 chars)
- "body": markdown body. For MISTAKES include **Root cause:** + **Prevention:**.
  For PATTERNS include **Why:** + **How to apply:** + the [P] tag.
  For DECISIONS include the rationale + alternatives considered.

Rules:
- Return [] if nothing genuinely new happened (drift, routine work, cleanups).
- Do NOT log generic observations like "should be careful" — only concrete,
  actionable lessons tied to specific evidence in the activity above.
- Maximum 5 entries per run. Pick the highest-signal items only.
- Do NOT repeat anything already in the existing memory files.

Return ONLY the JSON array, no preamble, no markdown fences."""


def _load_cooldowns() -> dict:
    if COOLDOWN_PATH.exists():
        try:
            return json.loads(COOLDOWN_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_cooldowns(c: dict) -> None:
    COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOLDOWN_PATH.write_text(json.dumps(c, indent=2), encoding="utf-8")


def _topic_hash(file: str, title: str) -> str:
    norm = re.sub(r"\s+", " ", f"{file}|{title}".lower()).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def _on_cooldown(file: str, title: str, cooldowns: dict) -> bool:
    h = _topic_hash(file, title)
    last = cooldowns.get(h)
    if not last:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
    try:
        return datetime.fromisoformat(last) > cutoff
    except ValueError:
        return False


def _recent_session_log(hours: int) -> str:
    if not STATE_DB.exists():
        return "(state DB not initialized)"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(STATE_DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT ts, agent, note FROM session_log WHERE ts >= ? ORDER BY ts DESC LIMIT 50",
            (cutoff,),
        ).fetchall()
    if not rows:
        return "(no entries in window)"
    return "\n".join(f"- [{r['ts']}] ({r['agent']}) {r['note']}" for r in rows)


def _recent_git_log(hours: int) -> str:
    try:
        result = subprocess.run(
            ["git", "log", f"--since={hours} hours ago", "--pretty=format:%h %s", "-50"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = result.stdout.strip()
        return out if out else "(no commits in window)"
    except (subprocess.SubprocessError, OSError):
        return "(git unavailable)"


def _call_model(prompt: str) -> str:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import model_router  # type: ignore
    except ImportError:
        raise RuntimeError("model_router not importable — fix that first")
    # Pin Haiku explicitly — nightly daemon, cheapest tier is correct
    result = model_router.call(
        messages=[{"role": "user", "content": prompt}],
        agent="bravo",
        model="claude-haiku-4-5",
        max_tokens=2000,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"model_router returned non-dict: {result!r}")
    if result.get("error"):
        raise RuntimeError(f"model call failed: {result.get('error')}")
    text = result.get("text", "").strip()
    if not text:
        raise RuntimeError(f"model returned empty text; full payload: {result!r}")
    return text


def _parse_proposals(raw: str) -> list[dict]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        f = entry.get("file", "").strip().upper()
        title = entry.get("title", "").strip()
        body = entry.get("body", "").strip()
        if f in VALID_TARGETS and title and body:
            out.append({"file": f, "title": title, "body": body})
    return out[:5]


def _append_entry(target: Path, title: str, body: str, dry_run: bool) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = f"\n### {today} — {title}\n\n{body}\n"
    if dry_run:
        print(f"[dry-run] would append to {target.name}:\n{block}")
        return
    with target.open("a", encoding="utf-8") as f:
        f.write(block)
    # Bump last_updated in frontmatter (best-effort, no-op if not present)
    content = target.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(last_updated:\s*)\d{4}-\d{2}-\d{2}",
        rf"\g<1>{today}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if new_content != content:
        target.write_text(new_content, encoding="utf-8")


def _git_commit(target: Path, kind: str, title: str, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        subprocess.run(["git", "add", str(target.relative_to(PROJECT_ROOT))],
                       cwd=PROJECT_ROOT, check=True, timeout=10)
        msg = f"sleep-agent: log {kind} — {title[:60]}"
        subprocess.run(["git", "commit", "-m", msg, "--no-verify"],
                       cwd=PROJECT_ROOT, check=True, timeout=15)
    except subprocess.SubprocessError as e:
        print(f"[warn] git commit failed for {target.name}: {e}", file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "lib"))
            from secret_loader import bootstrap  # type: ignore
            bootstrap()
        except Exception as e:
            print(f"[bravo_sleep] secret_loader bootstrap failed: {e}", file=sys.stderr)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[bravo_sleep] no ANTHROPIC_API_KEY — refusing to run", file=sys.stderr)
        return 2

    prompt = PROMPT_TEMPLATE.format(
        hours=args.window_hours,
        session_log=_recent_session_log(args.window_hours),
        git_log=_recent_git_log(args.window_hours),
    )
    try:
        raw = _call_model(prompt)
    except RuntimeError as e:
        print(f"[bravo_sleep] model call failed: {e}", file=sys.stderr)
        return 3
    proposals = _parse_proposals(raw)
    if not proposals:
        print(f"[bravo_sleep] no proposals (model returned: {raw[:120]!r})")
        LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RUN_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        return 0

    cooldowns = _load_cooldowns()
    written = 0
    skipped = 0
    for p in proposals:
        if _on_cooldown(p["file"], p["title"], cooldowns):
            skipped += 1
            continue
        target = MEMORY_DIR / f"{p['file']}.md"
        if not target.exists():
            print(f"[warn] target {target} missing — skipping", file=sys.stderr)
            continue
        _append_entry(target, p["title"], p["body"], args.dry_run)
        _git_commit(target, p["file"].lower(), p["title"], args.dry_run)
        cooldowns[_topic_hash(p["file"], p["title"])] = datetime.now(timezone.utc).isoformat()
        written += 1

    if not args.dry_run:
        _save_cooldowns(cooldowns)
        LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RUN_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    print(f"[bravo_sleep] wrote {written}, skipped {skipped} (cooldown), dry_run={args.dry_run}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    last = LAST_RUN_PATH.read_text(encoding="utf-8").strip() if LAST_RUN_PATH.exists() else "never"
    cooldowns = _load_cooldowns()
    print(json.dumps({"last_run": last, "active_cooldowns": len(cooldowns)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bravo sleep agent — nightly memory consolidation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run one consolidation pass")
    p_run.add_argument("--window-hours", type=int, default=24)
    p_run.add_argument("--dry-run", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="Show last run + cooldown count")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
