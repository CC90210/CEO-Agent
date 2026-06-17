"""V6.0 FTS5 retrieval over memory/, skills/, brain/.

Replaces whole-file context loads with snippet-level retrieval. The agent
queries `memory_retriever.py query "..."` and gets ranked chunks with
file+line refs instead of pulling 100K tokens of markdown into context.

CLI:
  python scripts/core/memory_retriever.py build              # full reindex
  python scripts/core/memory_retriever.py update             # incremental
  python scripts/core/memory_retriever.py query "stripe refund"
  python scripts/core/memory_retriever.py query --kind skill "schedule social post"
  python scripts/core/memory_retriever.py query --json "..." --limit 8
  python scripts/core/memory_retriever.py status             # index health
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "state"
INDEX_DB = STATE_DIR / "memory_index.db"
MIGRATIONS_DIR = STATE_DIR / "migrations"

# V6 BUILD 2 — semantic retrieval substrate (LanceDB + fastembed/ONNX).
# Lazy-loaded: a caller that only wants --lexical-only never imports either lib.
_LANCE_DIR = STATE_DIR / "memory_lance"
_LANCE_TABLE = "memory_chunks"
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # ONNX-quantized; 384-dim; ~80MB
EMBED_DIM = 384
RRF_K = 60                # Reciprocal Rank Fusion constant (standard)
EMBED_BATCH_SIZE = 256    # fastembed throughput sweet spot on CPU

# Indexing scope — relative paths from PROJECT_ROOT.
SCOPES: dict[str, list[str]] = {
    "memory":  ["memory/*.md"],
    "skill":   ["skills/*/SKILL.md"],
    "brain":   ["brain/*.md"],
    "entry":   ["CLAUDE.md", "AGENTS.md", "GEMINI.md", "ANTIGRAVITY.md", "OPENCODE.md", "ZCODE.md"],
    "context": ["CONTEXT.md"],
    "adr":     ["docs/adr/*.md"],
    "prompt":  ["prompts/*.md"],
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


# ── V6 BUILD 2: fastembed + LanceDB helpers (lazy-loaded) ─────────────────────

_embedder = None  # module-level singleton — first call pays the model-load cost


def _get_embedder():
    """Lazy-load the fastembed TextEmbedding model. Costs ~5s cold-start (first
    call downloads + initializes the ONNX runtime); subsequent calls are free.
    """
    global _embedder
    if _embedder is None:
        import os
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        from fastembed import TextEmbedding  # type: ignore[import-not-found]
        _embedder = TextEmbedding(model_name=EMBED_MODEL_NAME)
    return _embedder


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate L2-normalized 384-dim embeddings for a batch of texts."""
    if not texts:
        return []
    emb = _get_embedder()
    return [list(map(float, v)) for v in emb.embed(texts, batch_size=EMBED_BATCH_SIZE)]


def _open_lance_table(create_if_missing: bool = True):
    """Open the LanceDB `memory_chunks` table; create with schema on first use.

    Returns the table handle, or None if LanceDB isn't installed (graceful
    degrade — query() falls back to FTS5-only).
    """
    try:
        import lancedb  # type: ignore[import-not-found]
        import pyarrow as pa  # type: ignore[import-not-found]
    except ImportError:
        return None
    _LANCE_DIR.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(_LANCE_DIR))
    # LanceDB has shifted shapes for this call across versions:
    #   * legacy: table_names() → list[str]
    #   * 0.30+:  list_tables() → TableNamesResponse(tables=[...], page_token=...)
    #   * some others: list_tables() → list[str] directly
    # Handle all three by extracting the list defensively.
    try:
        raw = db.list_tables()
    except AttributeError:
        raw = db.table_names()
    if hasattr(raw, "tables"):
        existing = list(raw.tables)
    elif isinstance(raw, (list, tuple)):
        existing = list(raw)
    else:
        # Last resort — try iterating (returns Iterator[str] in some builds).
        try:
            existing = list(raw)
        except TypeError:
            existing = []
    if _LANCE_TABLE in existing:
        return db.open_table(_LANCE_TABLE)
    if not create_if_missing:
        return None
    schema = pa.schema([
        pa.field("chunk_id",     pa.string()),
        pa.field("source",       pa.string()),
        pa.field("kind",         pa.string()),
        pa.field("heading",      pa.string()),
        pa.field("body",         pa.string()),
        pa.field("tags",         pa.string()),
        pa.field("line_start",   pa.int32()),
        pa.field("line_end",     pa.int32()),
        pa.field("chunk_idx",    pa.int32()),
        pa.field("source_hash",  pa.string()),
        pa.field("last_indexed", pa.string()),
        pa.field("vector",       pa.list_(pa.float32(), EMBED_DIM)),
    ])
    return db.create_table(_LANCE_TABLE, schema=schema)


