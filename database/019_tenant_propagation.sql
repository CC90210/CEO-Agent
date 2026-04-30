-- Migration 019 — Tenant ID Propagation
--
-- Migration 018 introduced tenant_id on every business table, but the existing
-- RPCs (record_inbound_from_n8n_v2, record_inbound_from_n8n) and Python writers
-- predate that change and don't set tenant_id. New rows land tenant-less and
-- the dashboard's tenant-filtered queries don't see them.
--
-- This migration:
--   1. Rewrites record_inbound_from_n8n_v2 to resolve tenant_id from the profile
--      and stamp it on every new lead / lead_interaction / integrations_health row
--   2. Rewrites record_inbound_from_n8n (v1) similarly — drives the
--      email_engine.check-inbox path used by the local scheduler + future VPS
--   3. Adds resolve_tenant_for_email(text) helper for Python scripts to look
--      up the right tenant by operator email
--   4. Adds resolve_tenant_for_profile(uuid) helper for write paths that
--      already know the profile_id
--   5. Backfills tenant_id on rows still missing it
--
-- Apply with: python scripts/apply_migration.py database/019_tenant_propagation.sql

BEGIN;

-- ============================================================================
-- 1. Helper: resolve tenant by email (used by Python writers)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.resolve_tenant_for_email(p_email text)
RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT tenant_id FROM public.user_profiles
    WHERE lower(email) = lower(p_email)
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public.resolve_tenant_for_profile(p_profile_id uuid)
RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT tenant_id FROM public.user_profiles WHERE id = p_profile_id LIMIT 1;
$$;

-- ============================================================================
-- 2. Replace record_inbound_from_n8n_v2 — now stamps tenant_id everywhere
-- ============================================================================
CREATE OR REPLACE FUNCTION public.record_inbound_from_n8n_v2(
    p_profile_id      uuid,
    p_secret_hash     text,
    p_from_email      text,
    p_subject         text,
    p_body            text,
    p_classification  jsonb,
    p_received_at     timestamptz DEFAULT now()
)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_secret_valid     boolean;
    v_tenant_id        uuid;
    v_lead_id          uuid;
    v_interaction_id   uuid;
BEGIN
    -- Auth: validate secret hash (now also matches tenant_id implicitly via profile)
    SELECT EXISTS (
        SELECT 1 FROM public.n8n_webhook_secrets
        WHERE profile_id = p_profile_id
          AND secret_hash = p_secret_hash
          AND revoked_at IS NULL
    ) INTO v_secret_valid;
    IF NOT v_secret_valid THEN
        RAISE EXCEPTION 'invalid_n8n_secret' USING ERRCODE = '42501';
    END IF;

    -- Resolve tenant from profile
    v_tenant_id := public.resolve_tenant_for_profile(p_profile_id);
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant' USING ERRCODE = '22023';
    END IF;

    -- Bump secret usage
    UPDATE public.n8n_webhook_secrets
    SET last_used_at = now(), use_count = use_count + 1
    WHERE profile_id = p_profile_id AND secret_hash = p_secret_hash;

    -- Find or create the lead, scoped to tenant
    SELECT id INTO v_lead_id
    FROM public.leads
    WHERE lower(email) = lower(p_from_email) AND tenant_id = v_tenant_id
    LIMIT 1;

    IF v_lead_id IS NULL THEN
        INSERT INTO public.leads (tenant_id, email, name, status, source, score)
        VALUES (v_tenant_id, p_from_email, split_part(p_from_email, '@', 1), 'new', 'n8n_inbound', 50)
        RETURNING id INTO v_lead_id;
    END IF;

    -- Record the interaction with tenant_id
    INSERT INTO public.lead_interactions (
        tenant_id, lead_id, type, channel, subject, content, agent_source, metadata, created_at
    ) VALUES (
        v_tenant_id,
        v_lead_id,
        'email_received',
        'email',
        p_subject,
        p_body,
        'n8n',
        jsonb_build_object(
            'from_identity', p_from_email,
            'classification', p_classification,
            'profile_id', p_profile_id
        ),
        p_received_at
    )
    RETURNING id INTO v_interaction_id;

    -- Bump health for this tenant
    INSERT INTO public.integrations_health (tenant_id, profile_id, service, status, last_ping_at)
    VALUES (v_tenant_id, p_profile_id, 'n8n_inbound', 'healthy', now())
    ON CONFLICT (profile_id, service) DO UPDATE
    SET tenant_id = EXCLUDED.tenant_id,
        status = 'healthy',
        last_ping_at = now(),
        last_error = NULL,
        updated_at = now();

    RETURN v_interaction_id;
END;
$$;

