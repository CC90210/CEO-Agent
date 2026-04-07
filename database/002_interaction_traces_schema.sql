-- ============================================================
-- BRAVO V5.5 — Interaction Traces & Self-Modification Schema
-- Migration 002: Adds observability and self-evolution tables
-- Apply via Supabase MCP: apply_migration
-- ============================================================

-- ============================================================
-- 1. AGENT TRACES — Every meaningful action logged
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_traces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_interface TEXT NOT NULL CHECK (agent_interface IN ('claude_code', 'anti_gravity', 'blackbox', 'telegram', 'n8n')),
    event_type TEXT NOT NULL CHECK (event_type IN ('task_start', 'task_complete', 'task_fail', 'tool_call', 'decision', 'error', 'self_modify', 'memory_write', 'heartbeat', 'brain_loop_step')),
    event_name TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    duration_ms INTEGER,
    confidence DECIMAL(3,2) CHECK (confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'fail', 'partial', 'skipped')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_traces_trace_id ON agent_traces(trace_id);
CREATE INDEX idx_traces_timestamp ON agent_traces(timestamp DESC);
CREATE INDEX idx_traces_event_type ON agent_traces(event_type);
CREATE INDEX idx_traces_interface ON agent_traces(agent_interface);
CREATE INDEX idx_traces_status ON agent_traces(status);

-- ============================================================
-- 2. SELF-MODIFICATION LOG — Audit trail for agent self-edits
-- ============================================================
CREATE TABLE IF NOT EXISTS self_modification_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_path TEXT NOT NULL,
    section_modified TEXT,
    change_type TEXT NOT NULL CHECK (change_type IN ('create', 'update', 'delete', 'propose')),
    old_content_summary TEXT,
    new_content_summary TEXT,
    reason TEXT NOT NULL,
    evidence TEXT,
    confidence DECIMAL(3,2) DEFAULT 0.80 CHECK (confidence BETWEEN 0 AND 1),
    governance_tier TEXT NOT NULL CHECK (governance_tier IN ('immutable', 'semi_mutable', 'governed_mutable', 'freely_mutable', 'ephemeral')),
    approval_status TEXT NOT NULL DEFAULT 'auto_approved' CHECK (approval_status IN ('auto_approved', 'pending_approval', 'approved', 'rejected', 'rolled_back')),
    rollback_commit TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_selfmod_file ON self_modification_log(file_path);
CREATE INDEX idx_selfmod_type ON self_modification_log(change_type);
CREATE INDEX idx_selfmod_date ON self_modification_log(created_at DESC);

-- ============================================================
-- 3. PERFORMANCE METRICS — Aggregated daily metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,
    agent_interface TEXT NOT NULL,
    tasks_attempted INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    tool_calls_total INTEGER DEFAULT 0,
    tool_calls_failed INTEGER DEFAULT 0,
    avg_confidence DECIMAL(3,2),
    avg_task_duration_ms INTEGER,
    mistakes_logged INTEGER DEFAULT 0,
    patterns_logged INTEGER DEFAULT 0,
    sops_created INTEGER DEFAULT 0,
    self_modifications INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(metric_date, agent_interface)
);

CREATE INDEX idx_metrics_date ON performance_metrics(metric_date DESC);

-- ============================================================
-- 4. SKILL ACTIVATION — Track memory/skill access patterns
-- ============================================================
CREATE TABLE IF NOT EXISTS skill_activation (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_type TEXT NOT NULL CHECK (item_type IN ('memory', 'pattern', 'mistake', 'sop', 'skill', 'fact')),
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    access_count INTEGER DEFAULT 1,
    last_accessed TIMESTAMPTZ DEFAULT NOW(),
    first_accessed TIMESTAMPTZ DEFAULT NOW(),
    activation_score DECIMAL(5,4) DEFAULT 0.5000,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'probationary', 'validated', 'under_review', 'archived')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(item_type, item_id)
);

CREATE INDEX idx_activation_score ON skill_activation(activation_score DESC);
CREATE INDEX idx_activation_status ON skill_activation(status);

-- ============================================================
-- 5. HELPER FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION calculate_activation_score(
    p_access_count INTEGER,
    p_last_accessed TIMESTAMPTZ,
    p_confidence DECIMAL DEFAULT 0.80
) RETURNS DECIMAL AS $$
DECLARE
    recency_score DECIMAL;
    frequency_score DECIMAL;
    age_days DECIMAL;
BEGIN
    age_days := EXTRACT(EPOCH FROM (NOW() - p_last_accessed)) / 86400.0;
    recency_score := GREATEST(0, 1.0 - (age_days / 30.0));
    frequency_score := LEAST(1.0, p_access_count::DECIMAL / 20.0);
    RETURN (recency_score * 0.3) + (frequency_score * 0.4) + (p_confidence * 0.3);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refresh_activation_scores()
RETURNS INTEGER AS $$
DECLARE
    affected_count INTEGER;
BEGIN
    UPDATE skill_activation
    SET activation_score = calculate_activation_score(access_count, last_accessed),
        updated_at = NOW();
    GET DIAGNOSTICS affected_count = ROW_COUNT;
    RETURN affected_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION log_trace(
    p_trace_id TEXT,
    p_span_id TEXT,
    p_agent_interface TEXT,
    p_event_type TEXT,
    p_event_name TEXT,
    p_status TEXT DEFAULT 'success',
    p_input_summary TEXT DEFAULT NULL,
    p_output_summary TEXT DEFAULT NULL,
    p_duration_ms INTEGER DEFAULT NULL,
    p_confidence DECIMAL DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS UUID AS $$
DECLARE
    new_id UUID;
BEGIN
    INSERT INTO agent_traces (trace_id, span_id, agent_interface, event_type, event_name, status, input_summary, output_summary, duration_ms, confidence, metadata)
    VALUES (p_trace_id, p_span_id, p_agent_interface, p_event_type, p_event_name, p_status, p_input_summary, p_output_summary, p_duration_ms, p_confidence, p_metadata)
    RETURNING id INTO new_id;
    RETURN new_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- RLS POLICIES
-- ============================================================
ALTER TABLE agent_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE self_modification_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_activation ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON agent_traces FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON self_modification_log FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON performance_metrics FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON skill_activation FOR ALL USING (TRUE) WITH CHECK (TRUE);
