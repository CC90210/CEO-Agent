-- 023_backfill_lead_interactions_tenant.sql
--
-- Companion to migration 022 (outbound write-back). 022 makes new sends
-- carry tenant_id correctly. This migration backfills tenant_id on the
-- N rows that send_gateway wrote with tenant_id=NULL between migration 018
-- (when the column became filterable) and 022 (the fix). Without it,
-- "Recent Outbound" still appears stale until enough new sends accumulate.
--
-- Strategy: each lead_interactions row carries lead_id; leads.tenant_id is
-- canonical. JOIN-update fills the gap. Idempotent — re-running on already-
-- backfilled rows is a no-op (WHERE tenant_id IS NULL).
--
-- Apply with: python scripts/apply_migration.py database/023_backfill_lead_interactions_tenant.sql

BEGIN;

UPDATE public.lead_interactions li
SET tenant_id = l.tenant_id
FROM public.leads l
WHERE li.tenant_id IS NULL
  AND li.lead_id = l.id
  AND l.tenant_id IS NOT NULL;

COMMIT;
