-- 101_outbound_rpc_direction_preview.sql
--
-- ⚠️  NOT APPLIED ON THE VPS. No working DDL-apply path is available here:
--       * the exec_sql RPC false-positives on any DDL whose body contains
--         RETURNING (it treats the statement as a SELECT and wraps it in a
--         subquery -> "syntax error at or near CREATE"); this function body
--         uses RETURNING, so the service-role RPC path cannot apply it, and
--       * SUPABASE_ACCESS_TOKEN (Management API PAT) is absent from .env.agents
--         and there is no direct Postgres connection string.
--     CC must apply this via the Management API / Supabase SQL editor / psql.
--
-- ⚠️  TARGETING CORRECTED 2026-06-16. The live function has TWO overloads:
--       11-arg (migration 022)  and  12-arg (migration 030, adds
--       p_existing_interaction_id). The dashboard /api/outbound/log route
--       hits the 12-arg overload, so THIS migration replaces the 12-arg one
--       (the earlier draft replaced the dead 11-arg). CC should also resolve
--       the overload ambiguity by DROPping the stale 11-arg version:
--         DROP FUNCTION public.record_outbound_from_gateway_v1(
--           uuid,text,text,text,text,uuid,text,text,text,timestamptz,jsonb);
--
-- WHY
-- ---
-- record_outbound_from_gateway_v1 inserts lead_interactions with `content` =
-- body preview but never populates `content_preview` and never sets
-- `direction`, so Conversations had to guess the body/side from the subject.
-- The VPS writer (send_gateway.py local inserts) was fixed in the same pass.
-- NOTE: the 12-arg DEDUP path (p_existing_interaction_id IS NOT NULL) only
-- stamps tenant_id and does NOT touch direction/content_preview, so the
-- send_gateway writer fix already makes operator/CLI ("manual_cc") sends
-- correct. This migration only matters for the ELSE branch — dashboard-
-- originated sends that create a NEW interaction row via the RPC.
--
-- CHANGE (vs the live 12-arg definition): the ELSE-branch lead_interactions
-- INSERT now also writes
--   content_preview := COALESCE(NULLIF(p_body_preview, ''), left(p_subject, 140))
--   direction       := 'outbound'
-- Everything else is reproduced verbatim from the live function so the
-- CREATE OR REPLACE is a clean, signature-preserving swap.

BEGIN;

CREATE OR REPLACE FUNCTION public.record_outbound_from_gateway_v1(p_profile_id uuid, p_secret_hash text, p_to_email text, p_subject text, p_body_preview text, p_lead_id uuid DEFAULT NULL::uuid, p_status text DEFAULT 'sent'::text, p_channel text DEFAULT 'email'::text, p_agent_source text DEFAULT 'send_gateway'::text, p_sent_at timestamp with time zone DEFAULT now(), p_metadata jsonb DEFAULT '{}'::jsonb, p_existing_interaction_id uuid DEFAULT NULL::uuid)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
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
            tenant_id, lead_id, type, channel, subject, content, content_preview,
            direction, agent_source, metadata, created_at
        ) VALUES (
            v_tenant_id,
            v_lead_id,
            v_action_type,
            p_channel,
            p_subject,
            p_body_preview,
            COALESCE(NULLIF(p_body_preview, ''), left(p_subject, 140)),
            'outbound',
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
END $function$;

COMMIT;
