-- 098_materialize_today_plan_idempotent.sql
--
-- Make the canonical materialize_today_plan RPC idempotent: if a plan
-- already exists for (profile_id, plan_date), DO NOT clobber it. The
-- previous version used ON CONFLICT DO UPDATE which silently overwrote
-- the schedule, mission, and targets every call — meaning any operator
-- edits to today's plan (marking items done, swapping order, custom
-- mission) were lost the moment something re-triggered the RPC. CC's
-- complaint 2026-06-06: "I've had to set it up in settings multiple
-- times at this point now."
--
-- Behavior split:
--   - materialize_today_plan        — idempotent. Insert if missing, no-op
--                                     if present. Safe for the nightly cron
--                                     to re-fire without losing edits.
--   - force_materialize_today_plan  — clobber. Use ONLY from the operator's
--                                     explicit "Reset today's plan" affordance.
--
-- This keeps the cron path safe by default and makes intent-to-overwrite
-- explicit at the call site. The Vercel cron at
-- /api/cron/materialize-plans keeps calling materialize_today_plan and
-- becomes naturally idempotent. The manual endpoint
-- /api/daily-plan/materialize is updated in the same commit to call the
-- force variant.
--
-- Apply with: python scripts/apply_migration.py database/098_materialize_today_plan_idempotent.sql

BEGIN;

-- 1. Idempotent default: insert if missing, leave existing rows alone.
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
    v_existing_id    uuid;
BEGIN
    v_target_date := COALESCE(p_target_date, current_date);

    -- Idempotency check: if a plan already exists for this slot, return
    -- its id and do nothing. This is the load-bearing change vs the prior
    -- ON CONFLICT DO UPDATE behavior.
    SELECT id INTO v_existing_id
    FROM public.daily_plans
    WHERE profile_id = p_profile_id AND plan_date = v_target_date;

    IF v_existing_id IS NOT NULL THEN
        RETURN v_existing_id;
    END IF;

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
    RETURNING id INTO v_plan_id;

    RETURN v_plan_id;
END;
$$;

COMMENT ON FUNCTION public.materialize_today_plan(uuid, date) IS
    'Idempotent: returns existing plan id if present, else inserts fresh '
    'from template. Operator edits to existing plans are preserved across '
    're-fires. Use force_materialize_today_plan() for an explicit reset.';

-- 2. Explicit-reset variant. Only the operator-triggered reset endpoint
--    should call this — it CLOBBERS any in-flight edits.
CREATE OR REPLACE FUNCTION public.force_materialize_today_plan(
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
    SET schedule        = EXCLUDED.schedule,
        mission         = EXCLUDED.mission,
        target_calls    = EXCLUDED.target_calls,
        target_emails   = EXCLUDED.target_emails,
        target_bookings = EXCLUDED.target_bookings,
        finalized_at    = NULL,
        updated_at      = now()
    RETURNING id INTO v_plan_id;

    RETURN v_plan_id;
END;
$$;

COMMENT ON FUNCTION public.force_materialize_today_plan(uuid, date) IS
    'Explicit-overwrite variant of materialize_today_plan. Operator-only '
    'path used by /api/daily-plan/materialize when CC clicks "Reset". '
    'Clears finalized_at and rebuilds schedule from the latest template.';

COMMIT;
