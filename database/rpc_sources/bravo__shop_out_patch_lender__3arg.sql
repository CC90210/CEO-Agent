-- Extracted from Supabase project phctllmtsogkovoilwos before cancellation.
-- Signature: shop_out_patch_lender(p_round_id uuid, p_lender_id text, p_patch jsonb)
CREATE OR REPLACE FUNCTION public.shop_out_patch_lender(p_round_id uuid, p_lender_id text, p_patch jsonb)
 RETURNS shopping_threads
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_idx int;
    v_row public.shopping_threads;
    v_tenant uuid;
BEGIN
    -- Authorization. Only service-role bypasses the tenant check.
    -- Anon (logged-out) MUST be blocked; authenticated users must be
    -- members of the round's tenant.
    IF auth.role() <> 'service_role' THEN
        IF auth.uid() IS NULL THEN
            -- Anon role; no authentication. Refuse.
            RETURN NULL;
        END IF;
        SELECT tenant_id INTO v_tenant
          FROM public.shopping_threads
         WHERE id = p_round_id;
        IF v_tenant IS NULL THEN
            RETURN NULL;  -- round doesn't exist; same shape as miss
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.user_profiles
             WHERE auth_user_id = auth.uid()
               AND tenant_id = v_tenant
        ) THEN
            RETURN NULL;  -- cross-tenant; indistinguishable from miss
        END IF;
    END IF;

    SELECT idx - 1
      INTO v_idx
      FROM public.shopping_threads st,
           jsonb_array_elements(st.lenders) WITH ORDINALITY AS x(elem, idx)
     WHERE st.id = p_round_id
       AND elem->>'lender_id' = p_lender_id
     LIMIT 1;

    IF v_idx IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE public.shopping_threads
       SET lenders = jsonb_set(
                lenders,
                ARRAY[v_idx::text],
                COALESCE(lenders->v_idx, '{}'::jsonb) || p_patch,
                false
            ),
           updated_at = now()
     WHERE id = p_round_id
     RETURNING * INTO v_row;

    RETURN v_row;
END;
$function$
