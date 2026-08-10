-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: shop_out_next_round_number(p_tenant_id uuid, p_lead_id text)
CREATE OR REPLACE FUNCTION public.shop_out_next_round_number(p_tenant_id uuid, p_lead_id text)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_lock_key bigint;
    v_next int;
BEGIN
    -- Authorization. Same model as shop_out_patch_lender.
    IF auth.role() <> 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'forbidden: authentication required'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.user_profiles
             WHERE auth_user_id = auth.uid()
               AND tenant_id = p_tenant_id
        ) THEN
            RAISE EXCEPTION 'forbidden: not a member of tenant %', p_tenant_id
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;

    v_lock_key := ('x' || substr(md5(p_tenant_id::text || '|' || p_lead_id), 1, 16))::bit(64)::bigint;
    PERFORM pg_advisory_xact_lock(v_lock_key);

    SELECT COALESCE(MAX(round_number), 0) + 1
      INTO v_next
      FROM public.shopping_threads
     WHERE tenant_id = p_tenant_id
       AND lead_id = p_lead_id;

    RETURN v_next;
END;
$function$
