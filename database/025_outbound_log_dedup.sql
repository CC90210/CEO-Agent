-- 025_outbound_log_dedup.sql
--
-- Migration 022 introduced record_outbound_from_gateway_v1, which inserts
-- a fresh lead_interactions row per call. send_gateway already inserts
-- locally too (it's the source of truth for cooldown_until + the email_log
-- mirror), so when the operator configures the HTTP write-through, every
-- send produces TWO lead_interactions rows — Pipeline shows duplicates.
--
-- Fix: extend the RPC to accept an OPTIONAL p_existing_interaction_id.
-- When supplied (operator's local row already exists), the RPC stamps
-- tenant_id on that row + publishes agent_events instead of inserting.
-- When omitted (future SaaS clients without local Supabase access),
-- behavior unchanged — RPC inserts as before.
--
-- Apply with: python scripts/apply_migration.py database/025_outbound_log_dedup.sql

BEGIN;

CREATE OR REPLACE FUNCTION public.record_outbound_from_gateway_v1(
    p_profile_id              uuid,
    p_secret_hash             text,
    p_to_email                text,
    p_subject                 text,
    p_body_preview            text,
    p_lead_id                 uuid DEFAULT NULL,
    p_status                  text DEFAULT 'sent',
    p_channel                 text DEFAULT 'email',
    p_agent_source            text DEFAULT 'send_gateway',
    p_sent_at                 timestamptz DEFAULT now(),
    p_metadata                jsonb DEFAULT '{}'::jsonb,
    p_existing_interaction_id uuid DEFAULT NULL
)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_secret_valid   boolean;
    v_tenant_id      uuid;
    v_lead_id        uuid;
    v_interaction_id uuid;
    v_action_type    text;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM public.n8n_webhook_secrets
        WHERE profile_id = p_profile_id
          AND secret_hash = p_secret_hash
          AND revoked_at IS NULL
    ) INTO v_secret_valid;
    IF NOT v_secret_valid THEN
        RAISE EXCEPTION 'invalid_outbound_secret' USING ERRCODE = '42501';
    END IF;

    v_tenant_id := public.resolve_tenant_for_profile(p_profile_id);
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant' USING ERRCODE = '22023';
    END IF;

    UPDATE public.n8n_webhook_secrets
    SET last_used_at = now(), use_count = use_count + 1
    WHERE profile_id = p_profile_id AND secret_hash = p_secret_hash;

    v_action_type := CASE
        WHEN p_channel = 'email'    THEN 'email_sent'
        WHEN p_channel = 'dm'       THEN 'dm_sent'
        WHEN p_channel = 'linkedin' THEN 'linkedin_sent'
        WHEN p_channel = 'sms'      THEN 'sms_sent'
        WHEN p_channel = 'call'     THEN 'call_made'
        ELSE 'email_sent'
    END;

    -- DEDUP PATH — operator's local insert already wrote the row; just
    -- stamp tenant + bump health + publish agent_events. No second row.
    IF p_existing_interaction_id IS NOT NULL THEN
        UPDATE public.lead_interactions
        SET tenant_id = COALESCE(tenant_id, v_tenant_id)
        WHERE id = p_existing_interaction_id;
        v_interaction_id := p_existing_interaction_id;
    ELSE
        -- INSERT PATH — caller has no local row (future SaaS client
        -- machines without Supabase service-role access). Same logic
        -- as 022.
        IF p_lead_id IS NOT NULL THEN
            v_lead_id := p_lead_id;
        ELSE
            SELECT id INTO v_lead_id
            FROM public.leads
            WHERE lower(email) = lower(p_to_email) AND tenant_id = v_tenant_id
            LIMIT 1;

            IF v_lead_id IS NULL THEN
                INSERT INTO public.leads (tenant_id, email, name, status, source, score)
                VALUES (
                    v_tenant_id,
                    p_to_email,
                    split_part(p_to_email, '@', 1),
                    'new',
                    'outbound_gateway',
                    40
                )
                RETURNING id INTO v_lead_id;
            END IF;
        END IF;

        INSERT INTO public.lead_interactions (
            tenant_id, lead_id, type, channel, subject, content, agent_source, metadata, created_at
        ) VALUES (
            v_tenant_id,
            v_lead_id,
            v_action_type,
            p_channel,
            p_subject,
            p_body_preview,
            p_agent_source,
            p_metadata || jsonb_build_object(
                'to_email', p_to_email,
                'status', p_status,
                'profile_id', p_profile_id
            ),
            p_sent_at
        )
        RETURNING id INTO v_interaction_id;
    END IF;

    -- Always publish to agent_events on confirmed sends — Activity Tape
    -- needs the event regardless of which path the row came from.
    IF p_status = 'sent' THEN
        INSERT INTO public.agent_events (
            tenant_id, event_type, publisher_agent, severity, payload, published_at
        ) VALUES (
            v_tenant_id,
            'outbound.sent',
            COALESCE(p_agent_source, 'send_gateway'),
            'info',
            jsonb_build_object(
                'lead_id', COALESCE(v_lead_id, p_lead_id),
                'interaction_id', v_interaction_id,
                'to_email', p_to_email,
                'subject', p_subject,
                'channel', p_channel,
                'profile_id', p_profile_id
            ),
            p_sent_at
        );
    END IF;

    INSERT INTO public.integrations_health (tenant_id, profile_id, service, status, last_ping_at)
    VALUES (v_tenant_id, p_profile_id, 'send_gateway', 'healthy', now())
    ON CONFLICT (profile_id, service) DO UPDATE
    SET tenant_id = EXCLUDED.tenant_id,
        status = 'healthy',
        last_ping_at = now(),
        last_error = NULL,
        updated_at = now();

    RETURN v_interaction_id;
END;
$$;

COMMIT;
