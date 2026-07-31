-- V7.3.0 — L1 abstract layer (OpenViking pattern, re-implemented on FTS5).
-- FTS5 virtual tables cannot ALTER ADD COLUMN, so this rebuilds memory_chunks
-- with an `abstract` column (the per-file description: frontmatter, same value
-- on every chunk of the file) and wipes the incremental-index state so the next
-- `memory_retriever.py build` fully re-indexes + re-embeds.
--
-- GATED: applied ONLY when schema_version < 2 (see _apply_migrations in
-- scripts/core/memory_retriever.py) — running this unconditionally on every
-- connect would nuke the index each time.

DROP TABLE IF EXISTS memory_chunks;
CREATE VIRTUAL TABLE memory_chunks USING fts5(
  source,
  kind,
  heading,
  body,
  tags,
  abstract,
  tokenize='porter unicode61'
);

DELETE FROM chunk_meta;
DELETE FROM source_state;

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
