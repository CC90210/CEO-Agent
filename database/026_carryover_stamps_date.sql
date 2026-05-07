-- 026_carryover_stamps_date.sql
--
-- materialize_today_plan already auto-detects unfinished items and tags them
-- intensity='carryover'. Now also stamp carried_from_date so the UI can show
-- "carried from 2026-05-04" instead of always saying "yesterday" — useful
-- when the operator skips multiple days and the carryover chain stretches.
--
-- Apply with: python scripts/apply_migration.py database/026_carryover_stamps_date.sql

BEGIN;

CREATE OR REPLACE FUNCTION public.materialize_today_plan(
    p_profile_id  uuid,
    p_target_date date DEFAULT NULL
)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_target_date    date;
    v_dow            int;
    v_kind           text;
    v_template       record;
    v_yesterday_plan record;
    v_carryover      jsonb := '[]'::jsonb;
    v_final_schedule jsonb;
    v_tenant_id      uuid;
    v_plan_id        uuid;
    v_carried_from   date;
BEGIN
    v_target_date := COALESCE(p_target_date, current_date);
    v_dow := EXTRACT(DOW FROM v_target_date);
    v_kind := CASE WHEN v_dow IN (0, 6) THEN 'weekend' ELSE 'weekday' END;

    SELECT tenant_id INTO v_tenant_id FROM public.user_profiles WHERE id = p_profile_id;
    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'profile has no tenant_id' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_template
    FROM public.plan_templates
    WHERE profile_id = p_profile_id AND kind = v_kind AND enabled = true
    LIMIT 1;

    SELECT * INTO v_yesterday_plan
    FROM public.daily_plans
    WHERE profile_id = p_profile_id
      AND plan_date = v_target_date - INTERVAL '1 day'
    LIMIT 1;

    IF v_yesterday_plan.id IS NOT NULL AND jsonb_array_length(COALESCE(v_yesterday_plan.schedule, '[]'::jsonb)) > 0 THEN
        v_carried_from := v_yesterday_plan.plan_date;
        -- Tag each carryover with intensity + carried_from_date so the UI
        -- can render "carried from 2026-05-04" instead of always "yesterday".
        -- Reset completed/completed_at so the operator gets a fresh checkbox.
        SELECT COALESCE(
            jsonb_agg(
                b
                || jsonb_build_object(
                    'intensity', 'carryover',
                    'carried_from_date', v_carried_from::text,
                    'completed', false,
                    'completed_at', NULL
                )
            ),
            '[]'::jsonb
        )
        INTO v_carryover
        FROM jsonb_array_elements(v_yesterday_plan.schedule) b
        WHERE COALESCE(b->>'completed', 'false')::boolean = false
          AND COALESCE(b->>'intensity', '') <> 'break';
    END IF;

    v_final_schedule := COALESCE(v_carryover, '[]'::jsonb)
                     || COALESCE(v_template.schedule, '[]'::jsonb);

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
        v_final_schedule
    )
    ON CONFLICT (profile_id, plan_date) DO UPDATE
    SET schedule = EXCLUDED.schedule,
        mission = EXCLUDED.mission,
        target_calls = EXCLUDED.target_calls,
        target_emails = EXCLUDED.target_emails,
        target_bookings = EXCLUDED.target_bookings,
        updated_at = now()
    RETURNING id INTO v_plan_id;

    RETURN v_plan_id;
END;
$$;

COMMIT;
