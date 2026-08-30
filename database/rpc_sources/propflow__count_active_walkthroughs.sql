CREATE OR REPLACE FUNCTION public.count_active_walkthroughs(p_company_id uuid)
 RETURNS integer
 LANGUAGE sql
 STABLE
 SET search_path TO 'public'
AS $function$
  SELECT count(*)::integer FROM public.walkthrough_jobs
  WHERE company_id = p_company_id AND status IN ('uploading', 'queued', 'training');
$function$
