-- 078_lead_interactions_actor_user_id.sql
--
-- Add an `actor_user_id` column to lead_interactions so the dashboard
-- can answer "who sent / wrote / logged this?" for every row. Phase 4
-- of the SunBiz multi-employee personalization wired `acted_by_user_id`
-- as a parameter through send_gateway.log_action() and the email route,
-- but the value never landed in the database — the column didn't exist.
--
-- Without this column:
--   - The audit answer "Alex sent 47 emails this week" cannot be
--     computed from the canonical interaction table.
--   - Per-employee performance views (My Sends, My Calls) fall back
--     to fragile metadata.author_profile_id JSONB lookups.
--   - Manager visibility into who touched which deal is opaque.
--
-- The column is nullable because legacy rows + system-fired rows
-- (drip sequences with no human in the loop) won't carry an actor.
-- agent_source remains the "what process wrote this" field;
-- actor_user_id is the "which human is responsible" field.

ALTER TABLE public.lead_interactions
  ADD COLUMN IF NOT EXISTS actor_user_id uuid
    REFERENCES auth.users(id) ON DELETE SET NULL;

-- Per-employee filter index. Partial (WHERE NOT NULL) so legacy + system
-- rows stay out of the index.
CREATE INDEX IF NOT EXISTS lead_interactions_actor_user_id_idx
  ON public.lead_interactions (tenant_id, actor_user_id, created_at DESC)
  WHERE actor_user_id IS NOT NULL;

-- Comment for future schema readers.
COMMENT ON COLUMN public.lead_interactions.actor_user_id IS
  'The auth.users.id of the human employee responsible for this row. '
  'NULL for system-fired interactions (drip sequences, automated '
  'reconcilers). Use this — not metadata.author_profile_id — for any '
  'audit / per-employee analytics query.';
