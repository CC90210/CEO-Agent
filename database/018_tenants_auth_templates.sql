-- Migration 018 — Multi-Tenant + Auth + Plan Templates
--
-- Turns the OASIS AI Agent Command Center into a real multi-tenant product:
--   - tenants table (one per OASIS client)
--   - tenant_id on every business table + RLS policies
--   - plan_templates (weekday/weekend recurring schedule)
--   - daily_plan rollover via materialize_today_plan() RPC
--   - auth.users <-> user_profiles wiring for Supabase Auth
--
-- Apply with: python scripts/apply_migration.py database/018_tenants_auth_templates.sql

BEGIN;

-- ============================================================================
-- 1. tenants — one per OASIS client
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tenants (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            text UNIQUE NOT NULL,                         -- url-safe handle
    name            text NOT NULL,                                -- "OASIS AI" or "Acme Plumbing"
    plan_tier       text NOT NULL DEFAULT 'starter',              -- starter | pro | enterprise
    purchase_status text NOT NULL DEFAULT 'pending',              -- pending | active | suspended
    stripe_customer_id text,
    stripe_subscription_id text,
    primary_brand_color text DEFAULT '#e8c547',
    custom_fields   jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON public.tenants (slug);
CREATE INDEX IF NOT EXISTS idx_tenants_purchase_status ON public.tenants (purchase_status);

DROP TRIGGER IF EXISTS trg_tenants_updated_at ON public.tenants;
CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON public.tenants
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- 2. user_profiles ← link to tenants + auth.users
-- ============================================================================
ALTER TABLE public.user_profiles
    ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS preferred_language text NOT NULL DEFAULT 'en',
    ADD COLUMN IF NOT EXISTS prospect_focus text[] NOT NULL DEFAULT ARRAY['service_trades']::text[];

CREATE INDEX IF NOT EXISTS idx_user_profiles_tenant ON public.user_profiles (tenant_id);

-- Backfill: create the OASIS-AI tenant for CC and link existing profile
DO $$
DECLARE
    v_tenant_id uuid;
BEGIN
    SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = 'oasis-ai-cc';
    IF v_tenant_id IS NULL THEN
        INSERT INTO public.tenants (slug, name, plan_tier, purchase_status)
        VALUES ('oasis-ai-cc', 'OASIS AI', 'enterprise', 'active')
        RETURNING id INTO v_tenant_id;
    END IF;
    UPDATE public.user_profiles
    SET tenant_id = v_tenant_id
    WHERE tenant_id IS NULL;
END $$;

-- ============================================================================
-- 3. tenant_id on every business table
-- ============================================================================
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE;

ALTER TABLE public.lead_interactions
    ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE;

ALTER TABLE public.daily_plans
    ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE;

ALTER TABLE public.integrations_health
    ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE;

ALTER TABLE public.n8n_webhook_secrets
    ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE;

-- Backfill tenant_id on existing rows from CC's tenant
DO $$
DECLARE
    v_tenant_id uuid;
BEGIN
    SELECT id INTO v_tenant_id FROM public.tenants WHERE slug = 'oasis-ai-cc';
    IF v_tenant_id IS NOT NULL THEN
        UPDATE public.leads SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
        UPDATE public.lead_interactions SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
        UPDATE public.daily_plans SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
        UPDATE public.integrations_health SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
        UPDATE public.n8n_webhook_secrets SET tenant_id = v_tenant_id WHERE tenant_id IS NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leads_tenant ON public.leads (tenant_id);
CREATE INDEX IF NOT EXISTS idx_lead_interactions_tenant ON public.lead_interactions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_daily_plans_tenant ON public.daily_plans (tenant_id);
CREATE INDEX IF NOT EXISTS idx_integrations_health_tenant ON public.integrations_health (tenant_id);

-- ============================================================================
-- 4. plan_templates — recurring schedule (weekday | weekend)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.plan_templates (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    profile_id      uuid REFERENCES public.user_profiles(id) ON DELETE CASCADE,
    kind            text NOT NULL,                   -- 'weekday' | 'weekend'
    mission         text,                            -- default mission shown when this template fires
    target_calls    int NOT NULL DEFAULT 0,
    target_emails   int NOT NULL DEFAULT 0,
    target_bookings int NOT NULL DEFAULT 1,
    schedule        jsonb NOT NULL DEFAULT '[]'::jsonb,
    enabled         boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (profile_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_plan_templates_tenant ON public.plan_templates (tenant_id);
CREATE INDEX IF NOT EXISTS idx_plan_templates_profile_kind ON public.plan_templates (profile_id, kind);

DROP TRIGGER IF EXISTS trg_plan_templates_updated_at ON public.plan_templates;
CREATE TRIGGER trg_plan_templates_updated_at
    BEFORE UPDATE ON public.plan_templates
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- 5. RPC: materialize_today_plan — fired by cron at 11 PM each night
--    Picks the right template (weekday vs weekend) and creates tomorrow's plan.
--    Rolls forward incomplete blocks from yesterday as 'carryover'.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.materialize_today_plan(
    p_profile_id  uuid,
    p_target_date date DEFAULT NULL
)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_target_date    date;
    v_dow            int;        -- 0=Sun .. 6=Sat
    v_kind           text;
    v_template       record;
    v_yesterday_plan record;
    v_carryover      jsonb := '[]'::jsonb;
    v_final_schedule jsonb;
    v_tenant_id      uuid;
    v_plan_id        uuid;
BEGIN
    v_target_date := COALESCE(p_target_date, current_date);
    v_dow := EXTRACT(DOW FROM v_target_date);
    v_kind := CASE WHEN v_dow IN (0, 6) THEN 'weekend' ELSE 'weekday' END;

    SELECT tenant_id INTO v_tenant_id FROM public.user_profiles WHERE id = p_profile_id;
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant_id' USING ERRCODE = '22023';
    END IF;

    -- Find the template
    SELECT * INTO v_template
    FROM public.plan_templates
    WHERE profile_id = p_profile_id AND kind = v_kind AND enabled = true
    LIMIT 1;

    -- Carryover: yesterday's plan, blocks marked unfinished
    SELECT * INTO v_yesterday_plan
    FROM public.daily_plans
    WHERE profile_id = p_profile_id
      AND plan_date = v_target_date - INTERVAL '1 day'
    LIMIT 1;
    IF v_yesterday_plan.id IS NOT NULL AND jsonb_array_length(COALESCE(v_yesterday_plan.schedule, '[]'::jsonb)) > 0 THEN
        SELECT COALESCE(jsonb_agg(b || jsonb_build_object('intensity', 'carryover')), '[]'::jsonb)
        INTO v_carryover
        FROM jsonb_array_elements(v_yesterday_plan.schedule) b
        WHERE COALESCE(b->>'completed', 'false')::boolean = false
          AND COALESCE(b->>'intensity', '') <> 'break';
    END IF;

    v_final_schedule := COALESCE(v_carryover, '[]'::jsonb)
                     || COALESCE(v_template.schedule, '[]'::jsonb);

    -- Upsert today's plan
    INSERT INTO public.daily_plans (
        tenant_id, profile_id, plan_date, mission,
        target_calls, target_emails, target_bookings, schedule
    )
    VALUES (
        v_tenant_id, p_profile_id, v_target_date,
        COALESCE(v_template.mission, 'Daily ops'),
        COALESCE(v_template.target_calls, 0),
        COALESCE(v_template.target_emails, 0),
        COALESCE(v_template.target_bookings, 1),
        v_final_schedule
    )
    ON CONFLICT (profile_id, plan_date) DO UPDATE
    SET schedule = EXCLUDED.schedule,
        mission = EXCLUDED.mission,
        target_calls = EXCLUDED.target_calls,
        target_emails = EXCLUDED.target_emails,
        target_bookings = EXCLUDED.target_bookings,
        updated_at = now()
    RETURNING id INTO v_plan_id;

    RETURN v_plan_id;
END;
$$;

-- ============================================================================
-- 6. RLS — tenant isolation
-- ============================================================================
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integrations_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.n8n_webhook_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plan_templates ENABLE ROW LEVEL SECURITY;

-- Helper: get tenant_id for the current authed user
CREATE OR REPLACE FUNCTION public.current_tenant_id()
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT tenant_id FROM public.user_profiles WHERE auth_user_id = auth.uid() LIMIT 1;
$$;

-- Tenant policy template: each table — tenant members read/write their own rows.
-- Idempotent via pg_policies catalog check (avoids DROP POLICY which the
-- migration runner blocks for safety; rerunning is a no-op).
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'leads',
        'lead_interactions',
        'daily_plans',
        'integrations_health',
        'n8n_webhook_secrets',
        'plan_templates'
    ]) LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=t AND policyname='tenant_isolation_select') THEN
            EXECUTE format($p$
                CREATE POLICY tenant_isolation_select ON public.%1$I
                    FOR SELECT TO authenticated
                    USING (tenant_id = public.current_tenant_id());
            $p$, t);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=t AND policyname='tenant_isolation_modify') THEN
            EXECUTE format($p$
                CREATE POLICY tenant_isolation_modify ON public.%1$I
                    FOR ALL TO authenticated
                    USING (tenant_id = public.current_tenant_id())
                    WITH CHECK (tenant_id = public.current_tenant_id());
            $p$, t);
        END IF;
    END LOOP;
