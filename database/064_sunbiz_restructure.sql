-- ============================================================================
-- Migration 064 — SunBiz Agent Command Centre restructure (Jordan/Oasis 2026-05)
--
-- Scope: tenant_slug='sun' only. OASIS / Suga / other tenants untouched.
--
-- All Lead, Application, and Lender records live in tenant_records as JSONB
-- (per the V6 universal records pattern from migration 038). The Lead's
-- pipeline position is data->>'stage', the Application's is data->>'status'.
-- No PG ENUMs are in play — values are text inside JSONB — so this migration
-- is pure data UPDATEs, no DDL on tenant_records.
--
-- What this migration does (idempotent, transactional, scoped to SunBiz):
--
-- 1. LEAD STAGE COLLAPSE — drops imported / not_interested / approved from
--    the active Lead funnel. Existing rows are remapped, not dropped:
--      imported       -> hot_lead       (re-enter active funnel)
--      not_interested -> declined       (terminal state still preserved)
--      approved       -> submitted      (graduates toward Applications)
--
-- 2. APPLICATION STATUS CONSOLIDATION — collapses 17 stages to 9. Existing
--    rows remap as:
--      submitted_to_underwriting -> shopping
--      approved                  -> shopping  (offers live on Offers page now)
--      approved_open_offers      -> shopping
--      selling                   -> shopping
--      approved_never_funded     -> dead_file
--      no_offers_available       -> declined
--      contracts_ordered         -> docs_out
--      follow_ups                -> follow_ups  (kept; surfaced via filters)
--
-- 3. RENEWAL ELIGIBILITY THRESHOLD — patches the SunBiz tenant_manifests
--    row's manifest JSONB to add settings.renewal_eligibility_threshold_pct
--    (default 40). Read server-side by /t/sun/renewals. No new table needed
--    — the manifest is already the per-tenant config layer.
--
-- What this migration does NOT do:
--   - No DDL on tenant_records (JSONB shape covers new fields like
--     owner_address_* on applications and the lender field expansion).
--   - No PG ENUM type changes (none in play for these entities).
--   - No tenant_records row deletions — every record survives, just under
--     a different stage/status value.
--   - No changes to OASIS, Suga, or other tenants.
--
-- Apply via: python scripts/supabase_tool.py migrate database/064_sunbiz_restructure.sql
-- Verify after: every NOTICE in the output should show non-negative row counts;
-- a final SELECT against the remapped values should confirm the new shape.
-- ============================================================================

BEGIN;

DO $$
DECLARE
    v_sunbiz_tenant_id uuid;
    v_lead_imported_count       integer := 0;
    v_lead_notinterested_count  integer := 0;
    v_lead_approved_count       integer := 0;
    v_app_submitted_uw_count    integer := 0;
    v_app_approved_count        integer := 0;
    v_app_approved_open_count   integer := 0;
    v_app_selling_count         integer := 0;
    v_app_anf_count             integer := 0;
    v_app_no_offers_count       integer := 0;
    v_app_contracts_count       integer := 0;
    v_manifest_patched          integer := 0;
