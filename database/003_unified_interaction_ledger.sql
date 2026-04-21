-- ============================================================
-- BRAVO V5.6 — Migration 003: Unified Interaction Ledger
-- Apply via: python scripts/apply_migration.py database/003_unified_interaction_ledger.sql
-- ============================================================
-- PURPOSE
-- Extends the existing `lead_interactions` table into the single source of
-- truth for every outbound action across every channel (email, instagram,
-- linkedin, phone, skool, n8n_inbound).
--
-- Before this migration, four Python engines wrote to three different places
-- (email_log / lead_interactions / funnel_leads.follow_up_count), and the
-- N8N inbound qualifier wrote to none of them. No engine could reliably
-- answer "was this lead contacted in the last 72 hours?" before acting.
--
-- After this migration, `lead_interactions` carries everything needed for
-- architectural idempotency (cooldown_until), source tracing (agent_source),
-- and free-form context (metadata JSONB). The scripts/send_gateway.py build
-- uses these columns as its primary pre-send check.
--
-- DESIGN DECISIONS
-- 1. EXTEND, don't create a new table. Three engines already write here.
--    Adding a second ledger would deepen the fragmentation this migration
--    is meant to close. See audit report 2026-04-20.
-- 2. IF NOT EXISTS on every DDL statement. This migration is safe to re-run
--    and safe to apply mid-traffic — purely additive, no DROP/RENAME/TYPE
--    change, no index rebuild pressure on an empty table.
-- 3. Partial indexes where the filter column is often NULL. Saves storage
--    and keeps lookups on "has cooldown" / "has agent_source" fast.
-- ============================================================

-- 1. NEW COLUMNS ---------------------------------------------------------------

-- cooldown_until: when (if ever) the NEXT outbound action on this
-- lead+channel is allowed. send_gateway reads this to block early retries.
ALTER TABLE lead_interactions
  ADD COLUMN IF NOT EXISTS cooldown_until TIMESTAMPTZ;

-- agent_source: which code path performed the action. Examples:
--   'outreach_engine', 'outreach_batch', 'funnel_nurture', 'email_engine',
--   'booking_engine', 'instagram_engine', 'n8n_inbound', 'manual_cc'.
-- Critical for debugging duplicate sends and for auditing what each
-- autonomous engine did on any given day.
ALTER TABLE lead_interactions
  ADD COLUMN IF NOT EXISTS agent_source TEXT;

-- metadata: JSONB bucket for per-interaction context the gateway doesn't
-- know how to model yet (brand identity, persona used, sentiment, template
-- id, meet link, etc.). lead_engine.cmd_interact already wrote here on
-- older rows; IF NOT EXISTS makes this a no-op if the column exists.
ALTER TABLE lead_interactions
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- 2. INDEXES -------------------------------------------------------------------

-- Most common query: "has this lead been contacted on this channel recently?"
-- Supports send_gateway.can_act() pre-send check.
CREATE INDEX IF NOT EXISTS idx_lead_interactions_entity_channel
  ON lead_interactions (lead_id, channel, created_at DESC);

-- Cooldown enforcement: "are we still in a cooldown window for this lead?"
-- Partial index — most rows have NULL cooldown_until (logged-only events).
CREATE INDEX IF NOT EXISTS idx_lead_interactions_cooldown
  ON lead_interactions (lead_id, cooldown_until)
  WHERE cooldown_until IS NOT NULL;

-- Daily-cap enforcement: "how many emails did we send in the last 24h?"
CREATE INDEX IF NOT EXISTS idx_lead_interactions_channel_created
  ON lead_interactions (channel, created_at DESC);

-- Source audit: "what did outreach_batch do today?"
CREATE INDEX IF NOT EXISTS idx_lead_interactions_agent_source
  ON lead_interactions (agent_source, created_at DESC)
  WHERE agent_source IS NOT NULL;

-- 3. COMMENTS (documentation lives with the schema) ---------------------------

COMMENT ON COLUMN lead_interactions.cooldown_until IS
  'When the next outbound action on (lead_id, channel) is allowed. '
  'send_gateway blocks sends until now() >= cooldown_until. NULL means '
  'no cooldown applies (e.g., inbound events, manual notes).';

COMMENT ON COLUMN lead_interactions.agent_source IS
  'Which engine performed this action. Used for cross-engine audit and to '
  'distinguish autonomous sends from manual CC replies. Free-form text; '
  'see scripts/send_gateway.py AGENT_SOURCES for the canonical values.';

COMMENT ON COLUMN lead_interactions.metadata IS
  'JSONB bag for per-interaction context: brand, persona, sentiment, '
  'template_id, meet_link, etc. The gateway writes structured keys; '
  'consumers should treat unknown keys as opaque.';

-- ============================================================
-- END OF MIGRATION 003
-- ============================================================