def _lance_delete_source(table, source: str) -> None:
    """Remove all chunks for a given source path before re-embedding."""
    if table is None:
        return
    try:
        table.delete(f"source = '{source.replace(chr(39), chr(39)*2)}'")
    except Exception:
        pass


def _lance_upsert_chunks(table, rows: list[dict]) -> None:
    """Append a batch of embedded rows to the LanceDB table."""
    if table is None or not rows:
        return
    table.add(rows)


def _rrf_merge(rankings: list[list[tuple[str, int]]],
               k: int = RRF_K, limit: int = 5) -> list[tuple[str, int]]:
    """Reciprocal Rank Fusion across multiple rankings.

    Each ranking is an ordered list of (source, chunk_idx) keys. RRF score for
    a chunk = sum over rankings of 1/(k + rank). Returns the top `limit` keys
    by aggregate score.

    Why RRF (and not raw score normalization): BM25 scores and cosine
    similarities live on different scales — combining them numerically
    requires per-corpus tuning that drifts. Rank-only fusion is parameter-light
    and provably robust against scale mismatches.
    """
    from collections import defaultdict
    scores: dict[tuple[str, int], float] = defaultdict(float)
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] += 1.0 / (k + rank)
    # Sort: score DESC, then chunk-key ASC. The secondary key makes the
    # merger deterministic regardless of input-ranking insertion order —
    # required for `r1, r2` and `r2, r1` to produce the same merged output
    # when ties exist (provably-correct RRF behavior).
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [key for key, _ in ranked[:limit]]


def _walk_sources() -> Iterator[tuple[str, Path]]:
    for kind, patterns in SCOPES.items():
        for pattern in patterns:
            for path in PROJECT_ROOT.glob(pattern):
                if path.name in EXCLUDE_NAMES:
                    continue
                if "ARCHIVES" in path.parts:
                    continue
                yield (kind, path)