END $$;

-- user_profiles: a user reads their own row + their tenant siblings; updates their own only
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='user_profiles' AND policyname='profile_self_or_tenant') THEN
        CREATE POLICY profile_self_or_tenant ON public.user_profiles
            FOR SELECT TO authenticated
            USING (auth_user_id = auth.uid() OR tenant_id = public.current_tenant_id());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='user_profiles' AND policyname='profile_self_update') THEN
        CREATE POLICY profile_self_update ON public.user_profiles
            FOR UPDATE TO authenticated
            USING (auth_user_id = auth.uid())
            WITH CHECK (auth_user_id = auth.uid());
    END IF;
END $$;

-- tenants: members read their own tenant row
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='tenants' AND policyname='tenant_self_select') THEN
        CREATE POLICY tenant_self_select ON public.tenants
            FOR SELECT TO authenticated
            USING (id = public.current_tenant_id());
    END IF;
END $$;

-- Service-role bypasses RLS automatically; the dashboard reads via service role server-side.

-- ============================================================================
-- 7. RPC: signup_tenant — atomic tenant + profile creation post Supabase Auth signup
-- ============================================================================
CREATE OR REPLACE FUNCTION public.signup_tenant(
    p_auth_user_id uuid,
    p_email        text,
    p_full_name    text,
    p_brand        text DEFAULT 'OASIS AI',
    p_slug         text DEFAULT NULL
)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_tenant_id  uuid;
    v_profile_id uuid;
    v_slug       text;
