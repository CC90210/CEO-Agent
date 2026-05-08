-- Migration 031 — onboarding_completed_at
--
-- Adds a single column to user_profiles so middleware can force users who
-- abandoned mid-onboarding back to /onboarding when they next sign in.
-- Fully backwards-compatible: existing profiles get NULL, which the
-- middleware-side gate treats as "incomplete" — so legacy users will see
-- the onboarding flow once. They can either complete it or click "Skip
-- for now" (the existing escape hatch in app/onboarding/page.tsx).
--
-- Set the column on profiles created BEFORE this migration to NOW() so we
-- don't drag established operators back through the wizard. The signal is
-- "they have an agent_model_config row" — if they've configured at least
-- one agent, treat onboarding as complete.

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ;

-- Backfill: anyone who already has an agent_model_config row in their
-- tenant has already done the wizard (or done it manually via /settings).
-- Mark them complete so they don't get re-routed.
UPDATE user_profiles up
SET onboarding_completed_at = NOW()
WHERE onboarding_completed_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM agent_model_config amc
    WHERE amc.tenant_id = up.tenant_id
  );

COMMENT ON COLUMN user_profiles.onboarding_completed_at IS
  'Set to NOW() when the user completes the /onboarding wizard. Middleware redirects authed users with NULL here to /onboarding so they can finish.';
