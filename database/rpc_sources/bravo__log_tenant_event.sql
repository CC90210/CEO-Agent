CREATE OR REPLACE FUNCTION public.log_tenant_event(p_tenant_id uuid, p_action_type text, p_target_table text DEFAULT NULL::text, p_target_id text DEFAULT NULL::text, p_before jsonb DEFAULT NULL::jsonb, p_after jsonb DEFAULT NULL::jsonb, p_ip_hash text DEFAULT NULL::text, p_user_agent text DEFAULT NULL::text, p_metadata jsonb DEFAULT '{}'::jsonb)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_id uuid;
    v_actor_email text;
BEGIN
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'tenant_id required';
    END IF;

    IF auth.role() <> 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authenticated user required';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM public.user_profiles up
            WHERE up.auth_user_id = auth.uid()
              AND up.tenant_id = p_tenant_id
        ) THEN
            RAISE EXCEPTION 'cannot log audit events for another tenant';
        END IF;
    END IF;

    SELECT email INTO v_actor_email
    FROM auth.users
    WHERE id = auth.uid()
    LIMIT 1;

    INSERT INTO public.tenant_audit_log (
        tenant_id, actor_user_id, actor_email,
        action_type, target_table, target_id,
        before, after, ip_hash, user_agent, metadata
    ) VALUES (
        p_tenant_id, auth.uid(), v_actor_email,
        p_action_type, p_target_table, p_target_id,
        p_before, p_after, p_ip_hash, p_user_agent, COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$function$