BEGIN
    -- Slug: prefer caller-provided, else derive from email local-part
    v_slug := COALESCE(
        NULLIF(trim(p_slug), ''),
        regexp_replace(lower(split_part(p_email, '@', 1)), '[^a-z0-9-]+', '-', 'g')
    );
    -- Ensure uniqueness
    IF EXISTS (SELECT 1 FROM public.tenants WHERE slug = v_slug) THEN
        v_slug := v_slug || '-' || substr(p_auth_user_id::text, 1, 8);
    END IF;

    INSERT INTO public.tenants (slug, name, plan_tier, purchase_status)
    VALUES (v_slug, p_brand, 'starter', 'pending')
    RETURNING id INTO v_tenant_id;

    INSERT INTO public.user_profiles (
        auth_user_id, email, full_name, display_name, brand, role,
        tenant_id, agents_enabled, primary_agent
    )
    VALUES (
        p_auth_user_id, p_email, p_full_name, split_part(p_full_name, ' ', 1),
        p_brand, 'operator', v_tenant_id,
        ARRAY['bravo']::text[], 'bravo'
    )
    RETURNING id INTO v_profile_id;

    RETURN jsonb_build_object(
        'tenant_id', v_tenant_id,
        'profile_id', v_profile_id,
        'slug', v_slug
    );
END;
$$;

COMMIT;
