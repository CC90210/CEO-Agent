-- ============================================================
-- BRAVO V5.6.1 — Migration 009: Relationship Graph
-- Apply via: python scripts/apply_migration.py database/009_relationship_graph.sql
-- ============================================================
-- PURPOSE
-- Leads are not islands. Bob referred Carlos. Jane at Acme works with
-- Mark. Acme was acquired by Delta. With these edges captured, Bravo
-- can prepend "Bob referred you" to a cold email, recognize warm-intro
-- paths, and surface lookalike leads in the same industry cluster.
-- ============================================================

CREATE TABLE IF NOT EXISTS lead_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_lead_id UUID NOT NULL,
    to_lead_id UUID NOT NULL,
    edge_type TEXT NOT NULL
        CHECK (edge_type IN ('referral', 'colleague', 'vendor',
                             'competitor', 'industry_peer', 'acquired_by',
                             'works_with', 'mentored_by', 'client_of')),
    weight NUMERIC(3,2) DEFAULT 1.00
        CHECK (weight BETWEEN 0.00 AND 1.00),
    bidirectional BOOLEAN DEFAULT FALSE,
    discovered_source TEXT,
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(from_lead_id, to_lead_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_lead_edges_from
    ON lead_edges (from_lead_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_lead_edges_to
    ON lead_edges (to_lead_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_lead_edges_type_weight
    ON lead_edges (edge_type, weight DESC);

COMMENT ON TABLE lead_edges IS
    'Directed graph of lead-to-lead relationships. A referral has '
    'weight 1.0, an industry_peer 0.3. Bidirectional edges store a '
    'single row with bidirectional=TRUE. Populated by CC manually or '
    'by scripts/relationship_graph.py inference.';

-- Lightweight "neighbors of lead X" helper used by context_builder.
CREATE OR REPLACE FUNCTION lead_neighbors(p_lead_id UUID, p_limit INTEGER DEFAULT 10)
RETURNS TABLE(
    other_lead_id UUID,
    edge_type TEXT,
    weight NUMERIC,
    direction TEXT,
    notes TEXT
) LANGUAGE sql STABLE AS $$
    SELECT to_lead_id AS other_lead_id, edge_type, weight,
           'outbound' AS direction, notes
    FROM lead_edges
    WHERE from_lead_id = p_lead_id
    UNION ALL
    SELECT from_lead_id AS other_lead_id, edge_type, weight,
           CASE WHEN bidirectional THEN 'bidirectional' ELSE 'inbound' END,
           notes
    FROM lead_edges
    WHERE to_lead_id = p_lead_id
    ORDER BY weight DESC NULLS LAST
    LIMIT p_limit;
$$;

COMMENT ON FUNCTION lead_neighbors(UUID, INTEGER) IS
    'Return up to N neighbors of a lead, both outbound and inbound '
    'edges, weight-sorted. Used by context_builder to surface '
    'referral/colleague context in outbound prompts.';

-- ============================================================
-- END OF MIGRATION 009
-- ============================================================
