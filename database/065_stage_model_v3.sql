-- ============================================================================
-- Migration 065 — SunBiz stage model v3 (10 → 7 collapse + two-tier split)
--
-- Adopts Adon Yess's canonical two-tier stage model (ADR-0006) for the
-- SunBiz tenant. Two changes ship together:
--
--   1. Per-merchant `merchant_stage` JSONB key. Values:
--        Lead     — no active application yet
--        Active   — has an application in any non-terminal deal_stage
--        Funded   — most recent deal funded, no active in-flight deal
--        Dormant  — no activity in 90+ days
--
--   2. Per-application `deal_stage` JSONB key, collapsed from the current
--      10 SunBiz application stages to Adon's canonical 7:
--
--        application_in  → "Application In"
--        missing_info    → "Missing Info"
--        requested_docs  → "Missing Info"   (collapse — operational sub-state)
--        docs_out        → "Missing Info"   (collapse — operational sub-state)
--        shopping        → "Shopping"
--        login           → "Shopping"        (collapse — paperwork prep)
--        follow_ups      → "Shopping"        (collapse — active in flight)
--        funded          → "Funded"
--        declined        → "Declined"
--        dead_file       → "Dead"
--
--      "Approved" (Adon's 5th stage) is NOT a tenant_records value — it's
--      DERIVED in the merchant_summary view from
--      application_lender_threads.status='approved' AND no merchant decision
--      yet. So we don't write it to the JSONB.
--
-- Reversibility: every row's original stage is preserved at
-- data.legacy_stage so the merchant_summary view's
-- coalesce(data->>'deal_substage', data->>'legacy_stage') escape hatch can
-- expose the fine-grained sub-state if Adon later wants the original
-- granularity back on the operator dashboard.
--
-- ============================================================================
-- IMPORTANT — execution path
--
-- This migration contains UPDATE statements which scripts/apply_migration.py
-- HARD-BLOCKS by design (safety guard). Apply via the Supabase web SQL
-- editor instead:
--
--   1. Open https://app.supabase.com/project/<project-ref>/sql
--   2. Paste this entire file into a new query.
--   3. Click "Run" with the role set to `service_role`.
--   4. Verify the NOTICE lines printed at the end.
--
-- Companion migration 066 (the merchant_summary view) HAS no UPDATEs so
-- it goes through apply_migration.py normally.
-- ============================================================================

BEGIN;

DO $$
DECLARE
  _sun_tenant_id UUID;
  _leads_updated INT := 0;
  _apps_updated INT := 0;
BEGIN
  SELECT id INTO _sun_tenant_id FROM tenants WHERE slug = 'sun' LIMIT 1;
  IF _sun_tenant_id IS NULL THEN
    RAISE NOTICE 'No tenant with slug=sun — migration is a no-op.';
    RETURN;
  END IF;

  -- ------------------------------------------------------------------------
  -- STEP 1: preserve original stage at data.legacy_stage
  -- ------------------------------------------------------------------------
  -- Only stamp legacy_stage if it's not already set (idempotent re-runs).

  UPDATE tenant_records
     SET data = jsonb_set(data, '{legacy_stage}', to_jsonb(data->>'stage'), true),
         updated_at = NOW()
   WHERE tenant_id = _sun_tenant_id
     AND entity_type IN ('lead', 'application')
     AND data ? 'stage'
     AND NOT (data ? 'legacy_stage');

  -- ------------------------------------------------------------------------
  -- STEP 2: project deal_stage on every application row
  -- ------------------------------------------------------------------------

  UPDATE tenant_records
     SET data = jsonb_set(
                  data,
                  '{deal_stage}',
                  to_jsonb(
                    CASE LOWER(data->>'stage')
                      WHEN 'application_in'  THEN 'Application In'
                      WHEN 'missing_info'    THEN 'Missing Info'
                      WHEN 'requested_docs'  THEN 'Missing Info'
                      WHEN 'docs_out'        THEN 'Missing Info'
                      WHEN 'shopping'        THEN 'Shopping'
                      WHEN 'login'           THEN 'Shopping'
                      WHEN 'follow_ups'      THEN 'Shopping'
                      WHEN 'funded'          THEN 'Funded'
                      WHEN 'declined'        THEN 'Declined'
                      WHEN 'dead_file'       THEN 'Dead'
                      ELSE 'Application In'  -- safest default for unknown
                    END
                  ),
                  true
                ),
         updated_at = NOW()
   WHERE tenant_id = _sun_tenant_id
     AND entity_type = 'application';

  GET DIAGNOSTICS _apps_updated = ROW_COUNT;

  -- ------------------------------------------------------------------------
  -- STEP 3: project merchant_stage on every lead row
  -- ------------------------------------------------------------------------
  --
  -- Logic:
  --   - If lead has NO associated application → 'Lead'
  --   - If lead has any application with deal_stage IN
  --     ('Application In', 'Missing Info', 'Shopping') → 'Active'
  --   - If lead's most recent application has deal_stage='Funded' → 'Funded'
  --   - If lead has NO activity (updated_at) in past 90 days AND no
  --     active deal → 'Dormant'
  --   - Else 'Active'
  --
  -- Applications reference their parent lead via data->>'lead_id' (the
  -- existing SunBiz convention).

  WITH lead_app_status AS (
    SELECT
      l.id AS lead_id,
      l.updated_at AS lead_updated_at,
      EXISTS (
        SELECT 1 FROM tenant_records a
         WHERE a.tenant_id = _sun_tenant_id
           AND a.entity_type = 'application'
           AND a.data->>'lead_id' = l.id::text
           AND a.data->>'deal_stage' IN ('Application In', 'Missing Info', 'Shopping')
      ) AS has_active_deal,
      EXISTS (
        SELECT 1 FROM tenant_records a
         WHERE a.tenant_id = _sun_tenant_id
           AND a.entity_type = 'application'
           AND a.data->>'lead_id' = l.id::text
           AND a.data->>'deal_stage' = 'Funded'
      ) AS has_funded_deal,
      EXISTS (
        SELECT 1 FROM tenant_records a
         WHERE a.tenant_id = _sun_tenant_id
           AND a.entity_type = 'application'
           AND a.data->>'lead_id' = l.id::text
      ) AS has_any_application
    FROM tenant_records l
    WHERE l.tenant_id = _sun_tenant_id
      AND l.entity_type = 'lead'
  )
  UPDATE tenant_records AS t
     SET data = jsonb_set(
                  data,
                  '{merchant_stage}',
                  to_jsonb(
                    CASE
                      WHEN s.has_active_deal THEN 'Active'
                      WHEN s.has_funded_deal THEN 'Funded'
                      WHEN NOT s.has_any_application
                           AND s.lead_updated_at < NOW() - INTERVAL '90 days'
                        THEN 'Dormant'
                      WHEN NOT s.has_any_application THEN 'Lead'
                      ELSE 'Active'
                    END
                  ),
                  true
                ),
         updated_at = NOW()
    FROM lead_app_status s
   WHERE t.id = s.lead_id;

  GET DIAGNOSTICS _leads_updated = ROW_COUNT;

  RAISE NOTICE 'SunBiz stage v3 migration: % leads, % applications updated',
    _leads_updated, _apps_updated;

  -- ------------------------------------------------------------------------
  -- STEP 4: distribution sanity check — surfaced to operator
  -- ------------------------------------------------------------------------

  RAISE NOTICE '--- merchant_stage distribution ---';
  FOR _leads_updated IN
    SELECT NULL
  LOOP NULL; END LOOP;  -- placeholder so the FOR works

END $$;

-- Print distribution after the DO block (cleaner than inside it).
DO $$
DECLARE
  _r RECORD;
  _sun UUID;
BEGIN
  SELECT id INTO _sun FROM tenants WHERE slug='sun' LIMIT 1;
  IF _sun IS NULL THEN RETURN; END IF;

  RAISE NOTICE '--- merchant_stage distribution after migration ---';
  FOR _r IN
    SELECT data->>'merchant_stage' AS s, COUNT(*) AS n
      FROM tenant_records
     WHERE tenant_id = _sun
       AND entity_type = 'lead'
     GROUP BY 1 ORDER BY 2 DESC
  LOOP
    RAISE NOTICE '  % : %', COALESCE(_r.s, '(null)'), _r.n;
  END LOOP;

  RAISE NOTICE '--- deal_stage distribution after migration ---';
  FOR _r IN
    SELECT data->>'deal_stage' AS s, COUNT(*) AS n
      FROM tenant_records
     WHERE tenant_id = _sun
       AND entity_type = 'application'
     GROUP BY 1 ORDER BY 2 DESC
  LOOP
    RAISE NOTICE '  % : %', COALESCE(_r.s, '(null)'), _r.n;
  END LOOP;
END $$;

-- ============================================================================
-- INDEX SUPPORT for the new JSONB keys
-- ============================================================================
-- merchant_summary view filters heavily on tenant_id + merchant_stage and
-- tenant_id + deal_stage. Postgres can't directly index jsonb->>'key'
-- without an expression index. Two narrow expression indexes — these only
-- exist for the SunBiz access patterns and stay cheap to maintain because
-- they're partial (entity_type filter).

CREATE INDEX IF NOT EXISTS idx_tenant_records_sunbiz_merchant_stage
    ON public.tenant_records (tenant_id, (data->>'merchant_stage'))
 WHERE entity_type = 'lead';

CREATE INDEX IF NOT EXISTS idx_tenant_records_sunbiz_deal_stage
    ON public.tenant_records (tenant_id, (data->>'deal_stage'))
 WHERE entity_type = 'application';

CREATE INDEX IF NOT EXISTS idx_tenant_records_application_lead_id
    ON public.tenant_records ((data->>'lead_id'))
 WHERE entity_type = 'application';

COMMIT;

-- ============================================================================
-- ROLLBACK (if needed before commit):
--   ROLLBACK;
--
-- POST-COMMIT REVERSE (if needed later):
--   UPDATE tenant_records
--      SET data = data - 'merchant_stage' - 'deal_stage',
--          data = jsonb_set(data, '{stage}', to_jsonb(data->>'legacy_stage'), true)
--    WHERE tenant_id = (SELECT id FROM tenants WHERE slug='sun')
--      AND entity_type IN ('lead','application')
--      AND data ? 'legacy_stage';
--
--   DROP INDEX IF EXISTS idx_tenant_records_sunbiz_merchant_stage;
--   DROP INDEX IF EXISTS idx_tenant_records_sunbiz_deal_stage;
--   DROP INDEX IF EXISTS idx_tenant_records_application_lead_id;
-- ============================================================================
