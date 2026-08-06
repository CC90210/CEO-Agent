CREATE OR REPLACE FUNCTION public.reap_stale_walkthrough_jobs()
 RETURNS TABLE(job_id uuid, prev_status text, age_minutes integer)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
  RETURN QUERY
  WITH stale AS (
    SELECT id, status, extract(epoch FROM (now() - COALESCE(started_at, created_at)))::integer / 60 AS age
    FROM public.walkthrough_jobs
    WHERE status IN ('uploading', 'queued', 'training')
      AND COALESCE(started_at, created_at) < now() - interval '1 hour'
    FOR UPDATE
  ), updated AS (
    UPDATE public.walkthrough_jobs j
    SET status = 'failed', error_message = COALESCE(j.error_message, 'Walkthrough job timed out'), completed_at = now(), updated_at = now()
    FROM stale s WHERE j.id = s.id
    RETURNING j.id, s.status, s.age
  )
  SELECT * FROM updated;
END;
$function$
