CREATE OR REPLACE FUNCTION public.get_invitation_by_token(token_input text)
 RETURNS TABLE(id uuid, email text, role text, company_id uuid, company_name text, company_logo_url text, status text)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  SELECT ti.id, ti.email, ti.role, ti.company_id, c.name, c.logo_url, ti.status
  FROM public.team_invitations ti
  JOIN public.companies c ON c.id = ti.company_id
  WHERE ti.token = token_input AND ti.status = 'pending' AND ti.expires_at > now()
  LIMIT 1;
$function$
