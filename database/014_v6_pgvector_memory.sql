-- ============================================================
-- BRAVO V6.0 — Migration 014: pgvector RAG Memory
-- Apply via: python scripts/apply_migration.py database/014_v6_pgvector_memory.sql
-- ============================================================
-- PURPOSE
-- V5.7 loads 23-25k tokens at boot from Markdown files (STATE, CAPABILITIES,
-- AGENTS, SESSION_LOG, MEMORY, etc.). This triggers "lost in the middle"
-- forgetting and burns Anthropic budget on every turn.
--
-- V6.0 inverts this: Markdown files stay as source-of-truth for humans, but
-- agents query a chunk-level index. Only the 8 most relevant chunks load
-- per turn. Estimated boot reduction: ~60-65%.
--
-- This migration adds:
--   1. pgvector + pg_trgm extensions
--   2. memory_chunks table (source_file → chunks → embedding)
--   3. Hybrid (vector + BM25 trigram) retrieval function
--   4. Link-graph column for Obsidian wiki-link expansion
--
-- Consumers:
--   - scripts/memory_ingest.py — watches brain/, memory/, knowledge/,
--     APPS_CONTEXT/ → chunks → embeds → upserts (idempotent via content_hash)
--   - scripts/memory_query.py — task string → embed → hybrid search → return
--     top-k formatted markdown context block
--
-- Relationship to migration 007 (tiered memory):
--   007 = cognitive memory (episodic/semantic/procedural events the agent
--         learned). 014 = file-content RAG (what's in the repo's markdown).
--   They do NOT overlap. Different queries hit different tables.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---- memory_chunks ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS memory_chunks (
    id              BIGSERIAL PRIMARY KEY,
    source_file     TEXT        NOT NULL,   -- e.g. 'memory/SESSION_LOG.md'
    source_heading  TEXT,                   -- nearest H2/H3 — provenance anchor
    chunk_index     INT         NOT NULL,   -- ordinal within file
    content         TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,   -- sha256 — skip unchanged chunks
    embedding       vector(1536),           -- OpenAI text-embedding-3-small
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    tags            TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    wiki_links      TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],  -- [[outgoing]]
    freshness       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence      REAL        NOT NULL DEFAULT 1.0,
    token_estimate  INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file, chunk_index)
);

-- IVF flat index for approximate nearest neighbor (cosine). 100 lists is a
-- sane default for up to ~10k chunks — re-tune once we exceed that.
CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding
    ON memory_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- BM25-ish trigram fallback for when a query's literal keywords matter
-- (e.g., "BOOKING_LINK" — vector search might miss exact-token hits).
CREATE INDEX IF NOT EXISTS idx_memory_chunks_content_trgm
    ON memory_chunks USING GIN (content gin_trgm_ops);

-- Tag filter (e.g., tag='critical-links' to always include).
CREATE INDEX IF NOT EXISTS idx_memory_chunks_tags
    ON memory_chunks USING GIN (tags);

-- Fast file-level drop/re-ingest.
CREATE INDEX IF NOT EXISTS idx_memory_chunks_source_file
    ON memory_chunks (source_file);

-- Freshness decay index (prefer recent in ties).
CREATE INDEX IF NOT EXISTS idx_memory_chunks_freshness
    ON memory_chunks (freshness DESC);

COMMENT ON TABLE memory_chunks IS
    'V6.0 RAG index. Chunks of markdown files (brain/, memory/, knowledge/, '
    'APPS_CONTEXT/). Source files remain authoritative; this is a derived '
    'read index. Populated by scripts/memory_ingest.py.';

-- ---- Hybrid search function ------------------------------------------------
--
-- Called by scripts/memory_query.py. Takes (embedded_query, text_query, k).
-- Scores: 70% vector cosine + 30% trigram similarity + freshness boost.
-- Always-included tags (e.g., 'critical-links') bypass ranking and are
-- returned at the top.

CREATE OR REPLACE FUNCTION search_memory_chunks(
    p_embedding        vector(1536),
    p_query_text       TEXT,
    p_k                INT DEFAULT 8,
    p_always_tags      TEXT[] DEFAULT ARRAY[]::TEXT[],
    p_exclude_files    TEXT[] DEFAULT ARRAY[]::TEXT[],
    p_freshness_weight REAL DEFAULT 0.05
) RETURNS TABLE (
    id              BIGINT,
    source_file     TEXT,
    source_heading  TEXT,
    content         TEXT,
    tags            TEXT[],
    wiki_links      TEXT[],
    vector_score    REAL,
    text_score      REAL,
    freshness_score REAL,
    total_score     REAL,
    pinned          BOOLEAN
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    WITH pinned AS (
        SELECT
            mc.id,
            mc.source_file,
            mc.source_heading,
            mc.content,
            mc.tags,
            mc.wiki_links,
            1.0::REAL AS vector_score,
            1.0::REAL AS text_score,
            1.0::REAL AS freshness_score,
            10.0::REAL AS total_score,
            TRUE       AS pinned
        FROM memory_chunks mc
        WHERE mc.tags && p_always_tags
          AND NOT (mc.source_file = ANY(p_exclude_files))
    ),
    scored AS (
        SELECT
            mc.id,
            mc.source_file,
            mc.source_heading,
            mc.content,
            mc.tags,
            mc.wiki_links,
            (1.0 - (mc.embedding <=> p_embedding))::REAL AS vector_score,
            similarity(mc.content, p_query_text)::REAL    AS text_score,
            GREATEST(
                0.0,
                1.0 - (EXTRACT(EPOCH FROM (NOW() - mc.freshness)) / (86400.0 * 180.0))
            )::REAL AS freshness_score,
            FALSE   AS pinned
        FROM memory_chunks mc
        WHERE p_embedding IS NOT NULL
          AND NOT (mc.source_file = ANY(p_exclude_files))
          AND NOT (mc.tags && p_always_tags)
    )
    SELECT
        s.id,
        s.source_file,
        s.source_heading,
        s.content,
        s.tags,
        s.wiki_links,
        s.vector_score,
        s.text_score,
        s.freshness_score,
        (0.70 * s.vector_score
         + 0.30 * s.text_score
         + p_freshness_weight * s.freshness_score)::REAL AS total_score,
        s.pinned
    FROM (
        SELECT * FROM pinned
        UNION ALL
        SELECT * FROM scored
    ) s
    ORDER BY s.pinned DESC, total_score DESC
    LIMIT p_k;
END $$;

COMMENT ON FUNCTION search_memory_chunks IS
    'V6.0 hybrid RAG retrieval. 70%/30% vector/trigram weighting + freshness '
    'decay. Rows tagged in p_always_tags are pinned above ranking.';

-- ============================================================
-- END OF MIGRATION 014
-- ============================================================
