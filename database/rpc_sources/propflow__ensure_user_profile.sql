CREATE OR REPLACE FUNCTION public.ensure_user_profile()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  auth_user_record auth.users%ROWTYPE;
  new_company_id uuid;
BEGIN
  IF auth.uid() IS NULL THEN
    RETURN jsonb_build_object('status', 'error', 'message', 'Not authenticated');
  END IF;

  IF EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid()) THEN
    RETURN jsonb_build_object('status', 'success', 'message', 'Profile already exists');
  END IF;

  SELECT * INTO auth_user_record FROM auth.users WHERE id = auth.uid();
  INSERT INTO public.companies (name, email)
  VALUES (COALESCE(NULLIF(auth_user_record.raw_user_meta_data->>'company_name', ''), 'My Company'), lower(auth_user_record.email))
  RETURNING id INTO new_company_id;

  INSERT INTO public.profiles (id, company_id, email, full_name, job_title, role)
  VALUES (
    auth_user_record.id,
    new_company_id,
    lower(auth_user_record.email),
    COALESCE(NULLIF(auth_user_record.raw_user_meta_data->>'full_name', ''), split_part(auth_user_record.email, '@', 1)),
    auth_user_record.raw_user_meta_data->>'job_title',
    'admin'
  );

  INSERT INTO public.automation_subscriptions (company_id, is_active, tier)
  VALUES (new_company_id, true, 'professional');

  RETURN jsonb_build_object('status', 'success', 'message', 'Profile created');
END;
$function$
