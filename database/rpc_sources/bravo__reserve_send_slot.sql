CREATE OR REPLACE FUNCTION public.reserve_send_slot(p_lead_id uuid, p_channel text, p_subject text, p_content_preview text, p_agent_source text, p_cooldown_until timestamp with time zone, p_metadata jsonb, p_window_minutes integer, p_actor_user_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$
