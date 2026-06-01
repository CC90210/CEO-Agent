-- ============================================================================
-- Migration 089 — shopping_threads bugfixes from adversarial review
--
-- Two real bugs in migration 088, both dormant until specific actions:
--
-- 1. agent_user_id was NOT NULL with ON DELETE SET NULL — Postgres accepts
--    that DDL but the FK action would violate the NOT NULL when an auth
--    user is removed, blocking the DELETE. Drop NOT NULL so historical
--    rounds survive a departed employee.
--
-- 2. Add a Postgres RPC for atomic per-lender status patches. The CLI
--    tracker today does read-modify-write on the lenders[] jsonb, which
--    races between concurrent operators (the classifier daemon + a human
--    manual update at the same time can lose changes). The RPC does
--    jsonb_set inside one statement so the update is atomic at the row.
--
-- 3. Add a Postgres RPC for the round_number increment so two operators
--    triggering rounds for the same lead don't both compute N+1 and trip
--    the UNIQUE constraint with an ugly error. The RPC takes an advisory
--    lock keyed on (tenant, lead) so the second caller waits + gets N+2.
--
-- Idempotent. Re-runnable.
-- ============================================================================

ALTER TABLE public.shopping_threads
    ALTER COLUMN agent_user_id DROP NOT NULL;


-- shop_out_patch_lender — atomic per-lender status update.
--
-- Caller supplies the round id, the lender id (string match against
-- lenders[].lender_id), and a patch JSONB that gets MERGED into the
-- matching element. Returns the updated row.
--
-- jsonb_set with a single statement is atomic at the row level, so
-- concurrent calls for different lenders in the same round serialize
-- without either losing their write.
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

    IF v_idx IS NULL THEN
        RAISE EXCEPTION 'lender % not in round %', p_lender_id, p_round_id
            USING ERRCODE = 'no_data_found';
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

COMMENT ON FUNCTION public.shop_out_patch_lender IS
  'Atomic per-lender status patch on shopping_threads.lenders. Avoids the '
  'read-modify-write race the CLI tracker would otherwise hit when the '
  'classifier daemon and a manual operator update arrive concurrently.';


-- shop_out_next_round_number — increment round_number under advisory lock.
--
-- Two operators kicking off rounds for the same lead at the same time
-- previously both computed N+1 → second insert fails UNIQUE. The RPC
-- serializes the read+increment on a (tenant, lead) advisory lock so
-- the second caller waits and gets the right N+2.
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
    -- 64-bit advisory lock key derived from (tenant, lead). The hash
    -- collision space is large enough for the SunBiz scale; if
    -- collisions become a problem we'd switch to a (key1, key2) lock.
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

COMMENT ON FUNCTION public.shop_out_next_round_number IS
  'Race-free round_number increment for shop_out. Advisory lock keyed on '
  '(tenant, lead) so concurrent rounds for the same lead serialize.';