def build(force: bool = False, semantic: bool = True) -> dict:
    """Full reindex (or incremental if force=False).

    `semantic=True` (default) also generates 384-dim ONNX embeddings via
    fastembed and upserts them into the LanceDB store at `state/memory_lance/`.
    Set `semantic=False` to rebuild the FTS5 index without touching LanceDB
    (faster — useful when only the lexical layer is needed).
    """
    conn = connect()
    lance = _open_lance_table(create_if_missing=True) if semantic else None
    semantic_chunks_embedded = 0
    try:
        sources_seen: set[str] = set()
        chunks_added = 0
        files_indexed = 0
        files_skipped = 0
        now_iso = _now_iso()
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

            # Materialize all chunks for this source so we can batch the embedder.
            file_chunks: list[tuple[int, str, str, int, int]] = list(
                (idx, heading, chunk, ls, le)
                for idx, (heading, chunk, ls, le) in enumerate(_chunk_markdown(body, line_offset))
            )

            # Embed in batch BEFORE the SQLite transaction (CPU work; no DB lock held).
            embeddings: list[list[float]] = []
            if lance is not None and file_chunks:
                embeddings = _embed_texts([f"{h}\n\n{c}" if h else c
                                            for (_, h, c, _, _) in file_chunks])

            conn.execute("BEGIN IMMEDIATE")
            try:
                old = conn.execute(
                    "SELECT rowid FROM chunk_meta WHERE source=?", (rel,),
                ).fetchall()
                for row in old:
                    conn.execute("DELETE FROM memory_chunks WHERE rowid=?", (row["rowid"],))
                conn.execute("DELETE FROM chunk_meta WHERE source=?", (rel,))

                count = 0
                lance_rows: list[dict] = []
                for embed_idx, (idx, heading, chunk, ls, le) in enumerate(file_chunks):
                    cur = conn.execute(
                        "INSERT INTO memory_chunks(source, kind, heading, body, tags) "
                        "VALUES (?,?,?,?,?)",
                        (rel, kind, heading, chunk, tags),
                    )
                    rowid = cur.lastrowid
                    conn.execute(
                        "INSERT INTO chunk_meta(rowid, source, source_hash, chunk_idx, "
                        "line_start, line_end, last_indexed) VALUES (?,?,?,?,?,?,?)",
                        (rowid, rel, file_hash, idx, ls, le, now_iso),
                    )
                    count += 1
                    chunks_added += 1
                    if lance is not None and embeddings:
                        lance_rows.append({
                            "chunk_id":     f"{rel}::{idx}",
                            "source":       rel,
                            "kind":         kind,
                            "heading":      heading or "",
                            "body":         chunk,
                            "tags":         tags or "",
                            "line_start":   ls,
                            "line_end":     le,
                            "chunk_idx":    idx,
                            "source_hash":  file_hash,
                            "last_indexed": now_iso,
                            "vector":       embeddings[embed_idx],
                        })
                conn.execute(
                    "INSERT INTO source_state(source, source_hash, chunk_count, last_indexed) "
                    "VALUES (?,?,?,?) "
                    "ON CONFLICT(source) DO UPDATE SET source_hash=excluded.source_hash, "
                    "  chunk_count=excluded.chunk_count, last_indexed=excluded.last_indexed",
                    (rel, file_hash, count, now_iso),
                )
                conn.execute("COMMIT")
                files_indexed += 1

                # LanceDB upsert AFTER the FTS5 commit — keeps stores consistent
                # even if Lance fails (FTS5 wins; semantic is best-effort).
                if lance is not None and lance_rows:
                    try:
                        _lance_delete_source(lance, rel)
                        _lance_upsert_chunks(lance, lance_rows)
                        semantic_chunks_embedded += len(lance_rows)
                    except Exception as exc:
                        print(f"[memory_retriever] LanceDB upsert failed for {rel}: {exc}",
                              file=sys.stderr)
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
                # Mirror the GC to LanceDB — same stale-source delete.
                if lance is not None:
                    _lance_delete_source(lance, stale)
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return {
            "files_indexed": files_indexed,
            "files_skipped": files_skipped,
            "chunks_added": chunks_added,
            "semantic_chunks_embedded": semantic_chunks_embedded,
            "semantic_enabled": lance is not None,
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


def _lexical_query(text: str, limit: int, kind: str | None,
                   conn: sqlite3.Connection) -> tuple[list[dict], list[tuple[str, int]]]:
    """Return (hits, ranking) for the FTS5 lexical pass.

    `hits` is the existing dict-shape result list. `ranking` is the ordered
    list of (source, chunk_idx) keys the RRF merger needs. The two share
    the same order so a caller doing lexical-only can just take `hits`.
    """
    and_query, or_query = _sanitize_query(text)
    if not and_query:
        return ([], [])
    sql = (
        "SELECT mc.source, mc.kind, mc.heading, "
        "       snippet(memory_chunks, 3, '«', '»', ' … ', 16) AS snip, "
        "       bm25(memory_chunks) AS score, "
        "       cm.line_start, cm.line_end, cm.chunk_idx "
        "FROM memory_chunks mc JOIN chunk_meta cm ON mc.rowid = cm.rowid "
        "WHERE memory_chunks MATCH ?"
    )
    params: list = [and_query]
    if kind:
        sql += " AND mc.kind = ?"
        params.append(kind)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit * 3)
    rows = conn.execute(sql, params).fetchall()
    if not rows and or_query and or_query != and_query:
        params[0] = or_query
        rows = conn.execute(sql, params).fetchall()

    hits: list[dict] = []
    ranking: list[tuple[str, int]] = []
    for row in rows:
        hits.append({
            "source":     row["source"],
            "kind":       row["kind"],
            "heading":    row["heading"],
            "snippet":    row["snip"].strip(),
            "lex_score":  round(row["score"], 4),
            "line_range": f"{row['line_start']}-{row['line_end']}",
            "ref":        f"{row['source']}:{row['line_start']}",
            "chunk_idx":  row["chunk_idx"],
        })
        ranking.append((row["source"], row["chunk_idx"]))
    return (hits, ranking)


