-- ============================================================================
-- Migration 091 — tenant-membership guards on shop_out RPCs
--
-- 089 and 090 shipped two SECURITY DEFINER RPCs (shop_out_patch_lender,
-- shop_out_next_round_number) without any in-function authorization
-- check. Supabase grants EXECUTE on functions to PUBLIC by default, so
-- a logged-in user from a DIFFERENT tenant could call either RPC and
-- read or mutate state they shouldn't have access to:
--
--   * shop_out_patch_lender('<any round>', '<any lender>', '{"status":"approved"}')
--     would mutate another tenant's round, flipping a lender to
--     "approved" without authorization.
--
--   * shop_out_next_round_number('<any tenant>', '<any lead>') would
--     leak the current max round_number for any (tenant, lead) pair,
--     letting an outsider probe shopping activity.
--
-- This migration adds an auth.uid() membership check inside each RPC
-- body. Service-role callers (the bridge-side CLI) bypass the check
-- via auth.uid() IS NULL — service-role JWTs don't set the auth claim,
-- so the standard Supabase pattern is to treat NULL as "trusted
-- backend." If the caller is a regular user, we verify their
-- user_profiles row is in the target tenant before proceeding.
--
-- Threat model: an authenticated attacker in tenant A trying to read
-- or mutate tenant B's shop-out state via direct RPC call. Closed by
-- this migration.
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
    -- Tenant-membership check (skip for service-role, identified by
    -- auth.uid() returning NULL).
    IF auth.uid() IS NOT NULL THEN
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
            -- Cross-tenant attempt — return NULL (same shape as a
            -- not-found miss) so the caller cannot distinguish
            -- "round doesn't exist" from "you don't own it."
            RETURN NULL;
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
    -- Tenant-membership check (skip for service-role, identified by
    -- auth.uid() returning NULL).
    IF auth.uid() IS NOT NULL THEN
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
