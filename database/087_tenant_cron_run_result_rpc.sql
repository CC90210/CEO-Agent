-- 087_tenant_cron_run_result_rpc.sql
--
-- Atomic single-statement update for the cron poll's "report a run
-- result" path. The current dashboard code does:
--
--   SELECT run_count → add 1 in JS → UPDATE
--
-- Three round trips, no locking — two concurrent bridges paired to
-- the same tenant racing the same job ID would both read the same
-- run_count and both write the same incremented value, losing one.
-- Today's invariant is one bridge per tenant, so the race is latent;
-- the moment multi-machine pairing lands (already supported by
-- bridge_lock.py on the daemon side), this becomes a real bug.
--
-- This function does the whole thing in one statement with the
-- increment inside the SET clause. Tenant scope enforced inline so
-- the function can't be tricked into bumping rows that don't belong
-- to the caller's bridge.

CREATE OR REPLACE FUNCTION public.record_tenant_cron_run(
    p_job_id uuid,
    p_tenant_id uuid,
    p_status text,
    p_output text,
    p_error text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_new_count integer;
BEGIN
  IF p_status NOT IN ('success', 'error') THEN
    RETURN jsonb_build_object('ok', false, 'error', 'invalid_status');
  END IF;

  UPDATE public.tenant_cron_jobs
     SET last_run_at = now(),
         last_run_status = p_status,
         last_run_output = p_output,
         last_run_error = p_error,
         run_count = COALESCE(run_count, 0) + 1
   WHERE id = p_job_id
     AND tenant_id = p_tenant_id
   RETURNING run_count INTO v_new_count;

  IF v_new_count IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'error', 'job_not_found_or_other_tenant');
  END IF;
  RETURN jsonb_build_object('ok', true, 'run_count', v_new_count);
END;
$$;

COMMENT ON FUNCTION public.record_tenant_cron_run(uuid, uuid, text, text, text) IS
  'Atomic cron-run result recorder. Used by /api/cron-jobs/poll to '
  'replace the non-atomic SELECT-then-UPDATE pattern that races under '
  'multi-machine bridge pairing.';
