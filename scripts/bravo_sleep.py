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
- Model calls run through the local `claude` CLI on CC's Claude Code
  subscription (lib.claude_cli) — never the metered ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
_WINDOWLESS = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # windowless on Windows (V7 EPIC7A)
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
MEMORY_DIFF_DIR = PROJECT_ROOT / "state" / "memory_diff"

# V7.3.0 anti-pollution guard (OpenViking plugin lesson): never let injected
# retrieval/system context that leaked into a logged note be re-captured as if
# it were new activity — that's a self-referential memory loop.
_POLLUTION_MARKERS = ("<system-reminder", "## Relevant Memory", "<openviking", "<relevant-memories")

DEDUP_PROMPT = """You are Bravo's sleep agent running a dedup pass. For each CANDIDATE lesson
below, existing memory snippets that look similar are shown. Decide per candidate:
- "create" — genuinely new lesson (or the existing snippet covers a different point)
- "skip"   — the existing memory already captures this lesson

Return ONLY a JSON array: [{{"title": "<candidate title>", "decision": "create"|"skip", "reason": "<one line>"}}]

{blocks}"""

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
    lines = []
    for r in rows:
        note = str(r["note"] or "")
        if any(m in note for m in _POLLUTION_MARKERS):
            continue  # injected-context leakage — data, not activity
        lines.append(f"- [{r['ts']}] ({r['agent']}) {note}")
    return "\n".join(lines) if lines else "(no entries in window)"


def _recent_git_log(hours: int) -> str:
    try:
        result = subprocess.run(
            ["git", "log", f"--since={hours} hours ago", "--pretty=format:%h %s", "-50"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_WINDOWLESS,
        )
        out = result.stdout.strip()
        return out if out else "(no commits in window)"
    except (subprocess.SubprocessError, OSError):
        return "(git unavailable)"


def _call_model(prompt: str) -> str:
    # Local claude CLI on CC's subscription OAuth (lib.claude_cli), NOT the
    # metered ANTHROPIC_API_KEY. The old path used model_router.call() + the
    # API key, which now 400s ("credit balance too low") and violates the
    # CLI-only rule — the exact failure that left this nightly job dead. Haiku
    # alias: cheapest tier is correct for a nightly daemon.
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from lib.claude_cli import run_claude_cli  # type: ignore
    # Timeout is 180s, not the CLI default: this runs at 04:00 behind PYTHONW
    # with the whole nightly cron block, and a cold `claude -p` spawn measured
    # 11s idle. No prompt truncation here — the assembled prompt measured ~1KB
    # (50 session-log rows + git log), so a character cap would be a no-op that
    # falsely implies length was ever the failure mode. If this call starts
    # failing again, the reason now comes back in the claude_cli error text.
    text = run_claude_cli(prompt, model="haiku", timeout=180)
    if not text:
        raise RuntimeError("claude CLI returned no text (missing CLI / expired token / timeout)")
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
                       cwd=PROJECT_ROOT, check=True, timeout=10, creationflags=_WINDOWLESS)
        msg = f"sleep-agent: log {kind} — {title[:60]}"
        subprocess.run(["git", "commit", "-m", msg, "--no-verify"],
                       cwd=PROJECT_ROOT, check=True, timeout=15, creationflags=_WINDOWLESS)
    except subprocess.SubprocessError as e:
        print(f"[warn] git commit failed for {target.name}: {e}", file=sys.stderr)


