-- 022_outbound_log_rpc.sql
--
-- The /api/inbound/n8n surface lets the n8n classifier POST received emails;
-- the dashboard's Pipeline + Activity Tape pick them up via lead_interactions
-- + agent_events. Outbound (send_gateway.py + email_engine.py) had no such
-- surface — Python wrote direct to lead_interactions but never set tenant_id,
-- so the tenant-filtered Pipeline query missed every recent send. The
-- dashboard fell back to older gmail_historical_backfill rows that DID have
-- tenant set, so "Recent Outbound" lied with 8d-old data while real sends
-- happened hours ago.
--
-- This migration introduces:
--   1. record_outbound_from_gateway_v1 — RPC that mirrors the inbound RPC.
--      Resolves tenant from profile, writes lead_interactions WITH tenant_id,
--      and publishes agent_events("outbound.sent") so the Operations Activity
--      Tape lights up in the same write.
--   2. Reuses n8n_webhook_secrets for HMAC auth — the secret per profile
--      gates both inbound and outbound (one shared secret per operator).
--
-- Apply with: python scripts/apply_migration.py database/022_outbound_log_rpc.sql

BEGIN;

-- ============================================================================
-- record_outbound_from_gateway_v1 — auth + insert + event publish, atomic.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.record_outbound_from_gateway_v1(
    p_profile_id       uuid,
    p_secret_hash      text,
    p_to_email         text,
    p_subject          text,
    p_body_preview     text,
    p_lead_id          uuid DEFAULT NULL,
    p_status           text DEFAULT 'sent',
    p_channel          text DEFAULT 'email',
    p_agent_source     text DEFAULT 'send_gateway',
    p_sent_at          timestamptz DEFAULT now(),
    p_metadata         jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_secret_valid   boolean;
    v_tenant_id      uuid;
    v_lead_id        uuid;
    v_interaction_id uuid;
    v_action_type    text;
BEGIN
    -- 1. Auth — same secrets table as inbound. One HMAC per profile gates both.
    SELECT EXISTS (
        SELECT 1 FROM public.n8n_webhook_secrets
        WHERE profile_id = p_profile_id
          AND secret_hash = p_secret_hash
          AND revoked_at IS NULL
    ) INTO v_secret_valid;
    IF NOT v_secret_valid THEN
        RAISE EXCEPTION 'invalid_outbound_secret' USING ERRCODE = '42501';
    END IF;

    -- 2. Resolve tenant from profile (helper from migration 019)
    v_tenant_id := public.resolve_tenant_for_profile(p_profile_id);
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant' USING ERRCODE = '22023';
    END IF;

    -- 3. Bump secret usage for visibility on the secret-management UI.
    UPDATE public.n8n_webhook_secrets
    SET last_used_at = now(), use_count = use_count + 1
    WHERE profile_id = p_profile_id AND secret_hash = p_secret_hash;

    -- 4. Resolve lead — caller's lead_id wins; otherwise find-or-create by
    --    (tenant_id, lower(email)) so cross-tenant collisions don't share rows.
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

    -- 5. Action type by channel — keeps the existing dashboard filter
    --    (lib/queries.ts:recentOutbound `type IN ('email_sent','dm_sent',...)`)
    --    correct without dashboard-side changes.
    v_action_type := CASE
        WHEN p_channel = 'email'    THEN 'email_sent'
        WHEN p_channel = 'dm'       THEN 'dm_sent'
        WHEN p_channel = 'linkedin' THEN 'linkedin_sent'
        WHEN p_channel = 'sms'      THEN 'sms_sent'
        WHEN p_channel = 'call'     THEN 'call_made'
        ELSE 'email_sent'
    END;

    -- 6. The interaction row — tenant_id stamped so the dashboard query sees it.
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

    -- 7. Publish to agent_events so Operations Activity Tape sees it.
    --    Only on real sends — skip blocked/dry_run/queued so the tape stays
    --    signal-not-noise. (The lead_interactions row still gets written so
    --    cooldown logic is preserved.)
    IF p_status = 'sent' THEN
        INSERT INTO public.agent_events (
            tenant_id, event_type, publisher_agent, severity, payload, published_at
        ) VALUES (
            v_tenant_id,
            'outbound.sent',
            COALESCE(p_agent_source, 'send_gateway'),
            'info',
            jsonb_build_object(
                'lead_id', v_lead_id,
                'interaction_id', v_interaction_id,
                'to_email', p_to_email,
                'subject', p_subject,
                'channel', p_channel,
                'profile_id', p_profile_id
            ),
            p_sent_at
        );
    END IF;

    -- 8. Health ping for the gateway so /integrations shows it as live.
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

COMMENT ON FUNCTION public.record_outbound_from_gateway_v1 IS
    'Outbound write-back from send_gateway. HMAC-auth via n8n_webhook_secrets, '
    'tenant-resolved from profile, atomic insert of lead_interactions + '
    'agent_events. Mirrors record_inbound_from_n8n_v2.';

COMMIT;
