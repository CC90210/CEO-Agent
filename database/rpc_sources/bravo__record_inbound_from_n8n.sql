CREATE OR REPLACE FUNCTION public.record_inbound_from_n8n(p_from_email text, p_from_name text DEFAULT NULL::text, p_subject text DEFAULT NULL::text, p_content text DEFAULT NULL::text, p_classification jsonb DEFAULT '{}'::jsonb, p_thread_id text DEFAULT NULL::text, p_message_id text DEFAULT NULL::text, p_received_at timestamp with time zone DEFAULT now())
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$
