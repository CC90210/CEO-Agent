-- ============================================================================
-- Migration 067 — SunBiz stage remap fix (post-064 cleanup)
--
-- 064 resolved the SunBiz tenant by `slug = 'sun'` and silently NO-OP'd
-- because the real tenant has `slug = 'submissions'` with
-- `custom_fields.command_center_profile_slug = 'sun'`. As a result, 10
-- application rows kept retired status values that don't match any
-- post-064 chevron stage and rendered nowhere in /t/sun/applications:
--
--   submitted_to_underwriting (1 row) → expected: shopping
--   approved                  (9 rows) → expected: shopping
--
-- This migration:
--   1. Resolves the SunBiz tenant_id with the SAME resolver the dashboard
--      uses (`resolveClientProfileSlug` — slug OR custom_fields.*_slug).
--      Single tenant in scope; OASIS/Suga untouched.
--   2. Re-runs the application status remap on any rows still carrying
--      a retired value. Idempotent — safe to re-apply on a clean DB.
--   3. Also re-runs the lead stage remap for completeness.
--
-- Apply via: python scripts/integrations/supabase_admin.py migrate database/067_sunbiz_stage_remap_fix.sql
-- Verify: NOTICE rows show the actual counts touched; a follow-up SELECT
-- confirms every application's status is in the post-064 enum set.
-- ============================================================================

BEGIN;

DO $$
DECLARE
    v_sunbiz_tenant_id uuid;
    v_app_uw_count int;
    v_app_approved_count int;
    v_app_aoo_count int;
    v_app_selling_count int;
    v_app_anf_count int;
    v_app_noa_count int;
    v_app_co_count int;
    v_lead_imported int;
    v_lead_not_interested int;
    v_lead_approved int;
BEGIN
    -- ----------------------------------------------------------------
    -- Resolve SunBiz tenant_id via the dashboard's resolver shape:
    --   slug='sun' OR custom_fields->>'command_center_profile_slug'='sun'
    --   OR custom_fields->>'command_center_profile'='sun'
    --   OR custom_fields->>'dashboard_profile_slug'='sun'
    --   OR custom_fields->>'dashboard_profile'='sun'
    -- Bail out (without error) if nothing matches so dev environments
    -- without SunBiz data still apply the file.
    -- ----------------------------------------------------------------
    SELECT id INTO v_sunbiz_tenant_id
    FROM public.tenants
    WHERE slug = 'sun'
       OR LOWER(custom_fields->>'command_center_profile_slug') = 'sun'
       OR LOWER(custom_fields->>'command_center_profile') = 'sun'
       OR LOWER(custom_fields->>'dashboard_profile_slug') = 'sun'
       OR LOWER(custom_fields->>'dashboard_profile') = 'sun'
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_sunbiz_tenant_id IS NULL THEN
        RAISE NOTICE '[067] SunBiz tenant not found via slug or custom_fields — skipping.';
        RETURN;
    END IF;

    RAISE NOTICE '[067] SunBiz tenant_id resolved: %', v_sunbiz_tenant_id;

    -- ================================================================
    -- APPLICATION STATUS REMAP (the 064 NO-OP fix)
    -- ================================================================

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'submitted_to_underwriting';
    GET DIAGNOSTICS v_app_uw_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: submitted_to_underwriting -> shopping (%)', v_app_uw_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved';
    GET DIAGNOSTICS v_app_approved_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: approved -> shopping (%)', v_app_approved_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved_open_offers';
    GET DIAGNOSTICS v_app_aoo_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: approved_open_offers -> shopping (%)', v_app_aoo_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'selling';
    GET DIAGNOSTICS v_app_selling_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: selling -> shopping (%)', v_app_selling_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"dead_file"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved_never_funded';
    GET DIAGNOSTICS v_app_anf_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: approved_never_funded -> dead_file (%)', v_app_anf_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"declined"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'no_offers_available';
    GET DIAGNOSTICS v_app_noa_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: no_offers_available -> declined (%)', v_app_noa_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"docs_out"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'contracts_ordered';
    GET DIAGNOSTICS v_app_co_count = ROW_COUNT;
    RAISE NOTICE '[067] applications: contracts_ordered -> docs_out (%)', v_app_co_count;

    -- ================================================================
    -- LEAD STAGE REMAP (idempotent re-run; usually 0 rows on this tenant)
    -- ================================================================

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"hot_lead"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'imported';
    GET DIAGNOSTICS v_lead_imported = ROW_COUNT;
    RAISE NOTICE '[067] leads: imported -> hot_lead (%)', v_lead_imported;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"declined"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'not_interested';
    GET DIAGNOSTICS v_lead_not_interested = ROW_COUNT;
    RAISE NOTICE '[067] leads: not_interested -> declined (%)', v_lead_not_interested;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"submitted"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'approved';
    GET DIAGNOSTICS v_lead_approved = ROW_COUNT;
    RAISE NOTICE '[067] leads: approved -> submitted (%)', v_lead_approved;

    -- ================================================================
    -- DATA SHAPE INTEGRITY: stage mirrors status on application
    -- ================================================================
    -- 064 always wrote BOTH data.stage AND data.status to the same value
    -- on application rows (some legacy code reads stage, some reads
    -- status). Mirror the status writes above into stage to keep the
    -- two fields in lockstep for the rows we just touched.
    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', to_jsonb(data->>'status'), true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' IS NOT NULL
       AND COALESCE(data->>'stage', '') <> COALESCE(data->>'status', '');

    RAISE NOTICE '[067] DONE — applications touched: % | leads touched: %',
        (v_app_uw_count + v_app_approved_count + v_app_aoo_count +
         v_app_selling_count + v_app_anf_count + v_app_noa_count + v_app_co_count),
        (v_lead_imported + v_lead_not_interested + v_lead_approved);
END;
$$ LANGUAGE plpgsql;

COMMIT;

-- ============================================================================
-- VERIFY (run after migration, EXPECT zero rows):
--   SELECT data->>'status' AS status, COUNT(*)
--     FROM public.tenant_records
--    WHERE tenant_id = (
--            SELECT id FROM public.tenants
--             WHERE slug = 'sun'
--                OR LOWER(custom_fields->>'command_center_profile_slug') = 'sun'
--             LIMIT 1
--          )
--      AND entity_type = 'application'
--      AND data->>'status' IN (
--          'submitted_to_underwriting', 'approved', 'approved_open_offers',
--          'selling', 'approved_never_funded', 'no_offers_available',
--          'contracts_ordered'
--      )
--    GROUP BY data->>'status';
-- ============================================================================
