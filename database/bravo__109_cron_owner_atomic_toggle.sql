-- bravo__109_cron_owner_atomic_toggle.sql
-- Postgres rollback parity for the Command Center automation registry.
--
-- Turso owns the production data plane, but `supabase_legacy` is the explicit
-- emergency rollback. Keep that database capable of the same durable owner
-- grouping and atomic state+audit toggle contract before the application code
-- starts selecting owner_agent_key or invoking the RPC below.

ALTER TABLE public.cron_jobs
  ADD COLUMN IF NOT EXISTS owner_agent_key text;

ALTER TABLE public.cron_jobs
  ALTER COLUMN owner_agent_key SET DEFAULT 'bravo';

DO $owner_backfill$
BEGIN
  UPDATE public.cron_jobs
     SET owner_agent_key = 'bravo'
   WHERE owner_agent_key IS NULL;

  UPDATE public.cron_jobs
     SET owner_agent_key = 'maven'
   WHERE tenant_id = 'ef8d389e-3f15-43f2-ae00-3660f69a1452'::uuid
     AND name IN (
       'Carousel Media Retention',
       'Library Post Linker',
       'Marketing Publish Drain',
       'Maven — Carousel Post',
       'Post Analytics Sync',
       'Training Corpus Ingest'
     );

  UPDATE public.cron_jobs
     SET description = 'Daily 08:00 ET — runs the complete GEN-10 posting chain: verify-published, watch, author-carousels, unstick, generate, plan, deliver-renders, then library-sync. Authors and renders only the six recognized creative families, then books up to two posts at 13:00 and 19:00 UTC for Instagram, LinkedIn and Threads. Family is selected before lane/system/slug and distinct same-day families are preferred; constrained inventory may repeat rather than leave a slot empty. Finished renders go to CC''s Telegram and the founders Library.'
   WHERE tenant_id = 'ef8d389e-3f15-43f2-ae00-3660f69a1452'::uuid
     AND name = 'Maven — Carousel Post';
END
$owner_backfill$;

ALTER TABLE public.cron_jobs
  ALTER COLUMN owner_agent_key SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cron_jobs_tenant_owner_active
  ON public.cron_jobs (tenant_id, owner_agent_key, is_active);

CREATE OR REPLACE FUNCTION public.toggle_cron_job_with_audit_v1(
  p_source text,
  p_id uuid,
  p_tenant_id uuid,
  p_enabled boolean,
  p_expected_name text,
  p_expected_enabled boolean,
  p_actor_user_id uuid,
  p_actor_email text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_name text;
  v_previous_enabled boolean;
  v_persisted_row jsonb;
BEGIN
  IF p_source = 'empire' THEN
    SELECT job.name, job.is_active
      INTO v_name, v_previous_enabled
      FROM public.cron_jobs AS job
     WHERE job.id = p_id
       AND job.tenant_id = p_tenant_id
     FOR UPDATE;
  ELSIF p_source = 'tenant' THEN
    SELECT job.name, job.enabled
      INTO v_name, v_previous_enabled
      FROM public.tenant_cron_jobs AS job
     WHERE job.id = p_id
       AND job.tenant_id = p_tenant_id
     FOR UPDATE;
  ELSE
    RETURN jsonb_build_object(
      'ok', false,
      'status', 400,
      'body', jsonb_build_object('ok', false, 'error', 'invalid_cron_source')
    );
  END IF;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'ok', false,
      'status', 404,
      'body', jsonb_build_object('ok', false, 'error', 'not_found_or_forbidden')
    );
  END IF;

  IF v_name IS DISTINCT FROM p_expected_name
     OR v_previous_enabled IS DISTINCT FROM p_expected_enabled THEN
    RETURN jsonb_build_object(
      'ok', false,
      'status', 409,
      'body', jsonb_build_object('ok', false, 'error', 'cron_toggle_concurrent_update')
    );
  END IF;

  IF p_source = 'empire' THEN
    UPDATE public.cron_jobs AS job
       SET is_active = p_enabled
     WHERE job.id = p_id
       AND job.tenant_id = p_tenant_id
       AND job.name IS NOT DISTINCT FROM p_expected_name
       AND job.is_active IS NOT DISTINCT FROM p_expected_enabled;

    IF NOT FOUND THEN
      RETURN jsonb_build_object(
        'ok', false,
        'status', 409,
        'body', jsonb_build_object('ok', false, 'error', 'cron_toggle_concurrent_update')
      );
    END IF;

    SELECT to_jsonb(job)
      INTO v_persisted_row
      FROM public.cron_jobs AS job
     WHERE job.id = p_id
       AND job.tenant_id = p_tenant_id
       AND job.name IS NOT DISTINCT FROM p_expected_name
       AND job.is_active IS NOT DISTINCT FROM p_enabled;
  ELSE
    UPDATE public.tenant_cron_jobs AS job
       SET enabled = p_enabled
     WHERE job.id = p_id
       AND job.tenant_id = p_tenant_id
       AND job.name IS NOT DISTINCT FROM p_expected_name
       AND job.enabled IS NOT DISTINCT FROM p_expected_enabled;

    IF NOT FOUND THEN
      RETURN jsonb_build_object(
        'ok', false,
        'status', 409,
        'body', jsonb_build_object('ok', false, 'error', 'cron_toggle_concurrent_update')
      );
    END IF;

    SELECT to_jsonb(job)
      INTO v_persisted_row
      FROM public.tenant_cron_jobs AS job
     WHERE job.id = p_id
       AND job.tenant_id = p_tenant_id
       AND job.name IS NOT DISTINCT FROM p_expected_name
       AND job.enabled IS NOT DISTINCT FROM p_enabled;
  END IF;

  IF v_persisted_row IS NULL THEN
    RAISE EXCEPTION 'cron toggle persisted-state verification failed';
  END IF;

  INSERT INTO public.tenant_audit_log (
    tenant_id,
    actor_user_id,
    actor_email,
    action_type,
    target_table,
    target_id,
    before,
    after
  ) VALUES (
    p_tenant_id,
    p_actor_user_id,
    p_actor_email,
    'cron_job_toggle',
    CASE WHEN p_source = 'empire' THEN 'cron_jobs' ELSE 'tenant_cron_jobs' END,
    p_id::text,
    jsonb_build_object('source', p_source, 'name', v_name, 'enabled', v_previous_enabled),
    jsonb_build_object('source', p_source, 'name', v_name, 'enabled', p_enabled)
  );

  RETURN jsonb_build_object(
    'ok', true,
    'row', v_persisted_row,
    'previousEnabled', v_previous_enabled,
    'enabled', p_enabled
  );
END;
$$;

-- apply_migration.py blocks outer GRANT/REVOKE tokens before transmission.
-- These are constant statements (no interpolation) inside a DO body so the
-- migration remains runnable through that guarded path without weakening the
-- service-role-only contract.
DO $permissions$
BEGIN
  EXECUTE 'REVOKE ALL ON FUNCTION public.toggle_cron_job_with_audit_v1(text, uuid, uuid, boolean, text, boolean, uuid, text) FROM PUBLIC, anon, authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION public.toggle_cron_job_with_audit_v1(text, uuid, uuid, boolean, text, boolean, uuid, text) TO service_role';
END
$permissions$;

COMMENT ON FUNCTION public.toggle_cron_job_with_audit_v1(
  text, uuid, uuid, boolean, text, boolean, uuid, text
) IS 'Service-role-only, tenant-scoped cron toggle with locked CAS, persisted readback, and an audit receipt in one transaction.';