def _semantic_query(text: str, limit: int, kind: str | None,
                    ) -> tuple[list[dict], list[tuple[str, int]]]:
    """Return (hits, ranking) from a LanceDB cosine search.

    Returns ([], []) if the query is empty/whitespace, LanceDB isn't installed,
    or the table is empty (graceful degrade — query() then degrades to
    lexical-only).
    """
    # Empty / whitespace queries don't represent intent. fastembed would
    # happily return a default embedding and LanceDB would surface nearest
    # neighbors — surfacing arbitrary "closest to empty string" chunks
    # would mislead the agent.
    if not text or not text.strip():
        return ([], [])
    table = _open_lance_table(create_if_missing=False)
    if table is None:
        return ([], [])
    try:
        vec = _embed_texts([text])[0]
    except Exception as exc:
        print(f"[memory_retriever] embed failed: {exc}", file=sys.stderr)
        return ([], [])
    try:
        search = table.search(vec).metric("cosine")
        if kind:
            search = search.where(f"kind = '{kind}'", prefilter=True)
        result = search.limit(limit * 3).to_list()
    except Exception as exc:
        print(f"[memory_retriever] LanceDB search failed: {exc}", file=sys.stderr)
        return ([], [])

    hits: list[dict] = []
    ranking: list[tuple[str, int]] = []
    for row in result:
        # LanceDB returns _distance for cosine; smaller = closer. Convert to
        # a similarity in [0, 1] for human-readable display.
        dist = float(row.get("_distance", 1.0))
        sim = max(0.0, 1.0 - dist)
        body = row.get("body") or ""
        snippet = body[:240].replace("\n", " ").strip()
        hits.append({
            "source":     row["source"],
            "kind":       row.get("kind", ""),
            "heading":    row.get("heading", ""),
            "snippet":    snippet,
            "sem_score":  round(sim, 4),
            "line_range": f"{row.get('line_start', 0)}-{row.get('line_end', 0)}",
            "ref":        f"{row['source']}:{row.get('line_start', 0)}",
            "chunk_idx":  int(row.get("chunk_idx", 0)),
        })
        ranking.append((row["source"], int(row.get("chunk_idx", 0))))
    return (hits, ranking)


def _hits_by_key(hits: list[dict]) -> dict[tuple[str, int], dict]:
    """Index a hit list by (source, chunk_idx) for the RRF reconciliation pass."""
    return {(h["source"], h["chunk_idx"]): h for h in hits}


