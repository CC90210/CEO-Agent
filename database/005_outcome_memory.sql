-- ============================================================
-- BRAVO V5.6.1 — Migration 005: Outcome Memory
-- Apply via: python scripts/apply_migration.py database/005_outcome_memory.sql
-- ============================================================
-- PURPOSE
-- Closes the feedback loop. Before this migration every outbound was a
-- one-way street — the system never asked "did that work?" The two tables
-- below power compound learning: reply rates per template, per vertical,
-- per relationship stage; winning subject-line signals; time-of-day
-- effectiveness; per-agent-source performance.
-- Populated by scripts/outcome_tracker.py (weekly aggregation + live
-- reply correlation).
-- ============================================================

-- 1. template_performance ------------------------------------------------------
-- One row per (template_identity, vertical, stage) triple. Aggregated from
-- lead_interactions + reply correlations on a rolling basis.
CREATE TABLE IF NOT EXISTS template_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_identity TEXT NOT NULL,
    vertical TEXT,
    relationship_stage TEXT,
    brand TEXT,
    sends_total INTEGER DEFAULT 0,
    replies_total INTEGER DEFAULT 0,
    positive_replies INTEGER DEFAULT 0,
    negative_replies INTEGER DEFAULT 0,
    meetings_booked INTEGER DEFAULT 0,
    deals_closed INTEGER DEFAULT 0,
    revenue_attributed_cents BIGINT DEFAULT 0,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    last_computed_at TIMESTAMPTZ DEFAULT NOW(),
    score_30d NUMERIC(6,4),
    score_overall NUMERIC(6,4),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(template_identity, vertical, relationship_stage, brand)
);

CREATE INDEX IF NOT EXISTS idx_template_perf_template
    ON template_performance (template_identity);
CREATE INDEX IF NOT EXISTS idx_template_perf_score
    ON template_performance (vertical, relationship_stage, score_30d DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_template_perf_last_seen
    ON template_performance (last_seen DESC);

COMMENT ON TABLE template_performance IS
    'Aggregated outcome stats keyed on (template, vertical, stage). '
    'Scored weekly by outcome_tracker.py. Consumed by context_builder '
    'and outreach_batch to pick winning copy.';

-- 2. vertical_response_patterns -----------------------------------------------
-- What SIGNAL (subject-line cue, opening-line pattern, persona tone)
-- correlates with reply in which vertical. Filled in by outcome_tracker's
-- pattern miner.
CREATE TABLE IF NOT EXISTS vertical_response_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vertical TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_value TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    sample_size INTEGER DEFAULT 0,
    confidence NUMERIC(4,3),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    UNIQUE(vertical, signal_type, signal_value)
);

CREATE INDEX IF NOT EXISTS idx_vpat_vertical
    ON vertical_response_patterns (vertical, signal_type);
CREATE INDEX IF NOT EXISTS idx_vpat_confidence
    ON vertical_response_patterns (vertical, confidence DESC NULLS LAST);

COMMENT ON TABLE vertical_response_patterns IS
    'Mined patterns: which signals in a message correlate with reply in '
    'a given vertical. Signal types: subject_cue, opener_pattern, '
    'persona_tone, time_of_day, day_of_week, length_bracket.';

-- 3. Outbound-to-reply correlation helper view -------------------------------
-- Convenience view outcome_tracker uses to find unreplied outbounds older
-- than cooldown window, to close them as "no reply" outcomes.
CREATE OR REPLACE VIEW lead_interactions_unreplied_outbound AS
SELECT
    o.id AS outbound_id,
    o.lead_id,
    o.channel,
    o.created_at AS sent_at,
    o.subject,
    o.agent_source,
    o.metadata,
    EXTRACT(EPOCH FROM (NOW() - o.created_at))/3600.0 AS hours_since_send
FROM lead_interactions o
WHERE o.type IN ('email_sent', 'dm_sent', 'linkedin_sent')
  AND NOT EXISTS (
      SELECT 1 FROM lead_interactions r
      WHERE r.lead_id = o.lead_id
        AND r.channel = o.channel
        AND r.created_at > o.created_at
        AND (r.type LIKE '%_received' OR r.type LIKE '%_reply')
  );

COMMENT ON VIEW lead_interactions_unreplied_outbound IS
    'Outbound actions with no inbound follow-up on the same channel. '
    'outcome_tracker closes rows older than 14 days as no-reply outcomes.';

-- ============================================================
-- END OF MIGRATION 005
-- ============================================================
