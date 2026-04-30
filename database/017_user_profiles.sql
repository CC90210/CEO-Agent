-- Migration 017 — User Profiles + Integration Health + Daily Plans
-- The OASIS AI Agent Command Center is multi-tenant. This migration introduces
-- the schema that lets each operator (CC today, clients tomorrow) have:
--   1. A profile row that drives the dashboard (brand, MRR target, agents enabled,
--      manifesto, pinned sales script version, custom fields).
--   2. An integration health view so the Settings page can show green/red dots.
--   3. A daily-plans table so the Today page can render hour-by-hour schedules
--      and primary leads without hardcoding anything in the UI.
--   4. An n8n inbound shared-secret table so the webhook can authenticate posts
--      from the OASIS Inbound Qualifier workflow without us putting the secret
--      in the dashboard URL.
--
-- All tables are additive. None of the existing tables are altered. RLS-ready
-- (Supabase auth.users foreign keys), but the dashboard reads with the service-
-- role key for v1 — RLS hardens when we ship client-facing accounts.
--
-- Apply with:  python scripts/apply_migration.py database/017_user_profiles.sql

BEGIN;

-- ============================================================================
-- 1. user_profiles — one row per operator. Drives the entire UI.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id    uuid UNIQUE,                        -- nullable until Supabase Auth wired
    email           text UNIQUE NOT NULL,
    full_name       text NOT NULL,
    display_name    text,                               -- e.g. "CC" vs "Conaugh McKenna"
    brand           text NOT NULL DEFAULT 'OASIS AI',
    role            text NOT NULL DEFAULT 'operator',   -- 'operator' | 'client' | 'admin'

    -- Revenue targets (drives the stat band on Today)
    mrr_target_usd      numeric(10, 2) NOT NULL DEFAULT 5000.00,
    mrr_current_usd     numeric(10, 2) NOT NULL DEFAULT 0.00,
    mrr_target_date     date,

    -- Agent configuration (drives the Agents page + sidebar visibility)
    agents_enabled  text[] NOT NULL DEFAULT ARRAY['bravo'],
    primary_agent   text NOT NULL DEFAULT 'bravo',

    -- Sales / content pinning
    manifesto                  text,
    primary_script_version     text NOT NULL DEFAULT 'cold_call_v1',
    deal_architecture_version  text NOT NULL DEFAULT 'v1',

    -- Free-form expansion without migrations
    custom_fields   jsonb NOT NULL DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON public.user_profiles (email);
