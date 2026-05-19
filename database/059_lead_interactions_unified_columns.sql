-- ============================================================
-- 059_lead_interactions_unified_columns.sql
-- ============================================================
-- Adds the columns the dashboard's notes + email-queue + timeline
-- code assumes exist on lead_interactions. These were supposed to
-- land via migration 003 "unified_interaction_ledger" but never
-- landed on the current Bravo Supabase project (the
-- schema_migrations registry was empty when audited 2026-05-19).
--
-- Symptoms before this migration:
--   - Drawer's Notes Save button silently 500'd (column "content_preview"
--     does not exist).
--   - Drawer's Email Queue button silently 500'd (column "direction"
--     does not exist).
--   - Timeline rendered "Partial: couldn't read interactions" because
--     the SELECT listed columns that didn't exist.
--
-- All additions nullable + IF NOT EXISTS so the migration is safely
-- re-runnable and existing rows stay valid.
--
-- Apply via: python scripts/apply_migration.py database/059_lead_interactions_unified_columns.sql
-- (Already applied via Supabase MCP on 2026-05-19; this file is for
-- future Supabase projects to pick up the schema.)
-- ============================================================

ALTER TABLE public.lead_interactions
  ADD COLUMN IF NOT EXISTS direction TEXT,
  ADD COLUMN IF NOT EXISTS content_preview TEXT,
  ADD COLUMN IF NOT EXISTS to_email TEXT,
  ADD COLUMN IF NOT EXISTS to_phone TEXT,
  ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ;

-- Backfill content_preview from content for existing rows so the
-- timeline route surfaces what's there. Truncated to 1KB to match
-- the operator-side cap.
UPDATE public.lead_interactions
SET content_preview = LEFT(COALESCE(content, ''), 1024)
WHERE content_preview IS NULL AND content IS NOT NULL AND content <> '';

-- Common operator-side query: list outbound queued emails.
CREATE INDEX IF NOT EXISTS idx_lead_interactions_outbound_queued
  ON public.lead_interactions (tenant_id, channel, direction, created_at DESC)
  WHERE direction = 'outbound';

-- Notes lookup (drawer's Notes tab queries channel='note').
CREATE INDEX IF NOT EXISTS idx_lead_interactions_notes
  ON public.lead_interactions (tenant_id, lead_id, created_at DESC)
  WHERE channel = 'note';

COMMENT ON COLUMN public.lead_interactions.direction IS
  'inbound | outbound | internal. Internal = operator note (channel=note). '
  'Outbound = drip / dashboard send / manual reply. Inbound = lead reply.';

COMMENT ON COLUMN public.lead_interactions.content_preview IS
  'First ~1KB of content body. Renders in timeline drawers without '
  'loading the full content blob. Backfilled from content column on '
  'migration 059.';
