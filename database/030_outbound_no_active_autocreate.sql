-- ============================================================
-- BRAVO V6 — Migration 030: outbound gateway stops creating ACTIVE leads
-- ============================================================
-- PURPOSE
-- The record_outbound_from_gateway_v1 RPC (introduced in 022, deduped in
-- 025) auto-creates a lead row with status='new' and source='outbound_gateway'
-- whenever you send an email to an address not already in your leads table.
-- Result: cold-outreach addresses that never reply pollute the active pipeline.
-- CC's example: derrick@currentplumbing.ca - sent him an email, no response,
-- showed as a 'new' lead in /pipeline.
--
-- This migration changes the auto-create path to insert with
-- status='archived' instead of 'new'. The interaction still gets logged
-- (so you can see what was sent + cooldown logic still works), but the
-- recipient does NOT show in the active pipeline. If they REPLY (via the
-- inbound n8n path), the inbound RPC bumps status back to 'contacted'
-- and the lead surfaces.
--
-- Real leads come from:
--   - n8n_inbound (someone emailed YOU - they're engaged)
--   - Manual creation with score >= 50 (you flagged them as worth tracking)
--   - Status promotion (you moved a cold archive to contacted/qualified)
--
-- Apply with: python scripts/apply_migration.py database/030_outbound_no_active_autocreate.sql --allow-rls
-- ============================================================

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

    -- DEDUP PATH — operator's local insert already wrote the row.
    IF p_existing_interaction_id IS NOT NULL THEN
        UPDATE public.lead_interactions
        SET tenant_id = COALESCE(tenant_id, v_tenant_id)
        WHERE id = p_existing_interaction_id;
        v_interaction_id := p_existing_interaction_id;
    ELSE
        IF p_lead_id IS NOT NULL THEN
            v_lead_id := p_lead_id;
        ELSE
            SELECT id INTO v_lead_id
            FROM public.leads
            WHERE lower(email) = lower(p_to_email) AND tenant_id = v_tenant_id
            LIMIT 1;

            IF v_lead_id IS NULL THEN
                -- CHANGED IN 030: status='archived' (was 'new'). Outbound to
                -- an unknown address tracks the interaction but does NOT
                -- pollute the active pipeline. If they reply, the inbound
                -- RPC promotes to 'contacted' and surfaces them.
                INSERT INTO public.leads (tenant_id, email, name, status, source, score)
                VALUES (
                    v_tenant_id,
                    p_to_email,
                    split_part(p_to_email, '@', 1),
                    'archived',
                    'outbound_gateway',
                    20
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

    -- Bump integrations_health for send_gateway
    INSERT INTO public.integrations_health (
        profile_id, service, status, last_ping_at, metadata
    ) VALUES (
        p_profile_id, 'send_gateway', 'healthy', now(),
        jsonb_build_object('last_action', v_action_type)
    )
    ON CONFLICT (profile_id, service) DO UPDATE
    SET status = EXCLUDED.status,
        last_ping_at = EXCLUDED.last_ping_at,
        metadata = EXCLUDED.metadata;

    -- Publish agent_events for the live event tape
    INSERT INTO public.agent_events (
        event_type, publisher_agent, severity, payload, correlation_id, published_at
    ) VALUES (
        'outbound.recorded',
        p_agent_source,
        'info',
        jsonb_build_object(
            'lead_id', v_lead_id,
            'interaction_id', v_interaction_id,
            'channel', p_channel,
            'to_email', p_to_email,
            'subject', p_subject
        ),
        v_tenant_id::text,
        now()
    );

    RETURN v_interaction_id;
END $$;

COMMIT;
