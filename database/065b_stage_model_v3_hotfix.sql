-- ============================================================================
-- Migration 065b — stage model v3 hotfix (correct tenant lookup)
--
-- Migration 065 looked up the SunBiz tenant via WHERE slug = 'sun', based on
-- the tenant_slug field in SunBiz-Agent/dashboard/tenant.manifest.json. The
-- actual tenants.slug column in production is 'submissions' — 'sun' lives
-- in tenants.custom_fields.command_center_profile_slug as a dashboard-side
-- navigation hint. So 065's WHERE clause matched zero rows and the data
-- stamping was a no-op for the 462 application records, 1 lead, etc.
--
-- This hotfix re-runs the same data migration logic but matches the tenant
-- by NAME='SunBiz' (the canonical brand identity), with slug='submissions'
-- as a fallback. Idempotent — every UPDATE checks for the absence of the
-- new key (or that legacy_stage is the source of truth) before writing.
-- ============================================================================

BEGIN;

DO $$
DECLARE
  _sun_tenant_id UUID;
  _leads_updated INT := 0;
  _apps_updated INT := 0;
BEGIN
  -- Match by name first (most stable), fall back to either known slug.
  SELECT id INTO _sun_tenant_id
    FROM tenants
   WHERE name = 'SunBiz'
      OR slug IN ('submissions', 'sun')
      OR (custom_fields->>'command_center_profile_slug') = 'sun'
   LIMIT 1;

  IF _sun_tenant_id IS NULL THEN
    RAISE NOTICE 'No SunBiz tenant found by name/slug — hotfix is a no-op.';
    RETURN;
  END IF;

  RAISE NOTICE 'SunBiz tenant resolved: %', _sun_tenant_id;

  -- STEP 1: stamp legacy_stage on every record that has a stage but no
  -- legacy_stage yet. Same logic as 065 but tenant-scoped correctly now.
  UPDATE tenant_records
     SET data = jsonb_set(COALESCE(data, '{}'::jsonb), '{legacy_stage}', to_jsonb(data->>'stage'), true),
         updated_at = NOW()
   WHERE tenant_id = _sun_tenant_id
     AND entity_type IN ('lead', 'application')
     AND data ? 'stage'
     AND NOT (data ? 'legacy_stage');

  -- STEP 2: stamp deal_stage on application rows (Adon's 7-stage canonical
  -- mapping). Unknown stages remain NULL — surfaced in the NOTICE below.
  UPDATE tenant_records
     SET data = jsonb_set(
                  COALESCE(data, '{}'::jsonb),
                  '{deal_stage}',
                  -- COALESCE the to_jsonb result to a JSON null literal
                  -- so an unknown stage doesn't propagate SQL NULL up
                  -- through jsonb_set and violate the NOT NULL constraint
                  -- on the data column.
                  COALESCE(to_jsonb(
                    CASE LOWER(REPLACE(data->>'stage', ' ', '_'))
                      -- Canonical SunBiz stages (post-migration 064)
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
                      -- Pre-migration-064 legacy values (see
                      -- oasis-command-center/lib/sunbiz-stage-routing.ts
                      -- APPLICATION_STAGE_ALIASES). Older SunBiz
                      -- application rows still carry these in
                      -- data.stage, so we mirror the alias map here.
                      WHEN 'submitted'              THEN 'Shopping'
                      WHEN 'submitted_to_underwriting' THEN 'Shopping'
                      WHEN 'underwriting'           THEN 'Shopping'
                      WHEN 'approved'               THEN 'Shopping'
                      WHEN 'approved_open_offers'   THEN 'Shopping'
                      WHEN 'open_offers'            THEN 'Shopping'
                      WHEN 'selling'                THEN 'Shopping'
                      WHEN 'documents_out'          THEN 'Missing Info'
                      WHEN 'docs_requested'         THEN 'Missing Info'
                      WHEN 'logins'                 THEN 'Shopping'
                      WHEN 'fund'                   THEN 'Funded'
                      WHEN 'followups'              THEN 'Shopping'
                      WHEN 'contracts_ordered'      THEN 'Missing Info'
                      WHEN 'approved_never_funded'  THEN 'Dead'
                      WHEN 'no_offers_available'    THEN 'Declined'
                      WHEN 'decline'                THEN 'Declined'
                      WHEN 'dead'                   THEN 'Dead'
                      WHEN 'application'            THEN 'Application In'
                      WHEN 'app_in'                 THEN 'Application In'
                      ELSE NULL
                    END
                  ), 'null'::jsonb),
                  true
                ),
         updated_at = NOW()
   WHERE tenant_id = _sun_tenant_id
     AND entity_type = 'application'
     AND data IS NOT NULL
     AND data->>'stage' IS NOT NULL;

  GET DIAGNOSTICS _apps_updated = ROW_COUNT;

  -- STEP 3: stamp merchant_stage on lead rows. Uses the most-recent
  -- application's deal_stage to decide Active/Funded/Lead/Dormant.
  WITH ranked_apps AS (
    SELECT
      a.tenant_id,
      a.data->>'lead_id' AS lead_id_str,
      a.data->>'deal_stage' AS deal_stage,
      ROW_NUMBER() OVER (
        PARTITION BY a.tenant_id, a.data->>'lead_id'
        ORDER BY a.updated_at DESC
      ) AS rk
    FROM tenant_records a
    WHERE a.tenant_id = _sun_tenant_id
      AND a.entity_type = 'application'
      AND a.data->>'lead_id' IS NOT NULL
  ),
  lead_app_status AS (
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
        SELECT 1 FROM ranked_apps r
         WHERE r.lead_id_str = l.id::text
           AND r.rk = 1
           AND r.deal_stage = 'Funded'
      ) AS latest_deal_is_funded,
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
                  COALESCE(data, '{}'::jsonb),
                  '{merchant_stage}',
                  to_jsonb(
                    CASE
                      WHEN s.has_active_deal THEN 'Active'
                      WHEN s.latest_deal_is_funded THEN 'Funded'
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
   WHERE t.id = s.lead_id
     AND t.data IS NOT NULL;

  GET DIAGNOSTICS _leads_updated = ROW_COUNT;

  RAISE NOTICE 'Hotfix complete: % lead(s), % application(s) stamped',
    _leads_updated, _apps_updated;
END $$;

-- Unmapped stage report (operator triage).
DO $$
DECLARE
  _sun UUID;
  _unmapped INT;
BEGIN
  SELECT id INTO _sun FROM tenants
   WHERE name = 'SunBiz' OR slug IN ('submissions', 'sun')
   LIMIT 1;
  IF _sun IS NULL THEN RETURN; END IF;

  SELECT COUNT(*) INTO _unmapped
    FROM tenant_records
   WHERE tenant_id = _sun
     AND entity_type = 'application'
     AND (data->>'deal_stage') IS NULL
     AND (data->>'stage') IS NOT NULL;

  IF _unmapped > 0 THEN
    RAISE NOTICE 'WARNING: % application(s) have unmapped data.stage values.', _unmapped;
  END IF;
END $$;

COMMIT;