BEGIN
    -- ----------------------------------------------------------------
    -- Resolve the SunBiz tenant_id from the slug. Bail out (without
    -- error) if the tenant doesn't exist in this environment — keeps
    -- the migration runnable in dev environments without seeded data.
    -- ----------------------------------------------------------------
    SELECT id INTO v_sunbiz_tenant_id
    FROM public.tenants
    WHERE slug = 'sun'
    LIMIT 1;

    IF v_sunbiz_tenant_id IS NULL THEN
        RAISE NOTICE '[064] SunBiz tenant (slug=sun) not found — skipping data migration. Manifest/UI changes still apply via seeds.ts fallback.';
        RETURN;
    END IF;

    RAISE NOTICE '[064] SunBiz tenant_id resolved: %', v_sunbiz_tenant_id;

    -- ================================================================
    -- 1. LEAD STAGE COLLAPSE
    -- ================================================================

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"hot_lead"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'imported';
    GET DIAGNOSTICS v_lead_imported_count = ROW_COUNT;
    RAISE NOTICE '[064] leads: imported -> hot_lead (%)', v_lead_imported_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"declined"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'not_interested';
    GET DIAGNOSTICS v_lead_notinterested_count = ROW_COUNT;
    RAISE NOTICE '[064] leads: not_interested -> declined (%)', v_lead_notinterested_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{stage}', '"submitted"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'lead'
       AND data->>'stage' = 'approved';
    GET DIAGNOSTICS v_lead_approved_count = ROW_COUNT;
    RAISE NOTICE '[064] leads: approved -> submitted (%)', v_lead_approved_count;

    -- ================================================================
    -- 2. APPLICATION STATUS CONSOLIDATION
    -- ================================================================

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'submitted_to_underwriting';
    GET DIAGNOSTICS v_app_submitted_uw_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: submitted_to_underwriting -> shopping (%)', v_app_submitted_uw_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved';
    GET DIAGNOSTICS v_app_approved_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: approved -> shopping (%)', v_app_approved_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved_open_offers';
    GET DIAGNOSTICS v_app_approved_open_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: approved_open_offers -> shopping (%)', v_app_approved_open_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"shopping"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'selling';
    GET DIAGNOSTICS v_app_selling_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: selling -> shopping (%)', v_app_selling_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"dead_file"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'approved_never_funded';
    GET DIAGNOSTICS v_app_anf_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: approved_never_funded -> dead_file (%)', v_app_anf_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"declined"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'no_offers_available';
    GET DIAGNOSTICS v_app_no_offers_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: no_offers_available -> declined (%)', v_app_no_offers_count;

    UPDATE public.tenant_records
       SET data = jsonb_set(data, '{status}', '"docs_out"'::jsonb, true),
           updated_at = now()
     WHERE tenant_id = v_sunbiz_tenant_id
       AND entity_type = 'application'
       AND data->>'status' = 'contracts_ordered';
    GET DIAGNOSTICS v_app_contracts_count = ROW_COUNT;
    RAISE NOTICE '[064] applications: contracts_ordered -> docs_out (%)', v_app_contracts_count;

    -- ================================================================
    -- 3. RENEWAL ELIGIBILITY THRESHOLD — patch the SunBiz manifest
    -- ================================================================
    --
    -- If a DB-side manifest exists for SunBiz, patch its settings block.
    -- If only the in-code seed is in use (no row yet), skip — the seed
    -- ships with the default already wired in lib/manifest/seeds.ts.

    UPDATE public.tenant_manifests
       SET manifest = jsonb_set(
                manifest,
                '{settings,renewal_eligibility_threshold_pct}',
                '40'::jsonb,
                true
            ),
            updated_at = now()
     WHERE slug = 'sun';
    GET DIAGNOSTICS v_manifest_patched = ROW_COUNT;
    RAISE NOTICE '[064] manifest settings.renewal_eligibility_threshold_pct=40 patched on % row(s)', v_manifest_patched;

    -- ================================================================
    -- Summary
    -- ================================================================
    RAISE NOTICE '[064] DONE — leads remapped: % | applications remapped: % | manifest rows patched: %',
        v_lead_imported_count + v_lead_notinterested_count + v_lead_approved_count,
        v_app_submitted_uw_count + v_app_approved_count + v_app_approved_open_count
            + v_app_selling_count + v_app_anf_count + v_app_no_offers_count + v_app_contracts_count,
        v_manifest_patched;
END $$;

COMMIT;

-- ============================================================================
-- Verification queries (run manually post-apply; commented out so they don't
-- pollute the migration output). Replace <tenant_id> with the value the
-- NOTICE above reported.
-- ============================================================================
--
-- Confirm no leads remain in the removed stages:
--   SELECT data->>'stage' AS stage, COUNT(*)
--     FROM public.tenant_records
--    WHERE tenant_id = '<tenant_id>'
--      AND entity_type = 'lead'
--      AND data->>'stage' IN ('imported','not_interested','approved')
--    GROUP BY 1;
--   -- expected: 0 rows
--
-- Confirm no applications remain in the removed statuses:
--   SELECT data->>'status' AS status, COUNT(*)
--     FROM public.tenant_records
--    WHERE tenant_id = '<tenant_id>'
--      AND entity_type = 'application'
--      AND data->>'status' IN (
--          'submitted_to_underwriting','approved','approved_open_offers',
--          'selling','approved_never_funded','no_offers_available','contracts_ordered'
--      )
--    GROUP BY 1;
--   -- expected: 0 rows
--
-- Confirm the manifest carries the renewal threshold:
--   SELECT manifest->'settings'->>'renewal_eligibility_threshold_pct' AS threshold
--     FROM public.tenant_manifests
--    WHERE slug = 'sun';
--   -- expected: '40' (text)