-- ============================================================================
-- 3. Replace record_inbound_from_n8n (v1) — same tenant treatment, with the
--    profile resolved from p_to_email (the operator's address) when available.
-- ============================================================================

-- Find the existing signature so we replace exactly. Older RPC takes:
--   p_from_email, p_from_name, p_subject, p_content, p_classification, p_message_id
-- (per email_engine.py line ~1019). Keep that surface; resolve tenant via the
-- canonical operator email (OPERATOR_EMAIL is the env var; here we use the
-- email that owns the OASIS Gmail in the system — encoded as a system setting).
--
-- Strategy: look for ANY profile that's an 'operator' role and assume that's
-- the tenant. For multi-tenant servers (later), the email_engine writer will
-- need to pass the tenant_id explicitly. For now (single-operator server),
-- this is correct.

CREATE OR REPLACE FUNCTION public.record_inbound_from_n8n(
    p_from_email      text,
    p_from_name       text,
    p_subject         text,
    p_content         text,
    p_classification  jsonb,
    p_message_id      text DEFAULT NULL
)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_tenant_id        uuid;
    v_lead_id          uuid;
    v_interaction_id   uuid;
BEGIN
    -- Resolve the canonical operator's tenant. Single-operator-per-server for now;
    -- multi-tenant servers must route inbound to a specific tenant via the v2 RPC.
    SELECT tenant_id INTO v_tenant_id
    FROM public.user_profiles
    WHERE role = 'operator' AND tenant_id IS NOT NULL
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'no operator tenant configured' USING ERRCODE = '22023';
    END IF;

    -- Find or create lead in this tenant
    SELECT id INTO v_lead_id
    FROM public.leads
    WHERE lower(email) = lower(p_from_email) AND tenant_id = v_tenant_id
    LIMIT 1;

    IF v_lead_id IS NULL THEN
        INSERT INTO public.leads (tenant_id, email, name, status, source, score)
        VALUES (v_tenant_id, p_from_email,
                COALESCE(NULLIF(p_from_name, ''), split_part(p_from_email, '@', 1)),
                'new', 'inbound_email', 40)
        RETURNING id INTO v_lead_id;
    END IF;

    INSERT INTO public.lead_interactions (
        tenant_id, lead_id, type, channel, subject, content, agent_source, metadata, created_at
    ) VALUES (
        v_tenant_id,
        v_lead_id,
        'email_received',
        'email',
        p_subject,
        p_content,
        'email_engine',
        jsonb_build_object(
            'from_identity', p_from_email,
            'from_name', p_from_name,
            'classification', p_classification,
            'message_id', p_message_id
        ),
        now()
    )
    RETURNING id INTO v_interaction_id;

    RETURN v_interaction_id;
END;
$$;

-- ============================================================================
-- 4. Update ping_integration to default tenant_id from profile
-- ============================================================================
CREATE OR REPLACE FUNCTION public.ping_integration(
    p_profile_id  uuid,
    p_service     text,
    p_status      text DEFAULT 'healthy',
    p_error       text DEFAULT NULL,
    p_metadata    jsonb DEFAULT '{}'::jsonb
)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_tenant_id uuid;
BEGIN
    v_tenant_id := public.resolve_tenant_for_profile(p_profile_id);
    INSERT INTO public.integrations_health (tenant_id, profile_id, service, status, last_ping_at, last_error, metadata)
    VALUES (v_tenant_id, p_profile_id, p_service, p_status, now(), p_error, p_metadata)
    ON CONFLICT (profile_id, service) DO UPDATE
    SET tenant_id = COALESCE(EXCLUDED.tenant_id, public.integrations_health.tenant_id),
        status = EXCLUDED.status,
        last_ping_at = now(),
        last_error = EXCLUDED.last_error,
        metadata = EXCLUDED.metadata,
        updated_at = now();
END;
$$;

-- ============================================================================
-- 5. Backfill tenant_id on rows still missing it
-- ============================================================================
DO $$
DECLARE
    v_default_tenant uuid;
BEGIN
    -- Use CC's tenant as the canonical default for backfill
    SELECT id INTO v_default_tenant FROM public.tenants WHERE slug = 'oasis-ai-cc' LIMIT 1;
    IF v_default_tenant IS NULL THEN
        SELECT id INTO v_default_tenant FROM public.tenants ORDER BY created_at ASC LIMIT 1;
    END IF;
    IF v_default_tenant IS NOT NULL THEN
        UPDATE public.leads SET tenant_id = v_default_tenant WHERE tenant_id IS NULL;
        UPDATE public.lead_interactions SET tenant_id = v_default_tenant WHERE tenant_id IS NULL;
        UPDATE public.daily_plans SET tenant_id = v_default_tenant WHERE tenant_id IS NULL;
        UPDATE public.integrations_health SET tenant_id = v_default_tenant WHERE tenant_id IS NULL;
        UPDATE public.n8n_webhook_secrets SET tenant_id = v_default_tenant WHERE tenant_id IS NULL;
    END IF;
END $$;

-- ============================================================================
-- 6. Add unique constraint to prevent duplicate (profile_id, service) integrations.
--    Required for ON CONFLICT in ping_integration.
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'integrations_health_profile_service_uniq'
    ) THEN
        ALTER TABLE public.integrations_health
            ADD CONSTRAINT integrations_health_profile_service_uniq
            UNIQUE (profile_id, service);
    END IF;
END $$;

COMMIT;
