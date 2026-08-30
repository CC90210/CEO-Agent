CREATE OR REPLACE FUNCTION public.record_tenant_cron_run(p_job_id uuid, p_tenant_id uuid, p_status text, p_output text, p_error text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$
