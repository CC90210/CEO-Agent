-- ============================================================================
-- Migration 066 — Fix migration 064's tenant-resolution bug + remap stuck
--                  Sun Biz records + grant Ezra owner role
--
-- WHAT WENT WRONG IN 064
-- ----------------------
-- Migration 064 queried `tenants WHERE slug = 'sun'` to resolve the Sun Biz
-- tenant_id. That was wrong: `tenants.slug` for Sun Biz is `submissions`;
-- `sun` is the MANIFEST slug stored on `tenant_manifests.slug`. The two
-- namespaces are decoupled. When migration 064 ran, it returned NULL,
-- printed the polite bail message, and remapped 0 rows.
--
-- Aftermath: 9 records still have status='approved' + 1 has status=
-- 'submitted_to_underwriting' — both retired by the 064 schema slim-down
-- (collapsed into 'shopping'). These rows render as "HIDDEN" on the
-- Applications page because the post-064 SUNBIZ_STAGES set doesn't include
-- them.
--
-- DIAGNOSTIC OUTPUT (2026-05-25, scripts/diag_lead_visibility.py)
-- ---------------------------------------------------------------
--   Sun Biz tenant 'submissions' (aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110):
--     462 applications, 0 leads (raw imports went to entity_type=
--     'application' because CSV had application_url / bank_statement_urls /
--     requested_amount — that's the import router's hasApplicationEvidence
--     branch firing correctly).
--     Status: 232 declined, 149 dead_file, 39 follow_ups, 23 funded,
--             4 docs_out, 3 shopping, 2 application_in,
--             9 approved [HIDDEN], 1 submitted_to_underwriting [HIDDEN].
--
-- THIS MIGRATION DOES THREE THINGS
-- --------------------------------
-- 1. Resolves the Sun Biz tenant_id the CORRECT way:
--    `tenant_manifests WHERE slug = 'sun'` → tenants.id
--    Falls back to `tenants WHERE slug = 'submissions'` if the manifest
--    row doesn't exist yet.
--
-- 2. Re-runs migration 064's row remaps for the Sun Biz tenant.
--    Idempotent — rows already at the target stage are untouched.
--
-- 3. Grants the canonical Sun Biz operator Ezra
--    (Submissions@sunbizfunding.com) the `is_owner=true` + `team_role=
--    'owner'` role on his user_profiles row. Without this his Settings →
--    Devices section hides; he can't pair the VPS bridge. Documented in
--    playbook 08 as the operator hand-over step; this migration encodes
--    it idempotently so it's not lost.
--
-- Apply via: python scripts/apply_migration.py database/066_sunbiz_remap_stuck_records.sql
-- ============================================================================

BEGIN;

DO $$
DECLARE
    v_sunbiz_tenant_id uuid;
    v_app_approved_count        integer := 0;
    v_app_uw_count              integer := 0;
    v_lead_imported_count       integer := 0;
    v_lead_notinterested_count  integer := 0;
    v_lead_approved_count       integer := 0;
    v_ezra_grant_count          integer := 0;
BEGIN
    -- ----------------------------------------------------------------
    -- 1. Resolve Sun Biz tenant_id via tenant_manifests (the actual
    --    URL-slug → tenant_id mapping). Fall back to tenants.slug =
    --    'submissions' if the manifest row hasn't been seeded yet.
    -- ----------------------------------------------------------------
    SELECT tm.tenant_id INTO v_sunbiz_tenant_id
    FROM public.tenant_manifests tm
    WHERE tm.slug = 'sun'
    LIMIT 1;

    IF v_sunbiz_tenant_id IS NULL THEN
        SELECT id INTO v_sunbiz_tenant_id
        FROM public.tenants
        WHERE slug = 'submissions'
        LIMIT 1;
    END IF;

    IF v_sunbiz_tenant_id IS NULL THEN
        RAISE EXCEPTION '[066] Sun Biz tenant not found via tenant_manifests.slug=sun OR tenants.slug=submissions. Seed tenant before applying this migration.';
    END IF;

    RAISE NOTICE '[066] Sun Biz tenant_id resolved: %', v_sunbiz_tenant_id;

    -- ----------------------------------------------------------------
    -- 2. Application status remaps — same as 064 §2, scoped correctly.
    -- ----------------------------------------------------------------
    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved';
    GET DIAGNOSTICS v_app_approved_count = ROW_COUNT;
    RAISE NOTICE '[066] applications: approved -> shopping (%)', v_app_approved_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'submitted_to_underwriting';
    GET DIAGNOSTICS v_app_uw_count = ROW_COUNT;
    RAISE NOTICE '[066] applications: submitted_to_underwriting -> shopping (%)', v_app_uw_count;

    -- Catch any other 064-targeted stuck statuses defensively.
    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' IN ('approved_open_offers', 'selling');

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"dead_file"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved_never_funded';

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"declined"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'no_offers_available';

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"docs_out"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'contracts_ordered';

    -- ----------------------------------------------------------------
    -- 3. Lead stage remaps — also missed by 064. Sun Biz currently has
    --    0 lead rows per the diagnostic, but run the UPDATE defensively
    --    in case any get created before this migration applies.
    -- ----------------------------------------------------------------
    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"hot_lead"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'imported';
    GET DIAGNOSTICS v_lead_imported_count = ROW_COUNT;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"declined"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'not_interested';
    GET DIAGNOSTICS v_lead_notinterested_count = ROW_COUNT;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"submitted"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'approved';
    GET DIAGNOSTICS v_lead_approved_count = ROW_COUNT;

    -- ----------------------------------------------------------------
    -- 4. Grant Ezra owner role on the Sun Biz tenant. Without this his
    --    Settings → Devices section (gated by canManageTenant) hides
    --    and he can't pair the VPS bridge. Case-insensitive email
    --    match because user_profiles stores 'Submissions@sunbizfunding.com'
    --    with the original casing.
    -- ----------------------------------------------------------------
    UPDATE public.user_profiles
       SET is_owner = true,
           team_role = 'owner',
           updated_at = now()
     WHERE LOWER(email) = 'submissions@sunbizfunding.com'
       AND tenant_id = v_sunbiz_tenant_id
       AND (is_owner IS DISTINCT FROM true OR team_role IS DISTINCT FROM 'owner');
    GET DIAGNOSTICS v_ezra_grant_count = ROW_COUNT;
    RAISE NOTICE '[066] ezra owner grant applied to % row(s) (0 means already owner)', v_ezra_grant_count;

    -- ----------------------------------------------------------------
    -- 5. Patch tenant_manifests.settings.renewal_eligibility_threshold_pct
    --    The 064 attempt missed this because the tenant lookup failed
    --    upstream. Now sets it to 40 on the SunBiz manifest row.
    -- ----------------------------------------------------------------
    UPDATE public.tenant_manifests
       SET manifest = jsonb_set(
                manifest,
                '{settings,renewal_eligibility_threshold_pct}',
                '40'::jsonb,
                true
            ),
            updated_at = now()
     WHERE slug = 'sun';

    -- Summary
    RAISE NOTICE '[066] DONE — applications remapped (064 catch-up): %, leads remapped: %, ezra grant: %',
        v_app_approved_count + v_app_uw_count,
        v_lead_imported_count + v_lead_notinterested_count + v_lead_approved_count,
        v_ezra_grant_count;
END $$;

COMMIT;

-- ============================================================================
-- Post-apply verification (run via diag_lead_visibility.py — should now
-- show 0 [HIDDEN] application statuses for the Sun Biz tenant).
-- ============================================================================
