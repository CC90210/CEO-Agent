CREATE OR REPLACE FUNCTION public.materialize_today_plan(p_profile_id uuid, p_target_date date DEFAULT NULL::date)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_target_date    date;
    v_dow            int;
    v_kind           text;
    v_template       record;
    v_tenant_id      uuid;
    v_plan_id        uuid;
BEGIN
    v_target_date := COALESCE(p_target_date, current_date);
    v_dow         := EXTRACT(DOW FROM v_target_date);
    v_kind        := CASE WHEN v_dow IN (0, 6) THEN 'weekend' ELSE 'weekday' END;

    SELECT tenant_id INTO v_tenant_id FROM public.user_profiles WHERE id = p_profile_id;
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant_id' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_template
    FROM public.plan_templates
    WHERE profile_id = p_profile_id AND kind = v_kind AND enabled = true
    LIMIT 1;

    -- Atomic insert-or-no-op. ON CONFLICT DO NOTHING returns no row
    -- when the unique constraint blocks the insert; the follow-up
    -- SELECT then fetches the existing plan_id. Net effect: every
    -- caller gets back a real id, no caller sees a duplicate-key error.
    INSERT INTO public.daily_plans (
        tenant_id, profile_id, plan_date, mission,
        target_calls, target_emails, target_bookings, schedule
    )
    VALUES (
        v_tenant_id, p_profile_id, v_target_date,
        COALESCE(v_template.mission, 'Daily ops'),
        COALESCE(v_template.target_calls, 0),
        COALESCE(v_template.target_emails, 0),
        COALESCE(v_template.target_bookings, 1),
        COALESCE(v_template.schedule, '[]'::jsonb)
    )
    ON CONFLICT (profile_id, plan_date) DO NOTHING
    RETURNING id
    INTO v_plan_id;

    IF v_plan_id IS NULL THEN
        SELECT id INTO v_plan_id
        FROM public.daily_plans
        WHERE profile_id = p_profile_id AND plan_date = v_target_date;
    END IF;

    RETURN v_plan_id;
END;
$function$
