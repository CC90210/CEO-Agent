"""V6.0 FTS5 retrieval over memory/, skills/, brain/.

Replaces whole-file context loads with snippet-level retrieval. The agent
queries `memory_retriever.py query "..."` and gets ranked chunks with
file+line refs instead of pulling 100K tokens of markdown into context.

CLI:
  python scripts/memory_retriever.py build              # full reindex
  python scripts/memory_retriever.py update             # incremental
  python scripts/memory_retriever.py query "stripe refund"
  python scripts/memory_retriever.py query --kind skill "schedule social post"
  python scripts/memory_retriever.py query --json "..." --limit 8
  python scripts/memory_retriever.py status             # index health
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / "state"
INDEX_DB = STATE_DIR / "memory_index.db"
MIGRATIONS_DIR = STATE_DIR / "migrations"

# Indexing scope — relative paths from PROJECT_ROOT.
SCOPES: dict[str, list[str]] = {
    "memory": ["memory/*.md"],
    "skill":  ["skills/*/SKILL.md"],
    "brain":  ["brain/*.md"],
    "entry":  ["CLAUDE.md", "AGENTS.md", "GEMINI.md", "ANTIGRAVITY.md", "OPENCODE.md"],
}

# Files to skip — DB-derived, ephemeral, or templates.
EXCLUDE_NAMES = {
    "STATE.md",
    "OPERATIONAL_STATE.md",
    "SESSION_LOG.md",
    "MEMORY_INDEX.md",
    "SESSION_LOG.template.md",
    "CAPABILITY_GRAPH.json",
}

# Per-query output cap to keep agent context windows from being flooded.
MAX_RESULT_TOKENS = 1500
APPROX_CHARS_PER_TOKEN = 4

CHUNK_TARGET_CHARS = 1600  # ~400 tokens
CHUNK_HARD_MAX = 2400      # break beyond this regardless

H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
TAGS_RE = re.compile(r"^tags:\s*\[?(.+?)\]?\s*$", re.MULTILINE)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def connect(read_only: bool = False) -> sqlite3.Connection:
    _ensure_state_dir()
    if read_only and INDEX_DB.exists():
        uri = f"file:{INDEX_DB.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
    else:
        conn = sqlite3.connect(str(INDEX_DB), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _apply_migrations(conn)
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    sql_path = MIGRATIONS_DIR / "002_memory_index.sql"
    if sql_path.exists():
        conn.executescript(sql_path.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_tags(text: str) -> str:
    fm = FRONTMATTER_RE.match(text)
    if not fm:
        return ""
    inner = fm.group(1)
    m = TAGS_RE.search(inner)
    if not m:
        return ""
    raw = m.group(1)
    parts = [t.strip().strip('"').strip("'").strip("[]") for t in raw.split(",")]
    return " ".join(p for p in parts if p)


def _strip_frontmatter(text: str) -> tuple[str, int]:
    fm = FRONTMATTER_RE.match(text)
    if not fm:
        return text, 0
    body = text[fm.end():]
    line_offset = text[: fm.end()].count("\n")
    return body, line_offset


def _chunk_markdown(text: str, line_offset: int) -> Iterator[tuple[str, str, int, int]]:
    """Yield (heading_path, body, line_start, line_end) tuples."""
    sections: list[tuple[str, int]] = []
    for match in H2_RE.finditer(text):
        sections.append((match.group(1), match.start()))
    if not sections:
        sections = [("", 0)]

    for i, (heading, start_pos) in enumerate(sections):
        end_pos = sections[i + 1][1] if i + 1 < len(sections) else len(text)
        section_text = text[start_pos:end_pos].strip()
        if not section_text:
            continue
        line_start = line_offset + text[:start_pos].count("\n") + 1

        if len(section_text) <= CHUNK_TARGET_CHARS:
            line_end = line_start + section_text.count("\n")
            yield (heading, section_text, line_start, line_end)
            continue

        # Long section: split by H3 first, then fall back to char windows.
        h3_positions = [(m.group(1), m.start()) for m in H3_RE.finditer(section_text)]
        if h3_positions and len(h3_positions) > 1:
            for j, (sub_heading, sub_pos) in enumerate(h3_positions):
                sub_end = h3_positions[j + 1][1] if j + 1 < len(h3_positions) else len(section_text)
                sub_text = section_text[sub_pos:sub_end].strip()
                if not sub_text:
                    continue
                sub_line_start = line_start + section_text[:sub_pos].count("\n")
                sub_line_end = sub_line_start + sub_text.count("\n")
                yield (f"{heading} > {sub_heading}", sub_text, sub_line_start, sub_line_end)
                if len(sub_text) > CHUNK_HARD_MAX:
                    # split this sub-section further by chars
                    yield from _split_chars(heading + " > " + sub_heading, sub_text,
                                            sub_line_start)
        else:
            yield from _split_chars(heading, section_text, line_start)


def _split_chars(heading: str, text: str, line_start: int) -> Iterator[tuple[str, str, int, int]]:
    pos = 0
    while pos < len(text):
        end = min(pos + CHUNK_TARGET_CHARS, len(text))
        # Try to break on a paragraph
        if end < len(text):
            nl = text.rfind("\n\n", pos, end)
            if nl > pos + 400:
                end = nl
        chunk = text[pos:end].strip()
        if chunk:
            chunk_line_start = line_start + text[:pos].count("\n")
            chunk_line_end = chunk_line_start + chunk.count("\n")
            yield (heading, chunk, chunk_line_start, chunk_line_end)
        pos = end


def _walk_sources() -> Iterator[tuple[str, Path]]:
    for kind, patterns in SCOPES.items():
        for pattern in patterns:
            for path in PROJECT_ROOT.glob(pattern):
                if path.name in EXCLUDE_NAMES:
                    continue
                if "ARCHIVES" in path.parts:
                    continue
                yield (kind, path)


def build(force: bool = False) -> dict:
    """Full reindex (or incremental if force=False)."""
    conn = connect()
    try:
        sources_seen: set[str] = set()
        chunks_added = 0
        files_indexed = 0
        files_skipped = 0
        for kind, path in _walk_sources():
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            sources_seen.add(rel)
            file_hash = _hash_file(path)

            existing = conn.execute(
                "SELECT source_hash FROM source_state WHERE source=?", (rel,),
            ).fetchone()
            if not force and existing and existing["source_hash"] == file_hash:
                files_skipped += 1
                continue

            text = path.read_text(encoding="utf-8", errors="replace")
            tags = _extract_tags(text)
            body, line_offset = _strip_frontmatter(text)

            conn.execute("BEGIN IMMEDIATE")
            try:
                # Wipe existing chunks for this source
                old = conn.execute(
                    "SELECT rowid FROM chunk_meta WHERE source=?", (rel,),
                ).fetchall()
                for row in old:
                    conn.execute("DELETE FROM memory_chunks WHERE rowid=?", (row["rowid"],))
                conn.execute("DELETE FROM chunk_meta WHERE source=?", (rel,))

                count = 0
                for idx, (heading, chunk, ls, le) in enumerate(
                    _chunk_markdown(body, line_offset)
                ):
                    cur = conn.execute(
                        "INSERT INTO memory_chunks(source, kind, heading, body, tags) "
                        "VALUES (?,?,?,?,?)",
                        (rel, kind, heading, chunk, tags),
                    )
                    rowid = cur.lastrowid
                    conn.execute(
                        "INSERT INTO chunk_meta(rowid, source, source_hash, chunk_idx, "
                        "line_start, line_end, last_indexed) VALUES (?,?,?,?,?,?,?)",
                        (rowid, rel, file_hash, idx, ls, le, _now_iso()),
                    )
                    count += 1
                    chunks_added += 1
                conn.execute(
                    "INSERT INTO source_state(source, source_hash, chunk_count, last_indexed) "
                    "VALUES (?,?,?,?) "
                    "ON CONFLICT(source) DO UPDATE SET source_hash=excluded.source_hash, "
                    "  chunk_count=excluded.chunk_count, last_indexed=excluded.last_indexed",
                    (rel, file_hash, count, _now_iso()),
                )
                conn.execute("COMMIT")
                files_indexed += 1
            except Exception:
                conn.execute("ROLLBACK")
                raise

        # Garbage-collect deleted files
        all_known = {row["source"] for row in conn.execute("SELECT source FROM source_state")}
        for stale in all_known - sources_seen:
            conn.execute("BEGIN IMMEDIATE")
            try:
                old = conn.execute(
                    "SELECT rowid FROM chunk_meta WHERE source=?", (stale,),
                ).fetchall()
                for row in old:
                    conn.execute("DELETE FROM memory_chunks WHERE rowid=?", (row["rowid"],))
                conn.execute("DELETE FROM chunk_meta WHERE source=?", (stale,))
                conn.execute("DELETE FROM source_state WHERE source=?", (stale,))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return {
            "files_indexed": files_indexed,
            "files_skipped": files_skipped,
            "chunks_added": chunks_added,
            "sources_total": len(sources_seen),
        }
    finally:
        conn.close()


def update() -> dict:
    """Incremental — only re-index files whose hash changed."""
    return build(force=False)


def _sanitize_query(text: str) -> tuple[str, str]:
    """Convert free-text into a primary AND query and an OR fallback.

    FTS5 default operator is AND; we use that for precision. If no rows
    match, the caller falls back to OR for recall.
    """
    tokens = [t for t in re.findall(r"[A-Za-z0-9_]+", text) if len(t) >= 2]
    if not tokens:
        return ("", "")
    quoted = [f'"{t}"' for t in tokens]
    return (" AND ".join(quoted), " OR ".join(quoted))


def _run_match(conn: sqlite3.Connection, fts_query: str, limit: int,
               kind: str | None) -> list[sqlite3.Row]:
    sql = (
        "SELECT mc.source, mc.kind, mc.heading, "
        "       snippet(memory_chunks, 3, '«', '»', ' … ', 16) AS snip, "
        "       bm25(memory_chunks) AS score, "
        "       cm.line_start, cm.line_end "
        "FROM memory_chunks mc JOIN chunk_meta cm ON mc.rowid = cm.rowid "
        "WHERE memory_chunks MATCH ?"
    )
    params: list = [fts_query]
    if kind:
        sql += " AND mc.kind = ?"
        params.append(kind)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit * 3)
    return conn.execute(sql, params).fetchall()


def query(text: str, limit: int = 5, kind: str | None = None) -> list[dict]:
    if not INDEX_DB.exists():
        return []
    and_query, or_query = _sanitize_query(text)
    if not and_query:
        return []
    conn = connect(read_only=True)
    try:
        rows = _run_match(conn, and_query, limit, kind)
        if not rows and or_query and or_query != and_query:
            rows = _run_match(conn, or_query, limit, kind)
        out: list[dict] = []
        spent_chars = 0
        budget = MAX_RESULT_TOKENS * APPROX_CHARS_PER_TOKEN
        for row in rows:
            snip_chars = len(row["snip"]) + len(row["heading"]) + len(row["source"]) + 40
            if spent_chars + snip_chars > budget and out:
                break
            out.append({
                "source": row["source"],
                "kind": row["kind"],
                "heading": row["heading"],
                "snippet": row["snip"].strip(),
                "score": round(row["score"], 4),
                "line_range": f"{row['line_start']}-{row['line_end']}",
                "ref": f"{row['source']}:{row['line_start']}",
            })
            spent_chars += snip_chars
            if len(out) >= limit:
                break
        return out
    finally:
        conn.close()


def status() -> dict:
    if not INDEX_DB.exists():
        return {"index": "missing", "path": str(INDEX_DB)}
    conn = connect(read_only=True)
    try:
        rows = conn.execute(
            "SELECT COUNT(*) AS sources, SUM(chunk_count) AS chunks, MAX(last_indexed) AS last "
            "FROM source_state"
        ).fetchone()
        per_kind = conn.execute(
            "SELECT mc.kind, COUNT(*) AS c FROM memory_chunks mc GROUP BY mc.kind"
        ).fetchall()
        size_bytes = INDEX_DB.stat().st_size
        return {
            "index": str(INDEX_DB),
            "size_kb": round(size_bytes / 1024, 1),
            "sources": rows["sources"] or 0,
            "chunks": rows["chunks"] or 0,
            "by_kind": {r["kind"]: r["c"] for r in per_kind},
            "last_indexed": rows["last"],
        }
    finally:
        conn.close()


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cmd_build(args) -> int:
    result = build(force=args.force)
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def _cmd_update(args) -> int:
    result = update()
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def _cmd_query(args) -> int:
    hits = query(args.text, limit=args.limit, kind=args.kind)
    if args.json:
        print(json.dumps({"query": args.text, "hits": hits}, indent=2))
    else:
        if not hits:
            print(f"No matches for: {args.text}")
            return 0
        for i, hit in enumerate(hits, 1):
            print(f"\n[{i}] {hit['ref']}  (kind={hit['kind']}, score={hit['score']})")
            if hit["heading"]:
                print(f"    » {hit['heading']}")
            print(f"    {hit['snippet']}")
    return 0


def _cmd_status(args) -> int:
    print(json.dumps(status(), indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6.0 FTS5 memory retriever")
    sub = p.add_subparsers(dest="command", required=True)

    bd = sub.add_parser("build", help="Full reindex (or incremental)")
    bd.add_argument("--force", action="store_true", help="Reindex even if hash unchanged")
    bd.set_defaults(func=_cmd_build)

    up = sub.add_parser("update", help="Incremental reindex")
    up.set_defaults(func=_cmd_update)

    qy = sub.add_parser("query", help="Run a retrieval query")
    qy.add_argument("text")
    qy.add_argument("--limit", type=int, default=5)
    qy.add_argument("--kind", default=None, choices=sorted(SCOPES.keys()))
    qy.add_argument("--json", action="store_true")
    qy.set_defaults(func=_cmd_query)

    st = sub.add_parser("status", help="Index health")
    st.set_defaults(func=_cmd_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
