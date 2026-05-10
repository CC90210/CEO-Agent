-- V6.0 FTS5 retrieval index — separate DB so retrieval reads never block state writes.
-- Applied by scripts/memory_retriever.py on first connect; idempotent.

PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_chunks USING fts5(
  source,
  kind,
  heading,
  body,
  tags,
  tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS chunk_meta (
  rowid           INTEGER PRIMARY KEY,
  source          TEXT NOT NULL,
  source_hash     TEXT NOT NULL,
  chunk_idx       INTEGER NOT NULL,
  line_start      INTEGER NOT NULL,
  line_end        INTEGER NOT NULL,
  last_indexed    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunk_meta_source ON chunk_meta(source, source_hash);
CREATE INDEX IF NOT EXISTS idx_chunk_meta_indexed ON chunk_meta(last_indexed);

CREATE TABLE IF NOT EXISTS source_state (
  source          TEXT PRIMARY KEY,
  source_hash     TEXT NOT NULL,
  chunk_count     INTEGER NOT NULL DEFAULT 0,
  last_indexed    TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
