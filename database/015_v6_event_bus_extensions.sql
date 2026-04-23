-- ============================================================
-- BRAVO V6.0 — Migration 015: Event Bus Extensions (LISTEN/NOTIFY + durability)
-- Apply via: python scripts/apply_migration.py database/015_v6_event_bus_extensions.sql
-- ============================================================
-- PURPOSE
-- V5.7 cross-agent communication was pulse-JSON files (ceo_pulse.json,
-- cfo_pulse.json, cmo_pulse.json) — race-prone, not thread-safe.
-- Migration 006 added `agent_events` for durable pub/sub but publishers still
-- have to poll. V6.0 layers LISTEN/NOTIFY on top so subscribers get push
-- semantics without standing up Redis, AND adds the idempotency + state
-- columns needed for a concurrent-safe work queue (FOR UPDATE SKIP LOCKED).
--
-- Consumers:
--   - scripts/event_bus.py::publish()     — writes INSERT, trigger NOTIFYs
--   - scripts/event_bus.py::subscribe()   — LISTEN on channel + claim rows
--   - scripts/event_drain.py              — offline-queue replay
-- ============================================================

-- ---- Extend agent_events (from migration 006) ------------------------------

ALTER TABLE agent_events
    ADD COLUMN IF NOT EXISTS source_agent     TEXT        NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS idempotency_key  TEXT,
    ADD COLUMN IF NOT EXISTS status           TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processing','done','failed','dead')),
    ADD COLUMN IF NOT EXISTS processed_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS processed_by     TEXT,
    ADD COLUMN IF NOT EXISTS retry_count      INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_error       TEXT,
    ADD COLUMN IF NOT EXISTS visibility_until TIMESTAMPTZ;

-- Backfill source_agent from publisher_agent (migration 006 column) if anyone
-- inserted under the old name. Belt-and-braces: subscribers look at source_agent.
UPDATE agent_events
SET    source_agent = publisher_agent
WHERE  source_agent = 'unknown' AND publisher_agent IS NOT NULL;

-- Unique idempotency guard — a publisher passing the same key twice is a no-op.
-- NULL values allowed (not every event needs idempotency).
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_events_idem
    ON agent_events (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Hot path: subscribers claim pending rows for their target channel.
CREATE INDEX IF NOT EXISTS idx_agent_events_target_pending
    ON agent_events (target_agent, status, published_at)
    WHERE status = 'pending';

-- Broadcast channel (target_agent IS NULL).
CREATE INDEX IF NOT EXISTS idx_agent_events_broadcast_pending
    ON agent_events (status, published_at)
    WHERE status = 'pending' AND target_agent IS NULL;

-- ---- LISTEN/NOTIFY trigger -------------------------------------------------
-- Push a lightweight JSON payload on INSERT so subscribers wake immediately.
-- Payload is capped (Postgres NOTIFY limit is ~8kB); full row still lives
-- in the table and subscribers fetch the details via SELECT.

CREATE OR REPLACE FUNCTION notify_agent_event() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    channel TEXT;
    payload TEXT;
BEGIN
    channel := COALESCE(NEW.target_agent, 'broadcast');
    payload := json_build_object(
        'id',            NEW.id,
        'type',          NEW.event_type,
        'source',        NEW.source_agent,
        'target',        NEW.target_agent,
        'severity',      NEW.severity,
        'correlation',   NEW.correlation_id,
        'published_at',  NEW.published_at
    )::TEXT;
    PERFORM pg_notify(channel, payload);
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_notify_agent_event ON agent_events;
CREATE TRIGGER trg_notify_agent_event
    AFTER INSERT ON agent_events
    FOR EACH ROW EXECUTE FUNCTION notify_agent_event();

COMMENT ON FUNCTION notify_agent_event() IS
    'V6.0 LISTEN/NOTIFY trigger. Subscribers with LISTEN on target_agent name '
    '(or "broadcast" if target_agent is NULL) wake immediately on new events.';

-- ---- Claim function (atomic dequeue for subscribers) -----------------------
-- Subscribers call claim_events(my_agent, max_n) which atomically picks up
-- to N pending rows targeted at them (or broadcast), marks them processing,
-- and stamps a visibility timeout. FOR UPDATE SKIP LOCKED means concurrent
-- workers of the same agent never touch the same row.

CREATE OR REPLACE FUNCTION claim_events(
    p_agent              TEXT,
    p_max                INT  DEFAULT 10,
    p_visibility_seconds INT  DEFAULT 30
) RETURNS SETOF agent_events LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    UPDATE agent_events e
    SET    status           = 'processing',
           processed_by     = p_agent,
           visibility_until = NOW() + (p_visibility_seconds || ' seconds')::INTERVAL
    WHERE  e.id IN (
        SELECT e2.id
        FROM   agent_events e2
        WHERE  e2.status = 'pending'
          AND  (e2.target_agent = p_agent OR e2.target_agent IS NULL)
          AND  (e2.visibility_until IS NULL OR e2.visibility_until <= NOW())
        ORDER BY e2.published_at
        LIMIT p_max
        FOR UPDATE SKIP LOCKED
    )
    RETURNING e.*;
END $$;

COMMENT ON FUNCTION claim_events IS
    'V6.0 concurrent-safe dequeue. Multiple workers of the same agent name '
    'will never claim the same row thanks to FOR UPDATE SKIP LOCKED.';

-- ---- Ack / fail helpers ----------------------------------------------------

CREATE OR REPLACE FUNCTION ack_event(p_event_id UUID, p_agent TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
BEGIN
    UPDATE agent_events
    SET    status = 'done',
           processed_at = NOW(),
           processed_by = p_agent
    WHERE  id = p_event_id
      AND  status IN ('processing', 'pending');
    RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION fail_event(
    p_event_id UUID,
    p_agent    TEXT,
    p_error    TEXT,
    p_max_retries INT DEFAULT 3
) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    new_count INT;
    new_status TEXT;
BEGIN
    UPDATE agent_events
    SET    retry_count = retry_count + 1,
           last_error  = p_error,
           processed_by = p_agent
    WHERE  id = p_event_id
    RETURNING retry_count INTO new_count;

    IF new_count >= p_max_retries THEN
        new_status := 'dead';
    ELSE
        new_status := 'pending';   -- re-available for another worker
    END IF;

    UPDATE agent_events
    SET    status = new_status,
           visibility_until = NULL
    WHERE  id = p_event_id;

    RETURN new_status;
END $$;

COMMENT ON FUNCTION fail_event IS
    'V6.0 failure handling. After N retries rows are marked dead and an '
    'operator must manually unstick them (or a reaper job archives them).';

-- ---- Recover stuck rows ----------------------------------------------------
-- Call this periodically (cron or scheduler). Any row with
-- status=processing AND visibility_until <= NOW() gets knocked back to
-- pending so another worker can try.

CREATE OR REPLACE FUNCTION reap_stuck_events() RETURNS INT LANGUAGE plpgsql AS $$
DECLARE n INT;
BEGIN
    WITH reaped AS (
        UPDATE agent_events
        SET    status = 'pending',
               visibility_until = NULL,
               retry_count = retry_count + 1,
               last_error = COALESCE(last_error, '') || ' | visibility-timeout-reaped'
        WHERE  status = 'processing'
          AND  visibility_until <= NOW()
        RETURNING id
    )
    SELECT COUNT(*) INTO n FROM reaped;
    RETURN n;
END $$;

-- ============================================================
-- END OF MIGRATION 015
-- ============================================================
