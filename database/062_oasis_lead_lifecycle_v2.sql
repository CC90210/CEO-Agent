-- ============================================================================
-- Migration 062 — OASIS lead lifecycle v2 (7 → 11 stage migration)
--
-- The OASIS lead funnel was originally seeded with 7 stages
--   ["new", "contacted", "qualified", "proposal", "negotiation",
--    "won", "lost"]
-- which collapsed several distinct operator-facing moments into a
-- single "won" bucket. CC asked for a fuller lifecycle that mirrors
-- how an AI-agency deal actually moves:
--
--   new_contact   — fresh lead, no outreach sent
--   outreach      — first touch sent (cold email / DM / call)
--   discovery     — discovery call scheduled or completed
--   qualified     — replied with intent and confirmed as a fit
--   proposal      — SOW / proposal delivered, awaiting response
--   negotiation   — back-and-forth on scope, terms, or price
--   onboarding    — deal closed, client being onboarded
--   active_client — live retainer / project in delivery
--   churned       — was an active client, now departed
--   lost          — never closed (passed, ghosted, not a fit)
--   archived      — permanently inactive
--
-- Mapping from old → new for existing OASIS rows:
--   new        → new_contact
--   contacted  → outreach
--   won        → active_client
--   qualified / proposal / negotiation / lost → unchanged
--
-- The enum lives in lib/manifest/seeds.ts (OASIS_SEED.data_model.lead.stage)
-- and is validated at write time by the manifest layer. The Supabase
-- column is a free-form text JSONB key (tenant_records.data->>'stage')
-- so no Postgres enum type needs altering — just a data update.
--
-- Scope: ONLY the OASIS tenant. SunBiz / Suga rows are untouched. We
-- look the tenant up by slug='oasis' so the migration is portable
-- across staging / production where the UUID differs.
-- ============================================================================

BEGIN;

DO $$
DECLARE
  _oasis_tenant_id UUID;
  _updates JSONB := '[]'::JSONB;
  _row RECORD;
BEGIN
  SELECT id INTO _oasis_tenant_id FROM tenants WHERE slug = 'oasis' LIMIT 1;
  IF _oasis_tenant_id IS NULL THEN
    RAISE NOTICE 'No tenant with slug=oasis — nothing to migrate.';
    RETURN;
  END IF;

  -- Bulk remap. Three keys change; the other four are stable.
  UPDATE tenant_records
     SET data = jsonb_set(data, '{stage}', '"new_contact"'::JSONB),
         updated_at = NOW()
   WHERE tenant_id = _oasis_tenant_id
     AND entity_type = 'lead'
     AND data->>'stage' = 'new';

  UPDATE tenant_records
     SET data = jsonb_set(data, '{stage}', '"outreach"'::JSONB),
         updated_at = NOW()
   WHERE tenant_id = _oasis_tenant_id
     AND entity_type = 'lead'
     AND data->>'stage' = 'contacted';

  UPDATE tenant_records
     SET data = jsonb_set(data, '{stage}', '"active_client"'::JSONB),
         updated_at = NOW()
   WHERE tenant_id = _oasis_tenant_id
     AND entity_type = 'lead'
     AND data->>'stage' = 'won';

  -- Visibility log so an operator running this in psql sees what moved.
  FOR _row IN
    SELECT data->>'stage' AS stage, COUNT(*) AS n
      FROM tenant_records
     WHERE tenant_id = _oasis_tenant_id
       AND entity_type = 'lead'
     GROUP BY data->>'stage'
     ORDER BY n DESC
  LOOP
    RAISE NOTICE 'OASIS lead stage % → % rows', _row.stage, _row.n;
  END LOOP;
END $$;

COMMIT;
