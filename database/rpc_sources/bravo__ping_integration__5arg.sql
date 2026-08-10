-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: ping_integration(p_profile_id uuid, p_service text, p_status text, p_error text, p_metadata jsonb)
CREATE OR REPLACE FUNCTION public.ping_integration(p_profile_id uuid, p_service text, p_status text DEFAULT 'healthy'::text, p_error text DEFAULT NULL::text, p_metadata jsonb DEFAULT '{}'::jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_tenant_id uuid;
BEGIN
    v_tenant_id := public.resolve_tenant_for_profile(p_profile_id);
    INSERT INTO public.integrations_health (tenant_id, profile_id, service, status, last_ping_at, last_error, metadata)
    VALUES (v_tenant_id, p_profile_id, p_service, p_status, now(), p_error, p_metadata)
    ON CONFLICT (profile_id, service) DO UPDATE
    SET tenant_id = COALESCE(EXCLUDED.tenant_id, public.integrations_health.tenant_id),
        status = EXCLUDED.status,
        last_ping_at = now(),
        last_error = EXCLUDED.last_error,
        metadata = EXCLUDED.metadata,
        updated_at = now();
END;
$function$
