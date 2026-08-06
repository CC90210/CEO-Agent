CREATE OR REPLACE FUNCTION public.accept_invitation_manually(token_input text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  invite_record public.team_invitations%ROWTYPE;
BEGIN
  IF auth.uid() IS NULL THEN RETURN false; END IF;

  SELECT * INTO invite_record FROM public.team_invitations
  WHERE token = token_input AND status = 'pending' AND expires_at > now()
  LIMIT 1;

  IF invite_record.id IS NULL OR lower(invite_record.email) <> lower(auth.email()) THEN
    RETURN false;
  END IF;

  PERFORM set_config('propflow.trusted_profile_update', 'on', true);
  UPDATE public.profiles
  SET company_id = invite_record.company_id, role = invite_record.role, updated_at = now()
  WHERE id = auth.uid();
  PERFORM set_config('propflow.trusted_profile_update', 'off', true);

  UPDATE public.team_invitations
  SET status = 'accepted', accepted_at = now(), accepted_by = auth.uid(), updated_at = now()
  WHERE id = invite_record.id;
  RETURN true;
END;
$function$
