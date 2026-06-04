-- 094_cron_jobs_rls.sql
--
-- cron_jobs got a tenant_id column in migration 084, but RLS was never enabled
-- on the table. Combined with Supabase's default GRANT to `authenticated`, any
-- logged-in user could SELECT every empire cron row directly via the Supabase
-- client (schedule strings, last_result, action payloads) — bypassing the API
-- routes entirely. cron_jobs is CC's EMPIRE table (per 084, all rows belong to
-- CC's empire tenant); SunBiz's crons live in tenant_cron_jobs. So a tenant-
-- scoped SELECT policy correctly hides empire crons from SunBiz users.
--
-- Strategy mirrors 081_rls_close_open_tables.sql (agent_events):
--   - Enable RLS.
--   - SELECT scoped to the caller's tenant via user_profiles.
--   - No INSERT/UPDATE/DELETE policies → default-deny for anon + authenticated.
--     Every writer today is service-role (cron_engine.py) and bypasses RLS.
--
-- Idempotent: ENABLE RLS is a no-op if already on; the policy is created in an
-- exception-swallowing DO block so re-running is safe.

ALTER TABLE public.cron_jobs ENABLE ROW LEVEL SECURITY;

DO $policy$
BEGIN
  CREATE POLICY cron_jobs_tenant_select
    ON public.cron_jobs FOR SELECT
    TO authenticated
    USING (
      tenant_id IN (
        SELECT tenant_id
        FROM public.user_profiles
        WHERE auth_user_id = auth.uid()
      )
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $policy$;
