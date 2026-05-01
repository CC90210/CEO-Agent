"""
Memory Consolidation — 3-layer memory pipeline.

Moves working-memory items from memory/WORKING.md into the episodic and semantic
layers in Supabase, then resets WORKING.md to its blank template.

Three layers:
  Working    memory/WORKING.md                — ephemeral, session-scoped
  Episodic   memories_episodic (Supabase)     — timestamped events with recency decay
  Semantic   memories_semantic (Supabase)     — durable facts, procedures, knowledge

Consolidation logic (per item):
  importance > 0.7 + type='event'              -> memories_episodic with embedding
  importance > 0.7 + type in (fact|procedure)  -> memories_semantic with embedding
  importance <= 0.7 OR type='noise'            -> drop (log count only)

An archive of the pre-consolidation WORKING.md is written to
memory/archive/working_<timestamp>.md before clearing.

SUBCOMMANDS
-----------
    run --dry-run   Show what would move, don't write anything
    run             Full consolidation: parse -> classify -> upsert -> clear
    decay           Apply recency decay to memories_episodic.confidence
    sync-mem0       Push consolidated memories to mem0 via mem0_tool.py
    status          Print counts: working items / episodic rows / semantic rows

USAGE
-----
    python scripts/memory_consolidation.py status --json
    python scripts/memory_consolidation.py run --dry-run
    python scripts/memory_consolidation.py run
    python scripts/memory_consolidation.py decay --days 30 --rate 0.95
    python scripts/memory_consolidation.py sync-mem0
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
WORKING_MD = MEMORY_DIR / "WORKING.md"
ARCHIVE_DIR = MEMORY_DIR / "archive"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

WORKING_TEMPLATE = """\
---
tags: [working-memory, ephemeral]
---

# Working Memory

> Ephemeral scratch pad for the current session. Cleared by `memory_consolidation.py run`
> after items are promoted to episodic/semantic memory. Archive written to
> `memory/archive/working_<timestamp>.md` before each clear.

## Current Task

<!-- populated during session, cleared at consolidation -->

## Recent Tool Calls

<!-- populated during session, cleared at consolidation -->

## Hypotheses Active

<!-- populated during session, cleared at consolidation -->

## Open Questions

<!-- populated during session, cleared at consolidation -->

## Pending Decisions

<!-- populated during session, cleared at consolidation -->
"""

SECTION_HEADERS = [
    "Current Task",
    "Recent Tool Calls",
    "Hypotheses Active",
    "Open Questions",
    "Pending Decisions",
]

EMPTY_MARKER = re.compile(r"<!--\s*populated during session.*?-->", re.DOTALL)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- Env + DB ----------------------------------------------------------------

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def get_supabase(env: Optional[dict[str, str]] = None):
    e = env if env is not None else load_env()
    url = e.get("BRAVO_SUPABASE_URL") or e.get("SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (
        e.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        or e.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    )
    if not url or not key:
        raise RuntimeError("Supabase credentials missing — check .env.agents")
    from supabase import create_client  # type: ignore
    return create_client(url, key)


def get_anthropic_key(env: Optional[dict[str, str]] = None) -> str:
    e = env if env is not None else load_env()
    key = e.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in .env.agents")
    return key


# ---- Embedding (re-use memory_ingest pattern) --------------------------------

def _embed(texts: list[str], env: dict[str, str]) -> list[list[float]]:
    """Embed a list of strings. Delegates to memory_ingest.embed_batch."""
    _ingest_dir = str(SCRIPTS_DIR)
    if _ingest_dir not in sys.path:
        sys.path.insert(0, _ingest_dir)
    try:
        from memory_ingest import embed_batch  # type: ignore
        return embed_batch(texts, env=env)
    except ImportError:
        # Fallback: deterministic hash stubs so the module still works without
        # OpenAI/Ollama — not usable for production retrieval.
        import hashlib, struct
        dim = 1536
        result = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            floats = []
            for i in range(dim):
                b = h[(i * 4) % (len(h) - 3): (i * 4) % (len(h) - 3) + 4]
                (v,) = struct.unpack("f", b)
                floats.append(v)
            norm = sum(x * x for x in floats) ** 0.5 or 1.0
            result.append([x / norm for x in floats])
        return result


# ---- WORKING.md parser -------------------------------------------------------

def _is_empty_item(text: str) -> bool:
    """True if the item is only a comment placeholder or whitespace."""
    stripped = text.strip()
    if not stripped:
        return True
    if EMPTY_MARKER.fullmatch(stripped):
        return True
    return False


def parse_working_md(path: Path = WORKING_MD) -> list[dict[str, Any]]:
    """Parse memory/WORKING.md sections into a list of items.

    Each item: {"section": str, "content": str, "raw": str}
    Items that are only comment placeholders are excluded.
    """
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")

    # Strip frontmatter.
    fm_match = re.match(r"^\s*---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    body = text[fm_match.end():] if fm_match else text

    items: list[dict[str, Any]] = []
    current_section: Optional[str] = None
    current_lines: list[str] = []

    def _flush(section: Optional[str], lines: list[str]) -> None:
        if not section:
            return
        content = "\n".join(lines).strip()
        if not _is_empty_item(content):
            items.append({"section": section, "content": content, "raw": content})

    for line in body.splitlines():
        # H2 headings mark section boundaries.
        h2 = re.match(r"^##\s+(.+)$", line)
        if h2:
            _flush(current_section, current_lines)
            current_section = h2.group(1).strip()
            current_lines = []
            continue
        # Skip the top-level H1 (document title).
        if re.match(r"^#\s+", line):
            _flush(current_section, current_lines)
            current_section = None
            current_lines = []
            continue
        if current_section:
            current_lines.append(line)

    _flush(current_section, current_lines)
    return items


# ---- Claude Haiku classifier -------------------------------------------------

_CLASSIFY_SYSTEM = """\
You are a memory classification engine for an autonomous AI agent.
Given a piece of working memory content, return ONLY a JSON object with:
{
  "importance": <float 0.0-1.0>,
  "type": "event" | "fact" | "procedure" | "noise",
  "summary": "<one sentence distilling the key information>"
}

