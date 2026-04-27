-- ============================================================
-- BRAVO V5.6.1 — Migration 012: N8N Inbound → Unified Ledger RPC
-- Apply via: python scripts/apply_migration.py database/012_inbound_rpc.sql
-- ============================================================
-- PURPOSE
-- Close the last writer blind spot. Before this migration, the N8N
-- `OASIS Inbound Qualifier (Bravo Aware)` workflow (ID 1cGIN32alM8sf8OV)
-- classified inbound emails in the cloud but wrote nothing to
-- `lead_interactions`. That meant Bravo and the V5.6 send gateway had
-- no memory of inbound, and cooldown logic couldn't know "this lead
-- already replied — back off."
--
-- This migration adds ONE RPC function that CC's N8N workflow calls
-- via a single Supabase node (see docs/N8N_INBOUND_INTEGRATION.md for
-- the paste-in config). The function does three things atomically:
--   1. Upsert the sender into `leads` (create if new, update
--      last_contacted_at if existing).
--   2. Insert a row into `lead_interactions` with
--      agent_source='n8n_inbound'.
--   3. Publish an `inbound.classified` event on `agent_events` so
--      the autonomous reasoning loop (Build #3) can react in real time.
--
-- DESIGN DECISIONS
-- 1. Single function, single network hop. N8N does one call, everything
--    lands where it needs to be. Partial-failure mode is impossible —
--    either all three writes succeed or the transaction rolls back.
-- 2. Accepts whatever shape N8N's classifier produces. The classification
--    parameter is JSONB — we don't constrain keys. Bravo's consumers
--    (context_builder, autonomous agent) look for specific keys
--    (sentiment, intent, priority, suggested_action) but gracefully
--    degrade when they're missing.
-- 3. Lead auto-create on first inbound. Matches the gateway's
--    auto-create pattern (resolve_lead_id) so the graph stays consistent
--    regardless of whether the first touch was inbound or outbound.
-- 4. Server-side email normalization. N8N workflows vary in how they
--    clean email addresses; we normalize once here (lowercase, trim)
--    so downstream code never sees "Jane@Acme.com" and "jane@acme.com"
--    as two different leads.
-- ============================================================

CREATE OR REPLACE FUNCTION record_inbound_from_n8n(
    p_from_email      TEXT,
    p_from_name       TEXT        DEFAULT NULL,
    p_subject         TEXT        DEFAULT NULL,
    p_content         TEXT        DEFAULT NULL,
    p_classification  JSONB       DEFAULT '{}'::jsonb,
    p_thread_id       TEXT        DEFAULT NULL,
    p_message_id      TEXT        DEFAULT NULL,
    p_received_at     TIMESTAMPTZ DEFAULT NOW()
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_email        TEXT;
    v_name         TEXT;
    v_lead_id      UUID;
    v_lead_was_new BOOLEAN := FALSE;
    v_interaction_id UUID;
    v_event_id     UUID;
    v_severity     TEXT;
    v_priority     TEXT;
    v_intent       TEXT;
    v_now          TIMESTAMPTZ := COALESCE(p_received_at, NOW());
BEGIN
    -- Normalize email (lowercase, trim). Refuse empty — nothing to log.
    v_email := lower(trim(COALESCE(p_from_email, '')));
    IF v_email = '' OR position('@' in v_email) = 0 THEN
        RAISE EXCEPTION 'record_inbound_from_n8n: from_email is required and must look like an email';
    END IF;

    -- Derive a placeholder name from the email local-part if none given.
    v_name := COALESCE(NULLIF(trim(p_from_name), ''), split_part(v_email, '@', 1));

    -- 1. Upsert the lead by email.
    SELECT id INTO v_lead_id FROM leads WHERE email = v_email LIMIT 1;

    IF v_lead_id IS NULL THEN
        INSERT INTO leads (name, email, status, source, created_at, updated_at, last_contacted_at)
        VALUES (v_name, v_email, 'new', 'inbound_n8n', v_now, v_now, v_now)
        RETURNING id INTO v_lead_id;
        v_lead_was_new := TRUE;
    ELSE
        -- Keep last_contacted_at fresh so CRM views show them as active.
        UPDATE leads
        SET last_contacted_at = v_now,
            updated_at        = v_now
        WHERE id = v_lead_id;
    END IF;

    -- 2. Insert the interaction row.
    INSERT INTO lead_interactions (
        lead_id, type, channel, subject, content, agent_source, metadata, created_at
    )
    VALUES (
        v_lead_id,
        'email_received',
        'email',
        NULLIF(trim(COALESCE(p_subject, '')), ''),
        left(COALESCE(p_content, ''), 2000),
        'n8n_inbound',
        jsonb_build_object(
            'from_identity',   v_email,
            'from_name',       p_from_name,
            'thread_id',       p_thread_id,
            'message_id',      p_message_id,
            'received_at',     v_now,
            'classification',  COALESCE(p_classification, '{}'::jsonb),
            'source_workflow', 'oasis_inbound_qualifier'
        ),
        v_now
    )
    RETURNING id INTO v_interaction_id;

    -- 3. Publish an event on the bus. Severity lifts on hot/unsub cues so
    --    Telegram digests and the dashboard flag them appropriately.
    v_priority := COALESCE(p_classification ->> 'priority', 'unknown');
    v_intent   := COALESCE(p_classification ->> 'intent',   'unknown');
    v_severity := CASE
        WHEN v_priority = 'hot' THEN 'warn'
        WHEN v_intent   = 'unsubscribe' THEN 'warn'
        WHEN v_intent   = 'objection'   THEN 'warn'
        WHEN v_intent   = 'booking'     THEN 'warn'
        ELSE 'info'
    END;

    INSERT INTO agent_events (
        event_type, publisher_agent, severity, payload, correlation_id, published_at
    )
    VALUES (
        'inbound.classified',
        'n8n',
        v_severity,
        jsonb_build_object(
            'interaction_id', v_interaction_id,
            'lead_id',        v_lead_id,
            'lead_was_new',   v_lead_was_new,
            'from_identity',  v_email,
            'from_name',      p_from_name,
            'subject',        p_subject,
            'thread_id',      p_thread_id,
            'message_id',     p_message_id,
            'classification', COALESCE(p_classification, '{}'::jsonb)
        ),
        v_interaction_id::text,
        v_now
    )
    RETURNING id INTO v_event_id;

    -- Return handles so N8N can log / branch on the result.
    RETURN jsonb_build_object(
        'status',          'ok',
        'lead_id',         v_lead_id,
        'lead_was_new',    v_lead_was_new,
        'interaction_id',  v_interaction_id,
        'event_id',        v_event_id,
        'severity',        v_severity,
        'received_at',     v_now
    );
END;
$$;

-- Permissions: same lockdown pattern as exec_sql. Only the service role
-- (what N8N uses) may call this function; anon and authenticated cannot.
REVOKE ALL ON FUNCTION record_inbound_from_n8n(TEXT, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT, TIMESTAMPTZ)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION record_inbound_from_n8n(TEXT, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT, TIMESTAMPTZ)
    FROM anon;
REVOKE ALL ON FUNCTION record_inbound_from_n8n(TEXT, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT, TIMESTAMPTZ)
    FROM authenticated;
GRANT EXECUTE ON FUNCTION record_inbound_from_n8n(TEXT, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT, TIMESTAMPTZ)
    TO service_role;

COMMENT ON FUNCTION record_inbound_from_n8n(TEXT, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT, TIMESTAMPTZ) IS
    'Called by the OASIS Inbound Qualifier N8N workflow (1cGIN32alM8sf8OV) '
    'after each classified email. Upserts lead, inserts interaction, '
    'publishes agent_events.inbound.classified. See '
    'docs/N8N_INBOUND_INTEGRATION.md for the paste-in node config.';

-- ============================================================
-- END OF MIGRATION 012
-- ============================================================
