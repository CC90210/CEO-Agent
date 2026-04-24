-- ============================================================
-- BRAVO V5.6.1 — Migration 006: Event Bus
-- Apply via: python scripts/apply_migration.py database/006_event_bus.sql
-- ============================================================
-- PURPOSE
-- Coordination fabric for the C-Suite (Atlas = CFO, Bravo = CEO,
-- Maven = CMO). Before this migration agents polled each other's
-- pulse files — cadence was "whoever reads next." After this they
-- publish typed events and subscribe to Supabase Realtime.
--
-- Event publishers: any agent via scripts/event_bus.py::publish()
-- Event consumers:  any agent via scripts/event_bus.py::subscribe()
-- Bravo subscribes to budget_gate, campaign_launched, deal_closed, etc.
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type TEXT NOT NULL,
    publisher_agent TEXT NOT NULL,
    target_agent TEXT,
    severity TEXT NOT NULL DEFAULT 'info'
        CHECK (severity IN ('info', 'warn', 'error', 'critical')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    correlation_id TEXT,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consumed_by TEXT[] DEFAULT ARRAY[]::TEXT[],
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_events_type
    ON agent_events (event_type, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_events_target
    ON agent_events (target_agent, published_at DESC)
    WHERE target_agent IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_events_unconsumed
    ON agent_events (event_type, published_at DESC)
    WHERE consumed_by = ARRAY[]::TEXT[] OR consumed_by IS NULL;
CREATE INDEX IF NOT EXISTS idx_agent_events_correlation
    ON agent_events (correlation_id)
    WHERE correlation_id IS NOT NULL;

COMMENT ON TABLE agent_events IS
    'Pub-sub event bus for cross-agent coordination. Published by Atlas, '
    'Bravo, Maven, Aura. Consumed via Supabase Realtime subscriptions or '
    'pull-based reads. TTL via expires_at — events without expiry live '
    'until the weekly prune job archives them.';

-- Turn on Realtime for agent_events so subscribers receive live pushes.
-- NOTE: Supabase Realtime publication is managed at the project level;
-- if this statement fails because the publication doesn't exist, the
-- migration still succeeds — subscribers just fall back to polling.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE agent_events;
        EXCEPTION WHEN duplicate_object THEN
            NULL;  -- already in the publication
        END;
    END IF;
END $$;

-- Helper: claim an event as consumed by an agent (idempotent append).
CREATE OR REPLACE FUNCTION mark_event_consumed(p_event_id UUID, p_agent TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    already BOOLEAN;
BEGIN
    SELECT p_agent = ANY(consumed_by) INTO already
    FROM agent_events WHERE id = p_event_id;

    IF already IS TRUE THEN RETURN FALSE; END IF;

    UPDATE agent_events
    SET consumed_by = array_append(consumed_by, p_agent)
    WHERE id = p_event_id;
    RETURN TRUE;
END $$;

COMMENT ON FUNCTION mark_event_consumed(UUID, TEXT) IS
    'Record that agent X has handled event Y. Idempotent — returns '
    'FALSE if agent was already in consumed_by.';

-- ============================================================
-- END OF MIGRATION 006
-- ============================================================
