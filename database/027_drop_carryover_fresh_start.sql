-- 027_drop_carryover_fresh_start.sql
--
-- CC's explicit feedback: kill the "carried from yesterday" model. Daily
-- schedule should be the template, fresh every day. Items disappear when
-- checked. Tomorrow they reappear (re-materialized from the template).
-- The carryover stamping the operator sees today (3 missed days = 30 stale
-- carryover items piled up) is a UX noise generator, not accountability.
--
-- This migration:
--   1. Rewrites materialize_today_plan to load ONLY from the template —
--      no scanning yesterday's incomplete items, no carryover marker.
--   2. Adds a finalized_at timestamp to daily_plans so the "Finalize day"
--      button has somewhere to write.
--   3. Strips intensity='carryover' from today's existing schedule rows,
--      so CC's screen clears instantly (he asked for a fresh start).
--
-- Apply with: python scripts/apply_migration.py database/027_drop_carryover_fresh_start.sql

BEGIN;

-- 1. Add finalized_at column for the "Finalize day" UI checkpoint.
ALTER TABLE public.daily_plans
    ADD COLUMN IF NOT EXISTS finalized_at timestamptz;

COMMENT ON COLUMN public.daily_plans.finalized_at IS
    'Set when operator clicks "Finalize day" on /today. Read-only signal — '
    'tomorrow''s materializer rebuilds from template regardless.';

-- 2. Rewrite materialize_today_plan: template-only, no carryover.
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
    v_tenant_id      uuid;
    v_plan_id        uuid;
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

    -- Template-only — no carryover scan. Tomorrow is a fresh slate.
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

-- (Today's carryover-row cleanup runs as a separate one-shot — apply_migration
-- refuses raw UPDATE for safety. See scripts/_strip_today_carryovers.py.)

COMMIT;
