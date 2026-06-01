-- ============================================================================
-- Migration 092 — fix tenant-guard bypass on shop_out RPCs (CRITICAL)
--
-- Migration 091 added "tenant-membership check unless auth.uid() IS NULL"
-- to both RPCs. The intent was: service-role (the bridge CLI) bypasses
-- the check because service JWTs don't set the sub claim, so auth.uid()
-- returns NULL.
--
-- The bug: the ANON role ALSO has auth.uid() = NULL. An unauthenticated
-- attacker hitting the public PostgREST endpoint with the anon key
-- (which is public by design) hits the "bypass" branch and can:
--
--   * Probe shop_out_next_round_number(tenant, lead) across any tenant
--     -> leaks current max round_number for any (tenant, lead) pair.
--
--   * Call shop_out_patch_lender(<real round id>, <lender id>,
--     '{"status":"approved"}') and mutate a real round if they guess
--     or learn a round uuid.
--
-- Live attack simulation against the prod RPC with the anon key
-- confirmed both vectors before this migration. THIS IS A REAL EXPLOIT
-- closed by switching the bypass signal from auth.uid() IS NULL to
-- auth.role() = 'service_role' (the JWT role claim, which is "anon" /
-- "authenticated" / "service_role" depending on the calling JWT).
--
-- Idempotent. CREATE OR REPLACE FUNCTION; signatures unchanged.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.shop_out_patch_lender(
    p_round_id uuid,
    p_lender_id text,
    p_patch jsonb
) RETURNS public.shopping_threads
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
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
$$;


CREATE OR REPLACE FUNCTION public.shop_out_next_round_number(
    p_tenant_id uuid,
    p_lead_id text
) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
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
$$;