CREATE INDEX IF NOT EXISTS idx_user_profiles_auth_user_id ON public.user_profiles (auth_user_id);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.touch_user_profiles_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON public.user_profiles;
CREATE TRIGGER trg_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- 2. daily_plans — hour-by-hour schedule + primary lead per operator per day.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.daily_plans (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id       uuid NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    plan_date        date NOT NULL,

    -- The day's mission statement, primary lead, and notes
    mission          text,
    primary_lead_id  uuid REFERENCES public.leads(id) ON DELETE SET NULL,
    primary_lead_play text,           -- the specific play for that lead today

    -- Targets for the day (drives the Today stats)
    target_calls     int NOT NULL DEFAULT 0,
    target_emails    int NOT NULL DEFAULT 0,
    target_bookings  int NOT NULL DEFAULT 1,

    -- Schedule entries: array of {time_label, title, body, intensity: 'intense'|'normal'|'break'}
    schedule         jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- End-of-day retro
    actual_calls     int,
    actual_bookings  int,
    retro_notes      text,

    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),

    UNIQUE (profile_id, plan_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_plans_profile_date
    ON public.daily_plans (profile_id, plan_date DESC);

DROP TRIGGER IF EXISTS trg_daily_plans_updated_at ON public.daily_plans;
CREATE TRIGGER trg_daily_plans_updated_at
    BEFORE UPDATE ON public.daily_plans
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- 3. n8n_webhook_secrets — shared-secret auth for the n8n inbound bridge.
--    Each profile gets its own secret so multi-tenant n8n posts can be routed.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.n8n_webhook_secrets (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id       uuid NOT NULL REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    secret_hash      text NOT NULL,    -- sha256 of the actual secret
    label            text,             -- e.g. "OASIS Inbound Qualifier"
    last_used_at     timestamptz,
    use_count        int NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    revoked_at       timestamptz
);

CREATE INDEX IF NOT EXISTS idx_n8n_secrets_profile ON public.n8n_webhook_secrets (profile_id);
CREATE INDEX IF NOT EXISTS idx_n8n_secrets_hash ON public.n8n_webhook_secrets (secret_hash);

-- ============================================================================
-- 4. integrations_health — operator-facing status for Settings page.
--    Updated by background workers (scheduler, send_gateway, telegram bridge).
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.integrations_health (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id       uuid REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    service          text NOT NULL,         -- 'supabase' | 'stripe' | 'gmail' | 'n8n_inbound' | 'telegram' | 'browser_harness'
    status           text NOT NULL,         -- 'healthy' | 'degraded' | 'down' | 'unconfigured'
    last_ping_at     timestamptz,
    last_error       text,
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (profile_id, service)
);

CREATE INDEX IF NOT EXISTS idx_integrations_profile_service
    ON public.integrations_health (profile_id, service);

-- ============================================================================
-- 5. RPC: record_inbound_from_n8n_v2 — extends migration 012's RPC to accept
--    profile_id + secret_hash so multi-tenant routing works through one URL.
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
    v_lead_id          uuid;
    v_interaction_id   uuid;
BEGIN
    -- 1. Authenticate the secret
    SELECT EXISTS (
        SELECT 1 FROM public.n8n_webhook_secrets
        WHERE profile_id = p_profile_id
          AND secret_hash = p_secret_hash
          AND revoked_at IS NULL
    ) INTO v_secret_valid;

    IF NOT v_secret_valid THEN
        RAISE EXCEPTION 'invalid_n8n_secret' USING ERRCODE = '42501';
    END IF;

    -- 2. Update the secret's last_used_at + counter
    UPDATE public.n8n_webhook_secrets
    SET last_used_at = now(),
        use_count = use_count + 1
    WHERE profile_id = p_profile_id AND secret_hash = p_secret_hash;

    -- 3. Find or create a lead for this email
    SELECT id INTO v_lead_id
    FROM public.leads
    WHERE lower(email) = lower(p_from_email)
    LIMIT 1;

    IF v_lead_id IS NULL THEN
        INSERT INTO public.leads (email, name, status, source, score)
        VALUES (p_from_email, split_part(p_from_email, '@', 1), 'new', 'n8n_inbound', 50)
        RETURNING id INTO v_lead_id;
    END IF;

    -- 4. Record the interaction
    INSERT INTO public.lead_interactions (
        lead_id, type, channel, subject, content, agent_source, metadata, created_at
    ) VALUES (
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

    -- 5. Bump the integrations_health row so Settings shows green
    INSERT INTO public.integrations_health (profile_id, service, status, last_ping_at)
    VALUES (p_profile_id, 'n8n_inbound', 'healthy', now())
    ON CONFLICT (profile_id, service) DO UPDATE
    SET status = 'healthy',
        last_ping_at = now(),
        last_error = NULL,
        updated_at = now();

    RETURN v_interaction_id;
END;
$$;

-- ============================================================================
-- 6. RPC: ping_integration — lightweight health-bump for background workers.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.ping_integration(
    p_profile_id  uuid,
    p_service     text,
    p_status      text DEFAULT 'healthy',
    p_error       text DEFAULT NULL,
    p_metadata    jsonb DEFAULT '{}'::jsonb
)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.integrations_health (profile_id, service, status, last_ping_at, last_error, metadata)
    VALUES (p_profile_id, p_service, p_status, now(), p_error, p_metadata)
    ON CONFLICT (profile_id, service) DO UPDATE
    SET status = EXCLUDED.status,
        last_ping_at = now(),
        last_error = EXCLUDED.last_error,
        metadata = EXCLUDED.metadata,
        updated_at = now();
END;
$$;

COMMIT;
