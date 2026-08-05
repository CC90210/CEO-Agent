CREATE OR REPLACE FUNCTION public.patch_tenant_record_data(p_id uuid, p_tenant_id uuid, p_patch jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_new_data jsonb;
BEGIN
    IF p_patch IS NULL OR jsonb_typeof(p_patch) <> 'object' THEN
        RAISE EXCEPTION 'p_patch must be a non-null jsonb object' USING ERRCODE = '22023';
    END IF;

    UPDATE public.tenant_records
       SET data = COALESCE(data, '{}'::jsonb) || p_patch,
           updated_at = now()
     WHERE id = p_id
       AND tenant_id = p_tenant_id
     RETURNING data
       INTO v_new_data;

    IF v_new_data IS NULL THEN
        RAISE EXCEPTION 'lead_not_found_or_wrong_tenant: id=%, tenant=%', p_id, p_tenant_id
            USING ERRCODE = '02000';
    END IF;

    RETURN v_new_data;
END;
$function$
