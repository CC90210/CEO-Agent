-- ============================================================
-- BRAVO V5.6.1 — Migration 007: Tiered Memory
-- Apply via: python scripts/apply_migration.py database/007_tiered_memory.sql
-- ============================================================
-- PURPOSE
-- The existing `memories` table (from migration 001) is a flat bag. Real
-- cognitive memory has structure:
--   EPISODIC   — specific events ("Jane@Acme asked about pricing Apr 12")
--   SEMANTIC   — generalized patterns ("HVAC owners respond to efficiency
--                framing") — compiled from N episodic memories
--   PROCEDURAL — validated workflows ("on booking: confirm + reminder")
--                — promoted from repeated successful runs
-- With decay on episodic (90 days), slow decay on semantic (180 days),
-- and effectively immortal procedural (only demoted on failure).
-- ============================================================

-- 1. EPISODIC — raw specific events, decay fastest -----------------------------
CREATE TABLE IF NOT EXISTS memories_episodic (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    context_type TEXT,
    related_lead_id UUID,
    related_interaction_id UUID,
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    confidence NUMERIC(4,3) DEFAULT 0.85,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days'),
    consolidated_into_id UUID
);
CREATE INDEX IF NOT EXISTS idx_mem_ep_lead ON memories_episodic (related_lead_id);
CREATE INDEX IF NOT EXISTS idx_mem_ep_expires ON memories_episodic (expires_at);
CREATE INDEX IF NOT EXISTS idx_mem_ep_tags ON memories_episodic USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_mem_ep_content_trgm
    ON memories_episodic USING GIN (content gin_trgm_ops);

-- 2. SEMANTIC — compiled patterns ---------------------------------------------
CREATE TABLE IF NOT EXISTS memories_semantic (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern TEXT NOT NULL,
    domain TEXT,
    supporting_episodic_ids UUID[] DEFAULT ARRAY[]::UUID[],
    evidence_count INTEGER DEFAULT 1,
    counter_evidence_count INTEGER DEFAULT 0,
    confidence NUMERIC(4,3) DEFAULT 0.70,
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '180 days'),
    promoted_to_procedural_id UUID
);
CREATE INDEX IF NOT EXISTS idx_mem_sem_domain ON memories_semantic (domain);
CREATE INDEX IF NOT EXISTS idx_mem_sem_confidence
    ON memories_semantic (confidence DESC);
CREATE INDEX IF NOT EXISTS idx_mem_sem_tags ON memories_semantic USING GIN(tags);

-- 3. PROCEDURAL — validated workflows -----------------------------------------
CREATE TABLE IF NOT EXISTS memories_procedural (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_name TEXT UNIQUE NOT NULL,
    trigger_conditions JSONB NOT NULL,
    steps JSONB NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_executed TIMESTAMPTZ,
    last_success TIMESTAMPTZ,
    last_failure TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'probationary'
        CHECK (status IN ('probationary', 'validated', 'deprecated')),
    promoted_at TIMESTAMPTZ,
    demoted_at TIMESTAMPTZ,
    demotion_reason TEXT,
    owner_agent TEXT DEFAULT 'bravo',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mem_proc_status ON memories_procedural (status);
CREATE INDEX IF NOT EXISTS idx_mem_proc_name ON memories_procedural (workflow_name);

-- 4. Consolidation helper -----------------------------------------------------
-- Called by scripts/mem0_tool.py consolidation job (weekly). Given an
-- episodic_id, stores a link to the semantic memory it got compiled into.
CREATE OR REPLACE FUNCTION mark_episodic_consolidated(
    p_episodic_id UUID, p_semantic_id UUID
) RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    UPDATE memories_episodic
    SET consolidated_into_id = p_semantic_id
    WHERE id = p_episodic_id;
END $$;

COMMENT ON TABLE memories_episodic IS
    'Specific events with 90-day default expiry. Consolidated into '
    'semantic memories by the weekly pattern miner.';
COMMENT ON TABLE memories_semantic IS
    'Generalized patterns mined from episodic events. Slower decay. '
    'Promoted to procedural when the same pattern reliably produces '
    'desired outcomes 3+ times.';
COMMENT ON TABLE memories_procedural IS
    'Validated workflows. Promoted from semantic after 3 successful '
    'executions. Rarely decay unless demoted by repeated failure.';

-- ============================================================
-- END OF MIGRATION 007
-- ============================================================
