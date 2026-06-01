-- ============================================================================
-- Migration 090 — shop_out_patch_lender returns NULL on miss
--
-- The original 089 RPC used RAISE EXCEPTION when the lender wasn't in
-- the round. The Python tracker had to parse the exception MESSAGE
-- to distinguish "lender not in round" (expected miss, return clean
-- error to caller) from "real DB error" (re-raise). String-parsing
-- error messages is fragile — supabase-py wrapping or Postgres error
-- formatting can drift and the tracker silently regresses to
-- ugly RuntimeErrors instead of clean "lender_not_in_round" responses.
--
-- This migration replaces the RPC body with a RETURN NULL on miss
-- path. Python checks .data is null instead of parsing a string.
--
-- Idempotent. CREATE OR REPLACE FUNCTION is fine because the
-- signature is unchanged.
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
BEGIN
    SELECT idx - 1
      INTO v_idx
      FROM public.shopping_threads st,
           jsonb_array_elements(st.lenders) WITH ORDINALITY AS x(elem, idx)
     WHERE st.id = p_round_id
       AND elem->>'lender_id' = p_lender_id
     LIMIT 1;

    -- Miss path: return NULL so the caller can distinguish
    -- "lender_not_in_round" from a real exception via .data check
    -- instead of fragile error-string parsing.
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
