"""Publish memory/ACTIVE_TASKS.md tasks to the `oasis_quests` table (Turso via supabase-compat shim).

Used by OASIS Town's Quest Log panel — the game polls /api/quests every minute
and visualizes the live state of CC's actual TODO list.

Parser is deliberately tolerant: `ACTIVE_TASKS.md` is a markdown file CC + agents
hand-edit, with mixed conventions (checkbox lists, h2 buckets, free prose). We
extract things that look like tasks (a line starting with `- [ ]` or `- [x]`),
group them by the nearest h2 above, and upsert.

CLI:
  python scripts/quest_publisher.py publish        # one-shot publish
  python scripts/quest_publisher.py loop --interval 60   # daemon mode
  python scripts/quest_publisher.py dry-run        # parse + print, no write

Idempotency: each quest gets a stable `id` = sha1(bucket + title)[:16]. Re-running
upserts the same rows — no duplicates. Tasks removed from the markdown are
marked `status='archived'` on the next pass (not deleted, so we can show "recently
completed" in the game UI).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

ACTIVE_TASKS = PROJECT_ROOT / "memory" / "ACTIVE_TASKS.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _quest_id(bucket: str, title: str) -> str:
    return hashlib.sha1(f"{bucket}::{title}".encode("utf-8")).hexdigest()[:16]


CHECKBOX_RE = re.compile(r"^\s*-\s*\[(\s|x|X)\]\s+(.+?)\s*$")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")
OWNER_RE = re.compile(r"@(\w+)")


def parse_tasks(markdown: str) -> list[dict]:
    """Walk the markdown, group checkbox lines by the nearest preceding h2."""
    bucket = "(no bucket)"
    out: list[dict] = []
    for lineno, raw in enumerate(markdown.splitlines(), start=1):
        line = raw.rstrip()
        m_h = H2_RE.match(line)
        if m_h:
            bucket = m_h.group(1).strip()[:80]
            continue
        m_c = CHECKBOX_RE.match(line)
        if not m_c:
            continue
        checked = m_c.group(1).lower() == "x"
        title = m_c.group(2)[:300]
        # Pull @owner mentions if present (e.g. "- [ ] @bravo Ship Quest Log")
        owner_match = OWNER_RE.search(title)
        owner = owner_match.group(1).lower() if owner_match else None
        out.append({
            "id":          _quest_id(bucket, title),
            "bucket":      bucket,
            "title":       title,
            "owner":       owner,
            "status":      "completed" if checked else "open",
            "source_file": "memory/ACTIVE_TASKS.md",
            "source_line": lineno,
        })
    return out


def _supabase_client():
    try:
        from lib.secret_loader import load_env
    except Exception as e:
        print(f"[quest_publisher] cannot load env: {e}", file=sys.stderr)
        return None
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key").strip()
    if not url or not key:
        print("[quest_publisher] missing BRAVO_SUPABASE_URL/SERVICE_ROLE_KEY",
              file=sys.stderr)
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"[quest_publisher] db client failed: {e}", file=sys.stderr)
        return None


def publish_once(dry_run: bool = False) -> dict:
    if not ACTIVE_TASKS.exists():
        return {"error": f"missing {ACTIVE_TASKS}"}
    md = ACTIVE_TASKS.read_text(encoding="utf-8", errors="ignore")
    quests = parse_tasks(md)

    if dry_run:
        print(f"parsed {len(quests)} quests from {ACTIVE_TASKS}")
        for q in quests[:20]:
            owner = f"@{q['owner']}" if q['owner'] else "-"
            check = "✓" if q['status'] == "completed" else "○"
            print(f"  {check} [{q['bucket'][:25]:25s}] {owner:8s} {q['title'][:80]}")
        if len(quests) > 20:
            print(f"  ... and {len(quests) - 20} more")
        return {"parsed": len(quests), "dry_run": True}

    client = _supabase_client()
    if client is None:
        return {"error": "no db client (env missing or supabase lib not installed)"}

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    upserts: list[dict] = []
    for q in quests:
        row = dict(q)
        row["updated_at"] = now_iso
        if q["status"] == "completed":
            row["completed_at"] = now_iso
        upserts.append(row)

    if not upserts:
        return {"parsed": 0, "upserted": 0}

    try:
        client.table("oasis_quests").upsert(upserts, on_conflict="id").execute()
    except Exception as e:
        return {"error": f"upsert failed: {e}", "parsed": len(quests)}

    # Mark anything that's no longer in the markdown as 'archived'. We do this
    # by getting current open IDs and archiving the diff. Tolerant: failure
    # here doesn't lose the upsert above.
    try:
        current_ids = {q["id"] for q in quests}
        existing = client.table("oasis_quests").select("id, status").eq("status", "open").execute()
        stale = [r["id"] for r in (existing.data or []) if r["id"] not in current_ids]
        if stale:
            client.table("oasis_quests").update(
                {"status": "archived", "updated_at": now_iso}
            ).in_("id", stale).execute()
    except Exception as e:
        print(f"[quest_publisher] archive sweep skipped: {e}", file=sys.stderr)

    return {"parsed": len(quests), "upserted": len(upserts)}


def loop(interval: int) -> int:
    print(f"[quest_publisher] polling every {interval}s — Ctrl-C to stop", flush=True)
    total = 0
    try:
        while True:
            try:
                r = publish_once()
                if "error" in r:
                    print(f"[error] {r['error']}", flush=True)
                else:
                    total += r.get("upserted", 0)
                    print(f"  parsed={r['parsed']} upserted={r['upserted']} "
                          f"(running total {total})", flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[tick error] {e}", flush=True)
            time.sleep(max(5, interval))
    except KeyboardInterrupt:
        print(f"\n[quest_publisher] stopped. {total} total upserts.")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OASIS Town quest publisher")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("publish", help="One-shot publish + exit")
    sub.add_parser("dry-run", help="Parse + print, no DB writes")
    lp = sub.add_parser("loop", help="Poll continuously")
    lp.add_argument("--interval", type=int, default=60)
    args = p.parse_args(argv)

    if args.command == "publish":
        import json
        result = publish_once()
        print(json.dumps(result, indent=2))
        return 0 if "error" not in result else 1
    if args.command == "dry-run":
        publish_once(dry_run=True)
        return 0
    if args.command == "loop":
        return loop(args.interval)
    return 1


if __name__ == "__main__":
    sys.exit(main())
