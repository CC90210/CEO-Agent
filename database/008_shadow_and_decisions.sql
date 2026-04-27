-- ============================================================
-- BRAVO V5.6.1 — Migration 008: Shadow mode + decision log
-- Apply via: python scripts/apply_migration.py database/008_shadow_and_decisions.sql
-- ============================================================
-- PURPOSE
-- Two tables supporting safe deployment and introspection:
-- (a) shadow_decisions — send_gateway in shadow mode writes what it
--     WOULD have sent here instead of actually sending. Lets CC compare
--     a new persona/policy against the current baseline before flipping.
-- (b) agent_decisions — every time autonomous_agent.py decides to act
--     (or not act), the reasoning is written here. The decision tape
--     is what makes the daemon introspectable.
-- ============================================================

-- 1. shadow_decisions ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS shadow_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_source TEXT NOT NULL,
    channel TEXT NOT NULL,
    lead_id UUID,
    to_identity TEXT,
    subject TEXT,
    body_preview TEXT,
    would_have_status TEXT NOT NULL,
    block_reason TEXT,
    comparison_run_id TEXT,
    brand TEXT,
    intent TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shadow_decisions_run
    ON shadow_decisions (comparison_run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_shadow_decisions_agent_source
    ON shadow_decisions (agent_source, created_at DESC);

COMMENT ON TABLE shadow_decisions IS
    'Writes from send_gateway when invoked with shadow=True. Used to '
    'preview the effect of a new persona/policy/prompt before it ships.';

-- 2. agent_decisions ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tick_id TEXT NOT NULL,
    agent_name TEXT NOT NULL DEFAULT 'bravo',
    phase TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    target_lead_id UUID,
    target_description TEXT,
    reasoning TEXT,
    confidence NUMERIC(4,3),
    chosen_action TEXT,
    alternatives_considered JSONB,
    executed BOOLEAN DEFAULT FALSE,
    execution_result JSONB,
    outcome_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_tick
    ON agent_decisions (tick_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_lead
    ON agent_decisions (target_lead_id, created_at DESC)
    WHERE target_lead_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_decisions_created
    ON agent_decisions (created_at DESC);

COMMENT ON TABLE agent_decisions IS
    'Decision log for the autonomous reasoning loop. Each tick produces '
    'zero or more decisions; a decision is the smallest unit of agency '
    'that can be traced, audited, replayed, or reflected on.';

-- 3. agent_state_snapshot (for daemon persistence across restarts) ------------
CREATE TABLE IF NOT EXISTS agent_state_snapshot (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT UNIQUE NOT NULL,
    tick_count INTEGER DEFAULT 0,
    last_tick_at TIMESTAMPTZ,
    last_tick_id TEXT,
    working_memory JSONB DEFAULT '{}'::jsonb,
    pending_actions JSONB DEFAULT '[]'::jsonb,
    health_status TEXT DEFAULT 'ok',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_state_snapshot_agent
    ON agent_state_snapshot (agent_name);

COMMENT ON TABLE agent_state_snapshot IS
    'Persistent state for the autonomous reasoning loop. Survives process '
    'restarts so the daemon resumes where it left off.';

-- ============================================================
-- END OF MIGRATION 008
-- ============================================================
