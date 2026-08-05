CREATE OR REPLACE FUNCTION public.record_inbound_from_n8n_v2(p_profile_id uuid, p_secret_hash text, p_from_email text, p_subject text, p_body text, p_classification jsonb, p_received_at timestamp with time zone DEFAULT now())
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_secret_valid     boolean;
    v_tenant_id        uuid;
    v_lead_id          uuid;
    v_interaction_id   uuid;
BEGIN
    -- Auth: validate secret hash (now also matches tenant_id implicitly via profile)
    SELECT EXISTS (
        SELECT 1 FROM public.n8n_webhook_secrets
        WHERE profile_id = p_profile_id
          AND secret_hash = p_secret_hash
          AND revoked_at IS NULL
    ) INTO v_secret_valid;
    IF NOT v_secret_valid THEN
        RAISE EXCEPTION 'invalid_n8n_secret' USING ERRCODE = '42501';
    END IF;

    -- Resolve tenant from profile
    v_tenant_id := public.resolve_tenant_for_profile(p_profile_id);
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant' USING ERRCODE = '22023';
    END IF;

    -- Bump secret usage
    UPDATE public.n8n_webhook_secrets
    SET last_used_at = now(), use_count = use_count + 1
    WHERE profile_id = p_profile_id AND secret_hash = p_secret_hash;

    -- Find or create the lead, scoped to tenant
    SELECT id INTO v_lead_id
    FROM public.leads
    WHERE lower(email) = lower(p_from_email) AND tenant_id = v_tenant_id
    LIMIT 1;

    IF v_lead_id IS NULL THEN
        INSERT INTO public.leads (tenant_id, email, name, status, source, score)
        VALUES (v_tenant_id, p_from_email, split_part(p_from_email, '@', 1), 'new', 'n8n_inbound', 50)
        RETURNING id INTO v_lead_id;
    END IF;

    -- Record the interaction with tenant_id
    INSERT INTO public.lead_interactions (
        tenant_id, lead_id, type, channel, subject, content, agent_source, metadata, created_at
    ) VALUES (
        v_tenant_id,
        v_lead_id,
        'email_received',
        'email',
        p_subject,
        p_body,
        'n8n',
        jsonb_build_object(
            'from_identity', p_from_email,
            'classification', p_classification,
            'profile_id', p_profile_id
        ),
        p_received_at
    )
    RETURNING id INTO v_interaction_id;

    -- Bump health for this tenant
    INSERT INTO public.integrations_health (tenant_id, profile_id, service, status, last_ping_at)
    VALUES (v_tenant_id, p_profile_id, 'n8n_inbound', 'healthy', now())
    ON CONFLICT (profile_id, service) DO UPDATE
    SET tenant_id = EXCLUDED.tenant_id,
        status = 'healthy',
        last_ping_at = now(),
        last_error = NULL,
        updated_at = now();

    RETURN v_interaction_id;
END;
$function$
