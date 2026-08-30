CREATE OR REPLACE FUNCTION public.increment_automation_counter(config_id uuid, is_success boolean)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
  UPDATE public.automation_configs
  SET total_executions = total_executions + 1,
      successful_executions = successful_executions + CASE WHEN is_success THEN 1 ELSE 0 END,
      last_execution_at = now(),
      updated_at = now()
  WHERE id = config_id
    AND (company_id = public.get_user_company_id() OR auth.role() = 'service_role');
END;
$function$
