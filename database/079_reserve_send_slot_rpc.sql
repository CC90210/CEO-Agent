-- 079_reserve_send_slot_rpc.sql
--
-- Atomic send-slot reservation as a dedicated RPC. Replaces the raw-SQL
-- CTE that send_gateway._try_reserve_slot_via_rpc has been trying to
-- run through exec_sql since migration 013 hardened that wrapper to
-- forbid data-modifying CTEs nested inside its SELECT shell. As a
-- result the RPC path has been silently erroring for months, falling
-- through to send_gateway.reserve_send_slot() which has NO advisory
-- lock and NO existing-row check — two concurrent sends to the same
-- (lead_id, channel) can both win the reservation and double-send.
--
-- This function uses pg_try_advisory_xact_lock to serialize concurrent
-- requests for the same (lead_id, channel) pair, then checks for any
-- "reserving" row created within RESERVATION_WINDOW minutes. If the
-- lock can't be acquired, returns lock_acquired=false so the caller
-- can decide what to do (today's caller treats both lock-miss and
-- existing-row as "blocked").
--
-- Returns a JSONB object the Python caller normalizes:
--   {
--     "lock_acquired": bool,
--     "existing_id": uuid | null,
--     "reservation_id": uuid | null,   -- present when a fresh INSERT happened
--     "reservation_created_at": timestamptz | null
--   }
--
-- SECURITY DEFINER so the service-role caller can use it; the function
-- only touches public.lead_interactions which is already service-role-
-- accessible. No tenant filter needed at this layer — the caller
-- already resolved tenant_id when picking lead_id.

CREATE OR REPLACE FUNCTION public.reserve_send_slot(
    p_lead_id uuid,
    p_channel text,
    p_subject text,
    p_content_preview text,
    p_agent_source text,
    p_cooldown_until timestamptz,
    p_metadata jsonb,
    p_window_minutes int,
    p_actor_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_lock_key bigint;
    v_lock_acquired boolean;
    v_existing_id uuid;
    v_new_id uuid;
    v_new_created_at timestamptz;
BEGIN
    -- Hash (lead_id, channel) into a stable advisory-lock key. Two
    -- concurrent requests for the same pair contend; different pairs
    -- never block each other.
    v_lock_key := hashtext(p_lead_id::text || '|' || p_channel);
    v_lock_acquired := pg_try_advisory_xact_lock(v_lock_key);

    IF NOT v_lock_acquired THEN
        RETURN jsonb_build_object(
            'lock_acquired', false,
            'existing_id', NULL,
            'reservation_id', NULL,
            'reservation_created_at', NULL
        );
    END IF;

    -- Within the reservation window, has another reservation already
    -- landed for this (lead, channel) pair? If yes, return it as the
    -- existing reservation so the caller can dedupe.
    SELECT id INTO v_existing_id
      FROM public.lead_interactions
     WHERE lead_id = p_lead_id
       AND channel = p_channel
       AND type = 'reserving'
       AND created_at >= now() - make_interval(mins => p_window_minutes)
     ORDER BY created_at DESC
     LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        RETURN jsonb_build_object(
            'lock_acquired', true,
            'existing_id', v_existing_id,
            'reservation_id', NULL,
            'reservation_created_at', NULL
        );
    END IF;

    -- Insert a fresh reservation. actor_user_id may be NULL for system
    -- sends (drips, reconcilers); migration 078's FK to auth.users
    -- handles that gracefully.
    INSERT INTO public.lead_interactions (
        lead_id, type, channel, created_at, subject, content,
        agent_source, cooldown_until, metadata, actor_user_id
    )
    VALUES (
        p_lead_id, 'reserving', p_channel, now(),
        left(coalesce(p_subject, ''), 500),
        left(coalesce(p_content_preview, ''), 1000),
        p_agent_source,
        p_cooldown_until,
        coalesce(p_metadata, '{}'::jsonb),
        p_actor_user_id
    )
    RETURNING id, created_at INTO v_new_id, v_new_created_at;

    RETURN jsonb_build_object(
        'lock_acquired', true,
        'existing_id', NULL,
        'reservation_id', v_new_id,
        'reservation_created_at', v_new_created_at
    );
END;
$$;

COMMENT ON FUNCTION public.reserve_send_slot(
    uuid, text, text, text, text, timestamptz, jsonb, int, uuid
) IS
  'Atomic send-slot reservation. Replaces the broken exec_sql-wrapped '
  'CTE path. Returns lock_acquired/existing_id/reservation_id JSONB. '
  'Called from scripts/integrations/send_gateway.py.';