def query(text: str, limit: int = 5, kind: str | None = None,
          mode: str = "hybrid", explain: bool = False) -> list[dict]:
    """Retrieve ranked snippets.

    mode: 'hybrid' (default — FTS5 + LanceDB merged via RRF),
          'lexical' (FTS5 only — original behavior),
          'semantic' (LanceDB only — cosine on ONNX embeddings).
    explain: when True, each result includes `lex_rank`, `sem_rank`, `rrf_score`
             so callers can introspect why an item ranked where it did.
    """
    if not INDEX_DB.exists():
        return []
    conn = connect(read_only=True)
    try:
        if mode == "lexical":
            hits, _ = _lexical_query(text, limit, kind, conn)
            return _trim_to_budget(hits, limit, kind_field="lex_score")
        if mode == "semantic":
            hits, _ = _semantic_query(text, limit, kind)
            return _trim_to_budget(hits, limit, kind_field="sem_score")

        # Hybrid path — run both legs, RRF-merge.
        lex_hits, lex_rank = _lexical_query(text, limit, kind, conn)
        sem_hits, sem_rank = _semantic_query(text, limit, kind)
        if not sem_hits:
            # Semantic unavailable (lib missing, empty table, embed failure) —
            # degrade silently to lexical-only.
            return _trim_to_budget(lex_hits, limit, kind_field="lex_score")
        if not lex_hits:
            return _trim_to_budget(sem_hits, limit, kind_field="sem_score")

        merged_keys = _rrf_merge([lex_rank, sem_rank], k=RRF_K, limit=limit * 3)
        lex_by_key = _hits_by_key(lex_hits)
        sem_by_key = _hits_by_key(sem_hits)
        lex_rank_map = {key: r for r, key in enumerate(lex_rank, start=1)}
        sem_rank_map = {key: r for r, key in enumerate(sem_rank, start=1)}

        merged: list[dict] = []
        for key in merged_keys:
            h = lex_by_key.get(key) or sem_by_key.get(key)
            if not h:
                continue
            # Prefer the FTS5 snippet (it's «highlighted») when both surfaced.
            if key in lex_by_key:
                h = dict(lex_by_key[key])
                if key in sem_by_key:
                    h["sem_score"] = sem_by_key[key]["sem_score"]
            else:
                h = dict(sem_by_key[key])

            lex_rank_of = lex_rank_map.get(key)
            sem_rank_of = sem_rank_map.get(key)
            rrf = 0.0
            if lex_rank_of is not None:
                rrf += 1.0 / (RRF_K + lex_rank_of)
            if sem_rank_of is not None:
                rrf += 1.0 / (RRF_K + sem_rank_of)
            h["rrf_score"] = round(rrf, 6)
            h["score"] = h["rrf_score"]
            if explain:
                h["lex_rank"] = lex_rank_of
                h["sem_rank"] = sem_rank_of
                h["explain"] = (
                    f"lex_rank={lex_rank_of or '∞'} sem_rank={sem_rank_of or '∞'} "
                    f"→ rrf={h['rrf_score']:.4f}"
                )
            else:
                h.pop("lex_score", None)
                h.pop("sem_score", None)
            merged.append(h)
        return _trim_to_budget(merged, limit, kind_field="score")
    finally:
        conn.close()


def _trim_to_budget(hits: list[dict], limit: int, kind_field: str = "score") -> list[dict]:
    """Apply the per-query output cap (~1500 tokens) and clip to `limit`."""
    out: list[dict] = []
    spent = 0
    budget = MAX_RESULT_TOKENS * APPROX_CHARS_PER_TOKEN
    for h in hits:
        cost = len(h.get("snippet", "")) + len(h.get("heading", "")) + len(h.get("source", "")) + 40
        if spent + cost > budget and out:
            break
        # Promote whichever score field exists into a unified "score" for display.
        if "score" not in h and kind_field in h:
            h["score"] = h[kind_field]
        out.append(h)
        spent += cost
        if len(out) >= limit:
            break
    return out


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
        out: dict = {
            "index": str(INDEX_DB),
            "size_kb": round(size_bytes / 1024, 1),
            "sources": rows["sources"] or 0,
            "chunks": rows["chunks"] or 0,
            "by_kind": {r["kind"]: r["c"] for r in per_kind},
            "last_indexed": rows["last"],
        }
        # V6 BUILD 2 — surface LanceDB health alongside FTS5.
        lance = _open_lance_table(create_if_missing=False)
        if lance is not None:
            try:
                semantic_count = lance.count_rows()
            except Exception:
                semantic_count = None
            out["semantic"] = {
                "store":          "lancedb",
                "path":           str(_LANCE_DIR),
                "model":          EMBED_MODEL_NAME,
                "dim":            EMBED_DIM,
                "rows":           semantic_count,
                "size_kb":        _dir_size_kb(_LANCE_DIR),
            }
        else:
            out["semantic"] = {"store": "absent", "reason": "lancedb not installed or no table yet"}
        return out
    finally:
        conn.close()


