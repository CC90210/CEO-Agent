CREATE OR REPLACE FUNCTION public.get_platform_metrics()
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  SELECT CASE WHEN public.current_user_is_super_admin() THEN jsonb_build_object(
    'total_users', (SELECT count(*) FROM public.profiles),
    'total_companies', (SELECT count(*) FROM public.companies),
    'total_properties', (SELECT count(*) FROM public.properties),
    'total_applications', (SELECT count(*) FROM public.applications)
  ) ELSE NULL END;
$function$
