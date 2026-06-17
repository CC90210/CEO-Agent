-- 101_outbound_rpc_direction_preview.sql
--
-- ⚠️  NOT YET APPLIED. Authored by Bravo (VPS) 2026-06-16, surfaced to CC for
--     review before running. Apply with:
--         python scripts/apply_migration.py database/101_outbound_rpc_direction_preview.sql
--
-- WHY
-- ---
-- Conversations / Activity Tape showed outbound email rows with a blank body
-- and an ambiguous direction. Root cause: record_outbound_from_gateway_v1
-- (migration 022, step 6) inserts lead_interactions with `content` = body
-- preview but never populates `content_preview` and never sets `direction`.
-- The dashboard now masks this by falling back to the subject, but the stored
-- data is still wrong — `content_preview IS NULL` and `direction IS NULL`.
--
-- The VPS writer (send_gateway.py: reserve_send_slot / finalize_reserved_action
-- / log_action) was fixed in the same pass to stamp content_preview + direction
-- on its LOCAL inserts. This migration brings the dashboard RPC's INSERT path
-- to parity so rows created via /api/outbound/log are correct too.
--
-- CHANGE
-- ------
-- Only step 6 (the lead_interactions INSERT) changes vs migration 022:
--   + content_preview := COALESCE(NULLIF(p_body_preview, ''), left(p_subject, 140))
--   + direction       := 'outbound'   (this RPC only ever records sends)
-- Everything else (auth, tenant resolve, lead find-or-create, agent_events,
-- health ping) is reproduced verbatim from 022 so CREATE OR REPLACE is a clean
-- swap. Signature is unchanged, so no caller (outbound_log_post.py / the
-- /api/outbound/log route) needs to change.

BEGIN;

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

    -- 5. Action type by channel.
    v_action_type := CASE
        WHEN p_channel = 'email'    THEN 'email_sent'
        WHEN p_channel = 'dm'       THEN 'dm_sent'
        WHEN p_channel = 'linkedin' THEN 'linkedin_sent'
        WHEN p_channel = 'sms'      THEN 'sms_sent'
        WHEN p_channel = 'call'     THEN 'call_made'
        ELSE 'email_sent'
    END;

    -- 6. The interaction row. CHANGED vs 022: also stamp content_preview and
    --    direction so Conversations shows a real preview and a correct side.
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

    -- 7. Publish to agent_events so Operations Activity Tape sees it.
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
    'agent_events. Mirrors record_inbound_from_n8n_v2. v101: stamps '
    'content_preview + direction=outbound on the interaction row.';

COMMIT;