def _dir_size_kb(path: Path) -> float:
    """Sum of file sizes under `path`, rounded to KB. Returns 0 if missing."""
    if not path.exists():
        return 0.0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return round(total / 1024, 1)


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cmd_build(args) -> int:
    result = build(force=args.force, semantic=not args.lexical_only)
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def _cmd_update(args) -> int:
    result = update()
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def _cmd_query(args) -> int:
    # Resolve mode from the mutually-exclusive flags. Default = hybrid.
    if args.lexical_only:
        mode = "lexical"
    elif args.semantic_only:
        mode = "semantic"
    else:
        mode = "hybrid"

    hits = query(args.text, limit=args.limit, kind=args.kind,
                 mode=mode, explain=args.explain)
    if args.json:
        print(json.dumps({"query": args.text, "mode": mode, "hits": hits},
                         indent=2, default=str))
    else:
        if not hits:
            print(f"No matches for: {args.text} (mode={mode})")
            return 0
        for i, hit in enumerate(hits, 1):
            score = hit.get("score") or hit.get("rrf_score") or hit.get("lex_score") or hit.get("sem_score")
            print(f"\n[{i}] {hit['ref']}  (kind={hit['kind']}, score={score})")
            if hit["heading"]:
                print(f"    » {hit['heading']}")
            print(f"    {hit['snippet']}")
            if args.explain and "explain" in hit:
                print(f"    [explain] {hit['explain']}")
    return 0


def _cmd_status(args) -> int:
    print(json.dumps(status(), indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6.0 FTS5 memory retriever")
    sub = p.add_subparsers(dest="command", required=True)

    bd = sub.add_parser("build", help="Full reindex (or incremental)")
    bd.add_argument("--force", action="store_true", help="Reindex even if hash unchanged")
    bd.add_argument("--lexical-only", action="store_true",
                    help="Skip the LanceDB/fastembed pass — rebuild FTS5 only (faster)")
    bd.set_defaults(func=_cmd_build)

    up = sub.add_parser("update", help="Incremental reindex")
    up.set_defaults(func=_cmd_update)

    qy = sub.add_parser("query", help="Run a retrieval query")
    qy.add_argument("text")
    qy.add_argument("--limit", type=int, default=5)
    qy.add_argument("--kind", default=None, choices=sorted(SCOPES.keys()))
    qy.add_argument("--json", action="store_true")
    # V6 BUILD 2 — retrieval mode. Mutually exclusive; default = hybrid.
    mode_group = qy.add_mutually_exclusive_group()
    mode_group.add_argument("--lexical-only", action="store_true",
                            help="FTS5 only — original V6 BUILD 1 behavior")
    mode_group.add_argument("--semantic-only", action="store_true",
                            help="LanceDB cosine search only — pure semantic")
    qy.add_argument("--explain", action="store_true",
                    help="Show lex_rank / sem_rank / rrf_score per result")
    qy.set_defaults(func=_cmd_query)

    st = sub.add_parser("status", help="Index health")
    st.set_defaults(func=_cmd_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
