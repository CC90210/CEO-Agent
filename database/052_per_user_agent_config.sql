-- ============================================================================
-- Migration 052 — per-user agent config overrides
--
-- Phase B of the master multi-tenant infra plan (2026-05-17). Today
-- agent_model_config is UNIQUE on (tenant_id, agent_key), so every
-- employee on a tenant shares one provider key + one model per agent.
-- Goal: each employee can override their own key, model, and provider
-- while the tenant's default remains the fallback for anyone who
-- hasn't set their own.
--
-- Strategy:
--   - Add a nullable user_id column. NULL = tenant default row (every
--     employee falls back to it); non-NULL = that specific user's
--     override.
--   - Drop the old (tenant_id, agent_key) UNIQUE constraint and replace
--     with TWO partial unique indexes:
--       (tenant_id, agent_key) WHERE user_id IS NULL    — one default per agent
--       (tenant_id, agent_key, user_id) WHERE user_id IS NOT NULL — one override per (agent, user)
--   - Add an RLS policy so users can SELECT/INSERT/UPDATE/DELETE their
--     OWN rows. Admins keep their existing tenant-wide write power.
--
-- Resolver semantics (see lib/agent-resolver.ts shipping with this):
--   1. Look up (tenant_id, user_id, agent_key) — user override
--   2. Fall back to (tenant_id, agent_key, user_id=NULL) — tenant default
--   3. Fall back to bridge-mode if both are missing
--
-- Idempotent. Re-runnable.
-- ============================================================================

BEGIN;

-- 1. Add user_id column ----------------------------------------------------
ALTER TABLE public.agent_model_config
    ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_agent_model_config_user
    ON public.agent_model_config (tenant_id, user_id, agent_key)
    WHERE user_id IS NOT NULL;

-- 2. Replace the legacy (tenant_id, agent_key) UNIQUE -----------------------
-- The old constraint blocks insertion of per-user override rows. Drop it
-- if it exists, then add the two partial uniques.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.agent_model_config'::regclass
          AND conname = 'agent_model_config_tenant_id_agent_key_key'
    ) THEN
        ALTER TABLE public.agent_model_config
            DROP CONSTRAINT agent_model_config_tenant_id_agent_key_key;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_model_config_default_per_agent
    ON public.agent_model_config (tenant_id, agent_key)
    WHERE user_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_model_config_override_per_user
    ON public.agent_model_config (tenant_id, user_id, agent_key)
    WHERE user_id IS NOT NULL;

-- 3. RLS — users can read both their overrides AND the tenant default; --
-- they can WRITE only their own overrides. Admins (handled below) can
-- write tenant defaults. ----------------------------------------------------
DO $$
BEGIN
    -- Drop the legacy "amc_tenant_*" policies that gave every tenant
    -- member full write access. Replace with scoped versions below.
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_tenant_write'
    ) THEN
        DROP POLICY amc_tenant_write ON public.agent_model_config;
    END IF;

    -- amc_select_any: every tenant member can read every row in their
    -- tenant. This is necessary so the resolver can fall back to the
    -- tenant default after missing the user override.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_select_any'
    ) THEN
        CREATE POLICY amc_select_any ON public.agent_model_config
            FOR SELECT TO authenticated
            USING (
                tenant_id IN (
                    SELECT tenant_id FROM public.user_profiles
                    WHERE auth_user_id = auth.uid()
                )
            );
    END IF;

    -- amc_user_write: users can INSERT/UPDATE/DELETE their own override
    -- rows (user_id = auth.uid()) within their tenant.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_user_write'
    ) THEN
        CREATE POLICY amc_user_write ON public.agent_model_config
            FOR ALL TO authenticated
            USING (
                user_id = auth.uid()
                AND tenant_id IN (
                    SELECT tenant_id FROM public.user_profiles
                    WHERE auth_user_id = auth.uid()
                )
            )
            WITH CHECK (
                user_id = auth.uid()
                AND tenant_id IN (
                    SELECT tenant_id FROM public.user_profiles
                    WHERE auth_user_id = auth.uid()
                )
            );
    END IF;

    -- amc_admin_write: tenant admins can write tenant-default rows
    -- (user_id IS NULL). Uses the existing is_team_admin() helper from
    -- migration 037.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_admin_write'
    ) THEN
        CREATE POLICY amc_admin_write ON public.agent_model_config
            FOR ALL TO authenticated
            USING (
                user_id IS NULL
                AND tenant_id = public.current_tenant_id()
                AND public.is_team_admin()
            )
            WITH CHECK (
                user_id IS NULL
                AND tenant_id = public.current_tenant_id()
                AND public.is_team_admin()
            );
    END IF;
END $$;

-- 4. Convenience view — resolved-config per (tenant, user, agent) ---------
-- The resolver in lib/agent-resolver.ts could call this view instead of
-- two queries. Returns the user-override row if it exists, otherwise
-- the tenant default. NULL when neither exists (caller should fall
-- back to bridge mode).
CREATE OR REPLACE VIEW public.agent_model_resolved AS
WITH per_user AS (
    SELECT
        tenant_id,
        user_id,
        agent_key,
        provider,
        model,
        encrypted_api_key,
        system_prompt_override,
        enabled,
        'user' AS scope
    FROM public.agent_model_config
    WHERE user_id IS NOT NULL
),
per_tenant AS (
    SELECT
        tenant_id,
        NULL::uuid AS user_id,
        agent_key,
        provider,
        model,
        encrypted_api_key,
        system_prompt_override,
        enabled,
        'tenant' AS scope
    FROM public.agent_model_config
    WHERE user_id IS NULL
)
SELECT * FROM per_user
UNION ALL
SELECT * FROM per_tenant;

COMMIT;
