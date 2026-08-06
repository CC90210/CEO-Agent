CREATE OR REPLACE FUNCTION public.ensure_user_profile_admin(u_id uuid, u_email text, f_name text, c_name text, j_title text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  new_company_id uuid;
BEGIN
  IF EXISTS (SELECT 1 FROM public.profiles WHERE id = u_id) THEN
    RETURN jsonb_build_object('status', 'success', 'message', 'Profile already exists');
  END IF;

  INSERT INTO public.companies (name, email)
  VALUES (COALESCE(NULLIF(c_name, ''), 'My Company'), lower(u_email))
  RETURNING id INTO new_company_id;

  INSERT INTO public.profiles (id, company_id, email, full_name, job_title, role)
  VALUES (u_id, new_company_id, lower(u_email), COALESCE(NULLIF(f_name, ''), 'New User'), j_title, 'admin');

  INSERT INTO public.automation_subscriptions (company_id, is_active, tier)
  VALUES (new_company_id, true, 'professional');

  RETURN jsonb_build_object('status', 'success', 'message', 'Profile created');
EXCEPTION WHEN OTHERS THEN
  RETURN jsonb_build_object('status', 'error', 'message', 'Profile initialization failed');
END;
$function$
