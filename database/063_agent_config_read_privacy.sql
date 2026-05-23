-- ============================================================================
-- Migration 063 — agent_model_config per-user read privacy
--
-- Background:
-- ===========
-- Migration 052 added per-user override rows to agent_model_config and
-- tightened WRITES (only the row's owner can update / delete it; only
-- admins can write tenant defaults). But the SELECT policy
-- `amc_select_any` stayed permissive — every tenant member can read
-- every row in their tenant, including other employees' encrypted_api_key
-- ciphertexts, their provider/model choices, and their last_used_at
-- timestamps.
--
-- That was fine when the only tenant member was CC. With multi-employee
-- tenants (ADR-0006), it violates the stated requirement: "Whenever
-- someone inputs an API key, that's private to them, and it should
-- stay that way."
--
-- Threat model:
-- =============
-- AES-GCM encrypted keys can't be decrypted without
-- BRAVO_FIELD_ENCRYPTION_KEY (server-side env var). So Employee A can't
-- USE Employee B's key. But A CAN see:
--   * The ciphertext itself (defense-in-depth: don't expose secrets you
--     don't have to, even encrypted ones)
--   * The provider Employee B picked (privacy leak about B's tooling)
--   * The model selection (privacy leak)
--   * The last_used_at timestamp (when B chats)
--   * Whether B has an override at all (presence-leak)
--
-- Fix:
-- ====
-- Replace `amc_select_any` with `amc_select_own_and_default`:
--   * Tenant default rows (user_id IS NULL) — visible to every tenant
--     member (this is the workspace default the resolver falls back to).
--   * Per-user override rows (user_id IS NOT NULL) — visible only to
--     the owner OR to a tenant admin.
--
-- Resolver impact:
-- ================
-- `lib/chat-auth.ts:resolveChatContext` uses getServiceSupabase() which
-- bypasses RLS. The resolver continues to find the caller's override
-- row + the tenant default row identically. Zero functional regression.
--
-- Dashboard UI impact:
-- ====================
-- AgentConfigEditor + ProviderAccountsCard use the authenticated client
-- (RLS-enforced). After this migration:
--   * Employees see workspace defaults (same as before).
--   * Employees see their OWN overrides (same as before).
--   * Employees no longer see OTHER employees' overrides (closed leak).
--   * Admins see all rows (for support / audit).
-- No UI breakage expected.
--
-- Idempotent. Re-runnable.
-- ============================================================================

BEGIN;

DO $$
BEGIN
    -- Drop the existing permissive SELECT policy if present.
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_select_any'
    ) THEN
        DROP POLICY amc_select_any ON public.agent_model_config;
    END IF;

    -- Drop the V1 (migration 020) select policy too, in case it still
    -- exists in deployments that didn't run 052's drop block cleanly.
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_tenant_select'
    ) THEN
        DROP POLICY amc_tenant_select ON public.agent_model_config;
    END IF;

    -- New SELECT policy — tenant default rows visible to all tenant
    -- members; per-user override rows visible only to the owner or to
    -- a tenant admin.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_model_config'
          AND policyname='amc_select_own_and_default'
    ) THEN
        CREATE POLICY amc_select_own_and_default ON public.agent_model_config
            FOR SELECT TO authenticated
            USING (
                -- Always require the caller to be in the same tenant.
                tenant_id IN (
                    SELECT tenant_id FROM public.user_profiles
                    WHERE auth_user_id = auth.uid()
                )
                AND (
                    -- Tenant defaults — visible to every tenant member.
                    user_id IS NULL
                    -- The caller's own per-user override.
                    OR user_id = auth.uid()
                    -- Tenant admins can see all rows (for support /
                    -- audit). is_team_admin() is defined in migration 037.
                    OR public.is_team_admin()
                )
            );
    END IF;
END $$;

-- Quick verification query for the operator / migration runner.
-- Confirms the three intended visibility classes resolve correctly.
-- Comment out before running against production if you don't want
-- the test data left behind.
-- ----------------------------------------------------------------------
-- Expected when run as a non-admin tenant member:
--   own_overrides   >= 0
--   tenant_defaults >= 0
--   other_overrides == 0  (closed leak)
-- ----------------------------------------------------------------------
-- SELECT
--     COUNT(*) FILTER (WHERE user_id = auth.uid())                            AS own_overrides,
--     COUNT(*) FILTER (WHERE user_id IS NULL)                                  AS tenant_defaults,
--     COUNT(*) FILTER (WHERE user_id IS NOT NULL AND user_id != auth.uid())   AS other_overrides
-- FROM public.agent_model_config;

COMMIT;
