-- ============================================================================
-- Migration 077 — harden user_integration_credentials RLS write policies
--
-- Codex adversarial review of 076 (2026-05-29) flagged that the INSERT /
-- UPDATE / DELETE policies only checked user_id = auth.uid() and not
-- tenant membership. A logged-in user could (in theory) write Gmail
-- OAuth rows under any tenant_id they guessed — they'd be attaching
-- their OWN tokens to a tenant they don't belong to. The Settings UI
-- write path uses the service-role Node API which bypasses RLS, so the
-- exploit was theoretical, but defense-in-depth says the policy should
-- enforce tenant membership directly.
--
-- Also tightens the SELECT policy: instead of granting any "owner" rows
-- visibility, we keep it strictly self-only. Admin/support visibility
-- would belong in a separate elevated read path, not the RLS default —
-- pulling encrypted blobs back to a non-owner has no operational value
-- and increases the blast radius of any future leak.
--
-- Idempotent. Re-runnable.
-- ============================================================================

DROP POLICY IF EXISTS user_integration_credentials_self_select ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_select
    ON public.user_integration_credentials FOR SELECT
    USING (
        user_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.user_profiles up
             WHERE up.auth_user_id = auth.uid()
               AND up.tenant_id = user_integration_credentials.tenant_id
        )
    );

DROP POLICY IF EXISTS user_integration_credentials_self_insert ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_insert
    ON public.user_integration_credentials FOR INSERT
    WITH CHECK (
        user_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.user_profiles up
             WHERE up.auth_user_id = auth.uid()
               AND up.tenant_id = user_integration_credentials.tenant_id
        )
    );

DROP POLICY IF EXISTS user_integration_credentials_self_update ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_update
    ON public.user_integration_credentials FOR UPDATE
    USING (
        user_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.user_profiles up
             WHERE up.auth_user_id = auth.uid()
               AND up.tenant_id = user_integration_credentials.tenant_id
        )
    )
    WITH CHECK (
        user_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.user_profiles up
             WHERE up.auth_user_id = auth.uid()
               AND up.tenant_id = user_integration_credentials.tenant_id
        )
    );

DROP POLICY IF EXISTS user_integration_credentials_self_delete ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_delete
    ON public.user_integration_credentials FOR DELETE
    USING (
        user_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.user_profiles up
             WHERE up.auth_user_id = auth.uid()
               AND up.tenant_id = user_integration_credentials.tenant_id
        )
    );