def _near_duplicates(title: str, body: str) -> list[dict]:
    """Lexical near-dup probe against the memory index (deterministic, no embed
    cost). Returns hit dicts ({ref, snippet}) or [] on any failure — dedup is an
    enhancement, never a blocker."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from core.memory_retriever import query as _mq  # type: ignore
        hits = _mq(f"{title} {body[:200]}", limit=3, kind="memory", mode="lexical")
        return [{"ref": h.get("ref", ""), "snippet": h.get("snippet", "")[:220]} for h in hits]
    except Exception:  # noqa: BLE001
        return []


def _judge_duplicates(candidates: list[tuple[dict, list[dict]]]) -> dict[str, str]:
    """One batched model call deciding create/skip for candidates that have
    near-dup evidence (OpenViking two-level dedup pattern, candidate level —
    'merge' deliberately not adopted: this pipeline is append-only by design,
    see ADR-0011). Returns {title: decision}; on any failure, everything
    defaults to 'create' (the 7-day cooldown still backstops)."""
    if not candidates:
        return {}
    blocks = []
    for p, hits in candidates:
        ev = "\n".join(f"  - existing [{h['ref']}]: {h['snippet']}" for h in hits)
        blocks.append(f"CANDIDATE ({p['file']}): {p['title']}\n{p['body'][:400]}\nSIMILAR EXISTING:\n{ev}")
    try:
        raw = _call_model(DEDUP_PROMPT.format(blocks="\n\n".join(blocks)))
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        data = json.loads(cleaned)
        out = {}
        for d in data if isinstance(data, list) else []:
            if isinstance(d, dict) and d.get("decision") in ("create", "skip"):
                out[str(d.get("title", "")).strip()] = d["decision"]
        return out
    except Exception:  # noqa: BLE001
        return {}


def _write_memory_diff(record: dict, dry_run: bool) -> None:
    """Per-run audit artifact (OpenViking memory_diff pattern): every run writes
    a JSON record — even an empty one — so memory mutations are auditable and
    reversible. Best-effort: the sleep pass never fails because the audit did."""
    try:
        MEMORY_DIFF_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = "-dry" if dry_run else ""
        (MEMORY_DIFF_DIR / f"{stamp}{suffix}.json").write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[bravo_sleep] memory_diff write failed: {e}", file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> int:
    # Model calls go through the local claude CLI on CC's subscription (see
    # _call_model); no ANTHROPIC_API_KEY required. Bootstrap secrets anyway so
    # the state DB / git paths resolve under the PYTHONW scheduler.
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "lib"))
        from secret_loader import bootstrap  # type: ignore
        bootstrap()
    except Exception as e:
        print(f"[bravo_sleep] secret_loader bootstrap failed: {e}", file=sys.stderr)

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
    audit: dict = {"run_ts": datetime.now(timezone.utc).isoformat(),
                   "window_hours": args.window_hours, "dry_run": args.dry_run,
                   "proposals": []}
    if not proposals:
        print(f"[bravo_sleep] no proposals (model returned: {raw[:120]!r})")
        _write_memory_diff(audit, args.dry_run)
        LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RUN_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        return 0

    # V7.3.0 dedup state machine: cooldown (cheap) → retrieval near-dup probe →
    # batched judge decision (create/skip) for candidates with evidence.
    cooldowns = _load_cooldowns()
    staged: list[tuple[dict, list[dict], str]] = []  # (proposal, dup_evidence, state)
    needs_judgment: list[tuple[dict, list[dict]]] = []
    for p in proposals:
        if _on_cooldown(p["file"], p["title"], cooldowns):
            staged.append((p, [], "skipped-cooldown"))
            continue
        dups = _near_duplicates(p["title"], p["body"])
        if dups:
            needs_judgment.append((p, dups))
            staged.append((p, dups, "pending-judgment"))
        else:
            staged.append((p, [], "create"))
    verdicts = _judge_duplicates(needs_judgment)

    written = 0
    skipped = 0
    for p, dups, state in staged:
        if state == "pending-judgment":
            state = "skipped-duplicate" if verdicts.get(p["title"]) == "skip" else "create"
        entry = {"file": p["file"], "title": p["title"], "decision": state,
                 "dup_evidence": dups}
        if state == "create":
            target = MEMORY_DIR / f"{p['file']}.md"
            if not target.exists():
                entry["decision"] = "skipped-missing-target"
                print(f"[warn] target {target} missing — skipping", file=sys.stderr)
            else:
                _append_entry(target, p["title"], p["body"], args.dry_run)
                _git_commit(target, p["file"].lower(), p["title"], args.dry_run)
                cooldowns[_topic_hash(p["file"], p["title"])] = datetime.now(timezone.utc).isoformat()
                entry["body"] = p["body"]
                entry["decision"] = "created"
                written += 1
        if entry["decision"].startswith("skipped"):
            skipped += 1
        audit["proposals"].append(entry)

    audit["written"] = written
    audit["skipped"] = skipped
    _write_memory_diff(audit, args.dry_run)

    if not args.dry_run:
        _save_cooldowns(cooldowns)
        LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RUN_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    print(f"[bravo_sleep] wrote {written}, skipped {skipped} "
          f"(cooldown/duplicate — see state/memory_diff/), dry_run={args.dry_run}")
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
