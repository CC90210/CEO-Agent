-- ============================================================================
-- Migration 093 — call lifecycle columns on lead_interactions
--
-- Phase 1 of the TT + Kixie full embedding plan (2026-06-01).
--
-- Kixie call webhooks (Start Call, Answered, End Call, Call Outcome, CI
-- Summary) carry call metadata we want to land on the lead's interaction
-- ledger: who called whom, how long, what disposition, recording / transcript
-- URLs for in-drawer playback. Today the row exists but the metadata is
-- jammed into jsonb metadata; promoting the load-bearing fields to columns
-- lets the timeline + dashboard tiles query them without jsonb scans.
--
-- Why columns over jsonb:
--   - Recording URL is used by drawer audio playback every time the lead
--     drawer opens; jsonb extraction adds latency on every render.
--   - call_duration_sec rolls up into the "Today's calls" dashboard tile
--     (count + sum); indexed numeric column is materially faster.
--   - disposition is filterable (operators want "show me my no-answers
--     from yesterday"); a column with a partial index beats jsonb path.
--   - kixie_call_id is the idempotency anchor for webhooks — every event
--     for the same call references the same callid; we need a uniqueness
--     guarantee so duplicate webhooks (Kixie retries 5xx for ~10 min)
--     don't double-write.
--
-- All columns nullable so the migration is non-breaking. Email rows + SMS
-- rows have no call fields; that's fine.
--
-- Idempotent. Re-runnable.
-- ============================================================================

ALTER TABLE public.lead_interactions
    ADD COLUMN IF NOT EXISTS recording_url     text,
    ADD COLUMN IF NOT EXISTS transcript_url    text,
    ADD COLUMN IF NOT EXISTS disposition       text,
    ADD COLUMN IF NOT EXISTS call_outcome      text,
    ADD COLUMN IF NOT EXISTS call_duration_sec integer,
    ADD COLUMN IF NOT EXISTS kixie_call_id     text;

-- Partial unique index on kixie_call_id so duplicate webhook deliveries
-- (Kixie retries failed webhook POSTs for ~10 minutes) can't double-write.
-- Webhook handler ON CONFLICT DO UPDATE merges metadata in atomically.
CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_interactions_kixie_call_id_unique
    ON public.lead_interactions (kixie_call_id)
    WHERE kixie_call_id IS NOT NULL;

-- Index for the "Today's calls" dashboard tile + drawer timeline filter
-- by channel='phone' under a tenant. created_at sort gives drawer view.
CREATE INDEX IF NOT EXISTS idx_lead_interactions_phone_by_tenant
    ON public.lead_interactions (tenant_id, channel, created_at DESC)
    WHERE channel = 'phone';

-- Comments for the column registry — operators inspecting the table via
-- supabase studio see what each new column means.
COMMENT ON COLUMN public.lead_interactions.recording_url IS
    'Kixie call recording URL — populated by Call Outcome / End Call webhook. Drawer audio player streams from here.';
COMMENT ON COLUMN public.lead_interactions.transcript_url IS
    'Optional transcript URL (Kixie Conversation Intelligence). Streamed into the drawer if present.';
COMMENT ON COLUMN public.lead_interactions.disposition IS
    'Operator-set call disposition (e.g. "Interested", "Voicemail", "Wrong number"). From Disposition webhook.';
COMMENT ON COLUMN public.lead_interactions.call_outcome IS
    'Kixie auto-classified call outcome (answered / voicemail / missed / busy / failed). From Call Outcome webhook.';
COMMENT ON COLUMN public.lead_interactions.call_duration_sec IS
    'Talk time in seconds. End Call webhook. Aggregated by the daily-calls dashboard tile.';
COMMENT ON COLUMN public.lead_interactions.kixie_call_id IS
    'Kixie callid — idempotency anchor for multi-webhook call lifecycle.';
