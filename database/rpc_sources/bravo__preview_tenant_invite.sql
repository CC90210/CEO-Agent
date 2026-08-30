CREATE OR REPLACE FUNCTION public.preview_tenant_invite(p_token_hash text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_invite public.tenant_invites%ROWTYPE;
    v_tenant_name text;
BEGIN
    SELECT * INTO v_invite
    FROM public.tenant_invites
    WHERE token_hash = p_token_hash
      AND redeemed_at IS NULL
      AND revoked_at IS NULL
      AND expires_at > now()
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT name INTO v_tenant_name
    FROM public.tenants
    WHERE id = v_invite.tenant_id;

    RETURN jsonb_build_object(
        'tenant_id', v_invite.tenant_id,
        'tenant_name', COALESCE(v_tenant_name, 'a workspace'),
        'team_role', v_invite.team_role,
        'expires_at', v_invite.expires_at,
        'email_pinned', v_invite.email
    );
END;
$function$
