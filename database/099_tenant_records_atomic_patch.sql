-- 099_tenant_records_atomic_patch.sql
--
-- Codex adversarial review 2026-06-06 flagged two high-severity lost-update
-- races on tenant_records.data:
--   - /api/leads/[id]/score reads `data`, awaits a multi-second Claude call,
--     writes the whole blob back with only ai_* keys merged. Any sibling
--     edit during the model call is silently dropped.
--   - /api/leads/[id]/drip-toggle has the same shape (read → toggle → write).
--
-- Fix: ONE atomic-merge RPC that updates only the patch keys via JSONB ||,
-- so concurrent writers to other keys are preserved.
--
-- Migration also rewrites materialize_today_plan to use INSERT ON CONFLICT
-- DO NOTHING RETURNING, which closes the SELECT-then-INSERT race that
-- could land a unique_violation 500 on two simultaneous logins.
--
-- Apply with: python scripts/apply_migration.py database/099_tenant_records_atomic_patch.sql

BEGIN;

-- ---------------------------------------------------------------------
-- 1. patch_tenant_record_data — atomic shallow merge into the data jsonb.
-- ---------------------------------------------------------------------
-- Returns the post-patch row id + updated data so the caller can echo
-- back to the client without a second read. Tenant-scoped via the
-- caller-supplied p_tenant_id so RLS isn't required to enforce
-- isolation (the route's session resolver already gated the tenant_id).
--
-- We DO NOT touch the `data` payload in any way except `data || p_patch`
-- (top-level shallow merge — JSONB's standard semantics). Callers
-- needing nested merges must pre-build the full top-level patch.

CREATE OR REPLACE FUNCTION public.patch_tenant_record_data(
    p_id        uuid,
    p_tenant_id uuid,
    p_patch     jsonb
)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_new_data jsonb;
BEGIN
    IF p_patch IS NULL OR jsonb_typeof(p_patch) <> 'object' THEN
        RAISE EXCEPTION 'p_patch must be a non-null jsonb object' USING ERRCODE = '22023';
    END IF;

    UPDATE public.tenant_records
       SET data = COALESCE(data, '{}'::jsonb) || p_patch,
           updated_at = now()
     WHERE id = p_id
       AND tenant_id = p_tenant_id
     RETURNING data
       INTO v_new_data;

    IF v_new_data IS NULL THEN
        RAISE EXCEPTION 'lead_not_found_or_wrong_tenant: id=%, tenant=%', p_id, p_tenant_id
            USING ERRCODE = '02000';
    END IF;

    RETURN v_new_data;
END;
$$;

COMMENT ON FUNCTION public.patch_tenant_record_data(uuid, uuid, jsonb) IS
    'Atomic shallow merge into tenant_records.data — replaces the read-then-write '
    'pattern in /api/leads/[id]/score and /api/leads/[id]/drip-toggle so concurrent '
    'edits to non-overlapping keys are not silently lost. Returns the post-patch '
    'data blob. Errors with SQLSTATE 02000 when the lead is missing or belongs '
    'to a different tenant.';

-- ---------------------------------------------------------------------
-- 2. materialize_today_plan — atomic, no SELECT-then-INSERT race.
-- ---------------------------------------------------------------------
-- Two simultaneous callers (multi-tab login, /today fast-refresh) could
-- both see no existing row and both attempt the INSERT. The unique
-- constraint stops the duplicate but the loser raises 23505 which the
-- route returns as a 500. Rewriting to INSERT ON CONFLICT DO NOTHING
-- RETURNING id, then SELECT the row when the insert returned no id,
-- gives every caller a clean plan_id no matter who won.

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
$$;

COMMENT ON FUNCTION public.materialize_today_plan(uuid, date) IS
    'Idempotent + race-safe. INSERT ... ON CONFLICT DO NOTHING RETURNING then '
    'fallback SELECT means simultaneous callers all receive a real plan id '
    'instead of one of them getting unique_violation. Use force_materialize_today_plan '
    'for explicit operator reset.';

COMMIT;
