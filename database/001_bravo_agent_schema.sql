-- ============================================================
-- BRAVO V5.0 — Agent Intelligence Database Schema
-- Apply via Supabase MCP: apply_migration
-- ============================================================
-- This schema powers Bravo's persistent cross-session intelligence.
-- Files remain the source of truth; Supabase is the queryable index.
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- ============================================================
-- 1. AGENT STATE — Current operational state (single row)
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_state (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    confidence_level DECIMAL(3,2) DEFAULT 0.80 CHECK (confidence_level BETWEEN 0 AND 1),
    focus_area TEXT DEFAULT 'general',
    energy_level TEXT DEFAULT 'HIGH' CHECK (energy_level IN ('HIGH', 'MEDIUM', 'LOW', 'CRITICAL')),
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    active_goals JSONB DEFAULT '[]'::jsonb,
    known_issues JSONB DEFAULT '[]'::jsonb,
    system_health JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial state
INSERT INTO agent_state (confidence_level, focus_area, energy_level, active_goals, system_health)
VALUES (
    0.80,
    'architecture',
    'HIGH',
    '["Implement V5.0 brain architecture", "Configure Supabase persistence", "Build content pipeline"]'::jsonb,
    '{"git": "ok", "workspace": "clean", "mcp_playwright": "ok", "mcp_context7": "ok", "mcp_memory": "ok", "mcp_n8n": "ok", "mcp_late": "patched", "mcp_supabase": "token_pending", "mcp_seq_thinking": "ok"}'::jsonb
);

-- ============================================================
-- 2. MEMORIES — All memories with confidence scoring
-- ============================================================
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category TEXT NOT NULL CHECK (category IN ('decision', 'mistake', 'pattern', 'insight', 'fact', 'preference', 'capability')),
    content TEXT NOT NULL,
    confidence_score DECIMAL(3,2) DEFAULT 0.50 CHECK (confidence_score BETWEEN 0 AND 1),
    source TEXT DEFAULT 'observed' CHECK (source IN ('observed', 'inferred', 'told', 'tested', 'assumed')),
    tags TEXT[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_confidence ON memories(confidence_score DESC);
CREATE INDEX idx_memories_tags ON memories USING GIN(tags);
CREATE INDEX idx_memories_content_search ON memories USING GIN(content gin_trgm_ops);

-- ============================================================
-- 3. SESSION LOGS — Session history across all agent interfaces
-- ============================================================
CREATE TABLE IF NOT EXISTS session_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_date DATE NOT NULL DEFAULT CURRENT_DATE,
    agent_interface TEXT NOT NULL CHECK (agent_interface IN ('claude_code', 'anti_gravity', 'blackbox', 'telegram', 'n8n')),
    summary TEXT NOT NULL,
    tasks_completed TEXT[] DEFAULT '{}',
    tasks_failed TEXT[] DEFAULT '{}',
    tasks_blocked TEXT[] DEFAULT '{}',
    insights TEXT[] DEFAULT '{}',
    duration_minutes INTEGER,
    tool_calls_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_session_logs_date ON session_logs(session_date DESC);
CREATE INDEX idx_session_logs_interface ON session_logs(agent_interface);

-- ============================================================
-- 4. DAILY LOGS — Daily activity and emotional state tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    log_date DATE NOT NULL UNIQUE DEFAULT CURRENT_DATE,
    activities JSONB DEFAULT '[]'::jsonb,
    learnings JSONB DEFAULT '[]'::jsonb,
    emotional_state JSONB DEFAULT '{"confidence": 0.8, "focus": "general", "energy": "HIGH"}'::jsonb,
    goals_progress JSONB DEFAULT '{}'::jsonb,
    sessions_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_daily_logs_date ON daily_logs(log_date DESC);

-- ============================================================
-- 5. SOPS — Standard Operating Procedures with tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS sops (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sop_id TEXT UNIQUE NOT NULL,  -- e.g., 'SOP-001'
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL CHECK (category IN ('content', 'code', 'deploy', 'research', 'automation', 'admin', 'client', 'finance')),
    trigger_conditions TEXT NOT NULL,
    prerequisites TEXT,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    success_criteria TEXT,
    failure_handling TEXT,
    owner TEXT DEFAULT 'bravo',
    execution_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_executed TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sops_category ON sops(category);
CREATE INDEX idx_sops_active ON sops(is_active);

-- ============================================================
-- 6. SKILLS REGISTRY — Usage tracking for all skills
-- ============================================================
CREATE TABLE IF NOT EXISTS skills_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    skill_name TEXT UNIQUE NOT NULL,
    skill_path TEXT NOT NULL,
    description TEXT,
    category TEXT,
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_used TIMESTAMPTZ,
    dependencies TEXT[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skills_name ON skills_registry(skill_name);

-- ============================================================
-- 7. SELF-HEALING LOG — Recovery event tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS self_healing_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 4),
    dimension TEXT NOT NULL CHECK (dimension IN ('memory', 'context', 'skill', 'infrastructure', 'relationship')),
    trigger_event TEXT NOT NULL,
    diagnosis TEXT,
    action_taken TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('resolved', 'escalated', 'failed', 'deferred')),
    duration_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_healing_tier ON self_healing_log(tier);
CREATE INDEX idx_healing_dimension ON self_healing_log(dimension);
CREATE INDEX idx_healing_date ON self_healing_log(created_at DESC);

-- ============================================================
-- 8. GROWTH LOG — Learning and capability evolution
-- ============================================================
CREATE TABLE IF NOT EXISTS growth_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category TEXT NOT NULL CHECK (category IN ('skill_acquired', 'pattern_learned', 'mistake_corrected', 'capability_expanded', 'sop_created', 'integration_added')),
    description TEXT NOT NULL,
    evidence TEXT,
    confidence_score DECIMAL(3,2) DEFAULT 0.80 CHECK (confidence_score BETWEEN 0 AND 1),
    impact TEXT CHECK (impact IN ('high', 'medium', 'low')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_growth_category ON growth_log(category);
CREATE INDEX idx_growth_date ON growth_log(created_at DESC);

-- ============================================================
-- 9. HEARTBEAT TASKS — Proactive task registry
-- ============================================================
CREATE TABLE IF NOT EXISTS heartbeat_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_name TEXT NOT NULL,
    description TEXT,
    schedule_interval TEXT NOT NULL,  -- e.g., '30m', '6h', '24h', 'session_start', 'session_end'
    conditions JSONB DEFAULT '{}'::jsonb,
    action_template TEXT NOT NULL,
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    is_active BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    run_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_heartbeat_active ON heartbeat_tasks(is_active);
CREATE INDEX idx_heartbeat_next ON heartbeat_tasks(next_run);

-- Seed default heartbeat tasks
INSERT INTO heartbeat_tasks (task_name, description, schedule_interval, action_template, priority) VALUES
('memory_consistency_check', 'Verify memory files have no contradictions', 'session_start', 'Read ACTIVE_TASKS.md and SESSION_LOG.md. Flag stale items.', 'high'),
('infrastructure_health', 'Check MCP servers and git status', 'session_start', 'Run git status. Note any MCP failures from last session.', 'high'),
('workspace_cleanup', 'Scan for junk files in project root', 'session_start', 'Check for *.js, *.txt, *.log, debug dumps. Auto-clean trivial junk.', 'medium'),
('memory_bloat_check', 'Check memory file sizes', '24h', 'SESSION_LOG < 200 lines, ACTIVE_TASKS < 50 items. Compress if needed.', 'medium'),
('confidence_decay', 'Decay confidence on unverified facts', '7d', 'Review LONG_TERM.md. Reduce confidence on facts not verified in 30+ days.', 'low'),
('content_calendar_check', 'Check if posts are scheduled for today', '24h', 'Query Late MCP for scheduled posts. Alert CC if none today.', 'low');

-- ============================================================
-- 10. USER CONTEXT — CC's profile and preferences (queryable)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_context (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('identity', 'business', 'preference', 'weakness', 'strength', 'goal', 'content_pillar')),
    confidence_score DECIMAL(3,2) DEFAULT 0.90,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(key, category)
);

CREATE INDEX idx_user_context_category ON user_context(category);

-- Seed CC's core context
INSERT INTO user_context (key, value, category, confidence_score) VALUES
('name', 'Conaugh McKenna (CC)', 'identity', 0.99),
('age', '22', 'identity', 0.95),
('location', 'Collingwood, Ontario, Canada', 'identity', 0.95),
('primary_objective', 'Make as much money as possible through aggressive revenue generation', 'goal', 0.99),
('oasis_ai', 'OASIS AI Solutions — AI Automation Agency, $8-12K MRR, 10+ clients', 'business', 0.90),
('propflow', 'PropFlow — Real Estate SaaS (Next.js, Supabase, Stripe), pre-revenue', 'business', 0.85),
('nostalgic_requests', 'Nostalgic Requests — Song request platform (Stripe Connect)', 'business', 0.85),
('weakness_followthrough', 'Struggles with follow-through and task completion', 'weakness', 0.95),
('weakness_consistency', 'Struggles with consistency and persistence', 'weakness', 0.95),
('weakness_conviction', 'Struggles with conviction in own output and value', 'weakness', 0.90),
('weakness_organization', 'Struggles with direction, structure, daily organization', 'weakness', 0.95),
('pillar_builder', 'The Builder: OASIS, PropFlow, automations, shipping product', 'content_pillar', 0.95),
('pillar_outsider', 'The Outsider: Multi-country living, not fitting boxes', 'content_pillar', 0.95),
('pillar_dj', 'The DJ: Music, sets, gig booking, audio culture', 'content_pillar', 0.95),
('pillar_transformer', 'The Transformer: Discipline, personal evolution', 'content_pillar', 0.95),
('pillar_hustler', 'The Hustler: Working at Nickys while building a company', 'content_pillar', 0.95),
('pref_address', 'Address as CC, not CeCe', 'preference', 0.99),
('pref_communication', 'Direct, no filler, no corporate jargon', 'preference', 0.99),
('pref_git', 'Prefers remote git ops (saves disk, auto Vercel preview)', 'preference', 0.90),
('pref_confirmation', 'Confirm before destructive ops (Stripe, DB, deploys)', 'preference', 0.99);

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Function to search memories by text (fuzzy)
CREATE OR REPLACE FUNCTION search_memories(query_text TEXT, min_confidence DECIMAL DEFAULT 0.5, max_results INTEGER DEFAULT 10)
RETURNS TABLE(id UUID, category TEXT, content TEXT, confidence_score DECIMAL, tags TEXT[], similarity REAL) AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.category, m.content, m.confidence_score, m.tags,
           similarity(m.content, query_text) AS sim
    FROM memories m
    WHERE m.is_active = TRUE
      AND m.confidence_score >= min_confidence
      AND (m.content ILIKE '%' || query_text || '%' OR similarity(m.content, query_text) > 0.1)
    ORDER BY sim DESC, m.confidence_score DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Function to decay confidence scores
CREATE OR REPLACE FUNCTION decay_confidence_scores(days_threshold INTEGER DEFAULT 30, decay_amount DECIMAL DEFAULT 0.1)
RETURNS INTEGER AS $$
DECLARE
    affected_count INTEGER;
BEGIN
    UPDATE memories
    SET confidence_score = GREATEST(0.0, confidence_score - decay_amount),
        updated_at = NOW()
    WHERE is_active = TRUE
      AND last_accessed < NOW() - (days_threshold || ' days')::INTERVAL
      AND confidence_score > 0.0;
    GET DIAGNOSTICS affected_count = ROW_COUNT;
    RETURN affected_count;
END;
$$ LANGUAGE plpgsql;

-- Function to log a self-healing event
CREATE OR REPLACE FUNCTION log_healing_event(
    p_tier INTEGER,
    p_dimension TEXT,
    p_trigger TEXT,
    p_diagnosis TEXT,
    p_action TEXT,
    p_outcome TEXT,
    p_duration INTEGER DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    new_id UUID;
BEGIN
    INSERT INTO self_healing_log (tier, dimension, trigger_event, diagnosis, action_taken, outcome, duration_seconds)
    VALUES (p_tier, p_dimension, p_trigger, p_diagnosis, p_action, p_outcome, p_duration)
    RETURNING id INTO new_id;
    RETURN new_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================
-- Enable RLS on all tables (Supabase best practice)
ALTER TABLE agent_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sops ENABLE ROW LEVEL SECURITY;
ALTER TABLE skills_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE self_healing_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE growth_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE heartbeat_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_context ENABLE ROW LEVEL SECURITY;

-- Service role has full access (agent uses service key)
CREATE POLICY "Service role full access" ON agent_state FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON memories FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON session_logs FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON daily_logs FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON sops FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON skills_registry FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON self_healing_log FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON growth_log FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON heartbeat_tasks FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "Service role full access" ON user_context FOR ALL USING (TRUE) WITH CHECK (TRUE);
