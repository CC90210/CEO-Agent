-- ============================================================
-- 060_lead_interactions_drop_legacy_lead_fk.sql
-- ============================================================
-- Drops the legacy FK from lead_interactions.lead_id → leads(id).
--
-- The dashboard (Phase 5+) reads leads from tenant_records
-- (entity_type='lead'), not from public.leads. SunBiz tenant leads,
-- forms-ingested leads, and CSV-imported leads all live in
-- tenant_records. `public.leads` only holds pre-2026-05-15 OASIS-side
-- test data (~116 historical rows).
--
-- The FK constraint was breaking every new interaction insert from
-- the drawer's Notes / Email Queue / SMS composer because the
-- referenced lead_id didn't exist in `public.leads` — it existed in
-- `tenant_records`.
--
-- No replacement FK to tenant_records because tenant_records is
-- polymorphic (entity_type ∈ {lead, application, offer, ...}). A
-- column-level FK can't enforce the entity_type restriction.
-- Application-level integrity is the right tradeoff.
--
-- Applied via Supabase MCP on 2026-05-19; this file is for future
-- Supabase projects to pick up the schema.
-- ============================================================

ALTER TABLE public.lead_interactions
  DROP CONSTRAINT IF EXISTS lead_interactions_lead_id_fkey;

COMMENT ON COLUMN public.lead_interactions.lead_id IS
  'Logical lead reference. Points to either public.leads(id) for legacy '
  'rows or tenant_records.id for manifest-era leads. No FK enforcement '
  'because tenant_records is polymorphic (entity_type-discriminated). '
  'Application code resolves the right table via the row''s tenant.';