Definitions:
- event: something that happened (a task was completed, an email was sent, CC made a decision)
- fact: a durable piece of knowledge (a price, a client's name, a tool's behavior)
- procedure: a repeatable set of steps (how to run a workflow, how to handle a scenario)
- noise: low-value chatter, internal status that won't matter next session

importance >= 0.7 means "this should be remembered across sessions".
Return ONLY the JSON. No markdown fences, no explanation.
"""


def classify_item(
    content: str,
    section: str,
    api_key: str,
) -> dict[str, Any]:
    """Call Claude Haiku to score importance and classify one memory item."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise RuntimeError("anthropic SDK not installed — pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=_CLASSIFY_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Section: {section}\n\nContent:\n{content[:1000]}",
            }
        ],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat as unknown importance.
        return {"importance": 0.5, "type": "noise", "summary": content[:100]}

    return {
        "importance": float(result.get("importance") or 0.5),
        "type": str(result.get("type") or "noise"),
        "summary": str(result.get("summary") or content[:100]),
    }


# ---- Upsert helpers ----------------------------------------------------------

def _upsert_episodic(db: Any, item: dict[str, Any], embedding: list[float]) -> None:
    row = {
        "content": item["summary"],
        "raw_content": item["content"][:2000],
        "section": item["section"],
        "importance": item["importance"],
        "type": "event",
        "confidence": item["importance"],
        "embedding": embedding,
        "source_file": "memory/WORKING.md",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table("memories_episodic").insert(row).execute()


def _upsert_semantic(db: Any, item: dict[str, Any], embedding: list[float]) -> None:
    row = {
        "content": item["summary"],
        "raw_content": item["content"][:2000],
        "section": item["section"],
        "importance": item["importance"],
        "type": item["type"],
        "confidence": item["importance"],
        "embedding": embedding,
        "source_file": "memory/WORKING.md",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table("memories_semantic").insert(row).execute()


# ---- Archive -----------------------------------------------------------------

def _archive_working(content: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = ARCHIVE_DIR / f"working_{ts}.md"
    dest.write_text(content, encoding="utf-8")
    return dest


def _reset_working() -> None:
    WORKING_MD.write_text(WORKING_TEMPLATE, encoding="utf-8")


# ---- STATUS ------------------------------------------------------------------

def get_status(env: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Count working items, episodic rows, semantic rows."""
    e = env or load_env()
    items = parse_working_md()
    working_count = len(items)

    episodic_count = 0
    semantic_count = 0
    db_error: Optional[str] = None
    try:
        db = get_supabase(e)
        ep = db.table("memories_episodic").select("id", count="exact").execute()
        episodic_count = ep.count or len(ep.data or [])
        sm = db.table("memories_semantic").select("id", count="exact").execute()
        semantic_count = sm.count or len(sm.data or [])
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)

    return {
        "working_items": working_count,
        "episodic_rows": episodic_count,
        "semantic_rows": semantic_count,
        "working_file": str(WORKING_MD),
        "db_error": db_error,
    }


def cmd_status(args: argparse.Namespace) -> int:
    env = load_env()
    try:
        status = get_status(env)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(status, indent=2, default=str))
        return 0

    print("Memory layer status:")
    print(f"  Working items (WORKING.md): {status['working_items']}")
    print(f"  Episodic rows (Supabase):   {status['episodic_rows']}")
    print(f"  Semantic rows (Supabase):   {status['semantic_rows']}")
    if status.get("db_error"):
        print(f"  DB error: {status['db_error']}", file=sys.stderr)
    return 0


# ---- RUN (consolidate) -------------------------------------------------------

def consolidate(
    dry_run: bool = False,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Full consolidation pipeline.

    1. Parse WORKING.md sections into items.
    2. For each item, call Claude Haiku to score importance + classify.
    3. importance > 0.7 + 'event' -> memories_episodic with embedding.
    4. importance > 0.7 + ('fact' | 'procedure') -> memories_semantic with embedding.
    5. importance <= 0.7 -> drop.
    6. Archive WORKING.md content.
    7. Reset WORKING.md to template.
    """
    e = env or load_env()
    items = parse_working_md()

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "working_items_found": len(items),
        "classified": [],
        "promoted_episodic": 0,
        "promoted_semantic": 0,
        "dropped": 0,
        "archive_path": None,
    }

    if not items:
        result["message"] = "WORKING.md has no content to consolidate."
        return result

    api_key = get_anthropic_key(e)

    classified: list[dict[str, Any]] = []
    for item in items:
        try:
            classification = classify_item(item["content"], item["section"], api_key)
        except Exception as exc:  # noqa: BLE001
            classification = {"importance": 0.4, "type": "noise", "summary": item["content"][:80]}
            classification["classify_error"] = str(exc)
        item.update(classification)
        classified.append(item)

    result["classified"] = [
        {
            "section": c["section"],
            "type": c.get("type"),
            "importance": c.get("importance"),
            "summary": c.get("summary", "")[:120],
            "action": (
                "episodic" if c.get("importance", 0) > 0.7 and c.get("type") == "event"
                else "semantic" if c.get("importance", 0) > 0.7 and c.get("type") in ("fact", "procedure")
                else "drop"
            ),
        }
        for c in classified
    ]

    if dry_run:
        return result

    # Embed and upsert.
    to_store = [c for c in classified if c.get("importance", 0) > 0.7 and c.get("type") != "noise"]
    dropped_count = len(classified) - len(to_store)
    result["dropped"] = dropped_count

    if to_store:
        texts = [c.get("summary") or c["content"][:500] for c in to_store]
        try:
            embeddings = _embed(texts, e)
        except Exception as exc:  # noqa: BLE001
            result["embed_error"] = str(exc)
            embeddings = [[0.0] * 1536] * len(texts)

        try:
            db = get_supabase(e)
            for item, embedding in zip(to_store, embeddings):
                mem_type = item.get("type")
                if mem_type == "event":
                    _upsert_episodic(db, item, embedding)
                    result["promoted_episodic"] += 1
                elif mem_type in ("fact", "procedure"):
                    _upsert_semantic(db, item, embedding)
                    result["promoted_semantic"] += 1
                else:
                    result["dropped"] += 1
        except Exception as exc:  # noqa: BLE001
            result["db_error"] = str(exc)

    # Archive and reset.
    original_content = WORKING_MD.read_text(encoding="utf-8") if WORKING_MD.exists() else ""
    archive_path = _archive_working(original_content)
    result["archive_path"] = str(archive_path)
    _reset_working()

    return result


def cmd_run(args: argparse.Namespace) -> int:
    env = load_env()
    try:
        result = consolidate(dry_run=args.dry_run, env=env)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: consolidate failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.dry_run:
        print(f"Dry run — {result['working_items_found']} working items found:")
        for c in result.get("classified") or []:
            print(f"  [{c['action']:8}] {c['section']}: {c['summary'][:70]}")
    else:
        print(f"Consolidated {result['working_items_found']} items:")
        print(f"  Episodic:  {result['promoted_episodic']}")
        print(f"  Semantic:  {result['promoted_semantic']}")
        print(f"  Dropped:   {result['dropped']}")
        if result.get("archive_path"):
            print(f"  Archived:  {result['archive_path']}")
        if result.get("db_error"):
            print(f"  DB error:  {result['db_error']}", file=sys.stderr)
    return 0


# ---- DECAY -------------------------------------------------------------------

def apply_decay(
    days: int = 30,
    rate: float = 0.95,
    env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Apply recency decay to memories_episodic.confidence.

    Rows older than `days` get their confidence multiplied by `rate`.
    Rows with confidence < 0.05 after decay are eligible for archival
    (not deleted here — deletion is a separate manual step).
    """
    e = env or load_env()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    db = get_supabase(e)
    rows = (
        db.table("memories_episodic")
        .select("id,confidence,created_at")
        .lt("created_at", cutoff)
        .limit(500)
        .execute()
        .data
    ) or []

    updated = 0
    low_confidence: list[str] = []
    for row in rows:
        new_conf = round(float(row.get("confidence") or 1.0) * rate, 4)
        db.table("memories_episodic").update({"confidence": new_conf}).eq("id", row["id"]).execute()
        updated += 1
        if new_conf < 0.05:
            low_confidence.append(row["id"])

    return {
        "rows_decayed": updated,
        "decay_rate": rate,
        "cutoff_days": days,
        "low_confidence_ids": low_confidence,
        "low_confidence_count": len(low_confidence),
    }


def cmd_decay(args: argparse.Namespace) -> int:
    env = load_env()
    try:
        result = apply_decay(days=args.days, rate=args.rate, env=env)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: decay failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print(f"Decay applied: {result['rows_decayed']} rows")
    print(f"  Rate: {result['decay_rate']} | Cutoff: {result['cutoff_days']}d")
    if result["low_confidence_count"]:
        print(f"  {result['low_confidence_count']} rows now below 0.05 confidence (eligible for archival)")
    return 0


# ---- SYNC-MEM0 ---------------------------------------------------------------

def cmd_sync_mem0(args: argparse.Namespace) -> int:
    """Push recently consolidated memories to mem0 via mem0_tool.py."""
    env = load_env()
    mem0_script = SCRIPTS_DIR / "mem0_tool.py"
    if not mem0_script.exists():
        print(f"ERROR: mem0_tool.py not found at {mem0_script}", file=sys.stderr)
        return 1

    # Pull recent semantic memories (last 24h) to sync.
    try:
        db = get_supabase(env)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        rows = (
            db.table("memories_semantic")
            .select("content,type,section")
            .gte("created_at", cutoff)
            .limit(50)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot read memories_semantic: {exc}", file=sys.stderr)
        return 1

    synced = 0
    errors: list[str] = []
    for row in rows:
        content = row.get("content") or ""
        if not content.strip():
            continue
        result = subprocess.run(
            [sys.executable, str(mem0_script), "add", "--text", content, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            synced += 1
        else:
            errors.append(result.stderr.strip()[:100])

    out: dict[str, Any] = {
        "rows_to_sync": len(rows),
        "synced": synced,
        "errors": errors[:5],
    }
    if args.output_json:
        print(json.dumps(out, indent=2, default=str))
        return 0

    print(f"mem0 sync: {synced}/{len(rows)} memories pushed")
    if errors:
        print(f"  {len(errors)} errors (first: {errors[0]})")
    return 0 if not errors else 1


# ---- CLI entry ---------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        prog="memory_consolidation.py",
        description="3-layer memory consolidator: WORKING.md -> episodic/semantic Supabase.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pr = sub.add_parser("run", help="Consolidate WORKING.md into Supabase memory layers")
    pr.add_argument("--dry-run", action="store_true", help="Show what would move, don't write")
    pr.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    pd = sub.add_parser("decay", help="Apply recency decay to memories_episodic.confidence")
    pd.add_argument("--days", type=int, default=30, help="Decay rows older than N days")
    pd.add_argument("--rate", type=float, default=0.95, help="Multiply confidence by this rate")
    pd.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    pm = sub.add_parser("sync-mem0", help="Push consolidated memories to mem0")
    pm.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    ps = sub.add_parser("status", help="Show item counts across all memory layers")
    ps.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    pdry = sub.add_parser("dry-run", help="Alias for `run --dry-run` — simulate consolidation")
    pdry.add_argument("--json", dest="output_json", action="store_true", default=argparse.SUPPRESS)

    args = p.parse_args()
    if not getattr(args, "output_json", False):
        args.output_json = p.parse_known_args()[0].output_json

    if args.command == "dry-run":
        args.command = "run"
        args.dry_run = True

    dispatch = {
        "run": cmd_run,
        "decay": cmd_decay,
        "sync-mem0": cmd_sync_mem0,
        "status": cmd_status,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        p.print_help()
        sys.exit(1)
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
