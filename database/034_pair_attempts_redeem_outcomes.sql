-- ============================================================
-- BRAVO V6 — Migration 034: extend pair_attempts outcome vocabulary
-- ============================================================
-- PURPOSE
-- Migration 031 created public.pair_attempts with a CHECK constraint
-- limiting outcome to 5 values that only fit /api/auth/pair. Now that
-- the rate-limit + audit pattern is being extended to /api/auth/pair-
-- code/redeem (same threat surface, weaker auth), we need outcomes
-- that describe the redeem flow too.
--
-- Added outcomes:
--   code_invalid_shape — request body didn't match XXX-XXX-XXX
--   code_not_found     — code doesn't exist in pair_codes table
--   code_expired       — code passed its TTL
--   code_consumed      — code was already redeemed (single-use)
--   code_redeem_failed — generic 500 from the redeem RPC
--
-- The 5 original values (ok, invalid_hmac, invalid_bearer, rate_limited,
-- missing_headers) are preserved.
--
-- profile_id column is intentionally kept as `text` (not uuid) so it can
-- hold either a real UUID (pair endpoint) or a synthetic key like
-- 'redeem:<ip>' (redeem endpoint). The column name is a slight misnomer
-- now — it's really a 'rate-limit key' — but renaming would churn the
-- index and the application reads. Comment block on the table updated.
-- ============================================================

BEGIN;

ALTER TABLE public.pair_attempts
    DROP CONSTRAINT IF EXISTS pair_attempts_outcome_check;

ALTER TABLE public.pair_attempts
    ADD CONSTRAINT pair_attempts_outcome_check
    CHECK (outcome IN (
        -- pair endpoint outcomes (migration 031)
        'ok',
        'invalid_hmac',
        'invalid_bearer',
        'rate_limited',
        'missing_headers',
        -- pair-code/redeem outcomes (this migration)
        'code_invalid_shape',
        'code_not_found',
        'code_expired',
        'code_consumed',
        'code_redeem_failed'
    ));

COMMENT ON TABLE public.pair_attempts IS
    'Audit + rate-limit log for /api/auth/pair AND /api/auth/pair-code/redeem. '
    'profile_id column holds either a real UUID (pair endpoint, keyed on '
    'OASIS_PROFILE_ID) or a synthetic key like ''redeem:<ip>'' (redeem '
    'endpoint, keyed on client IP). See migrations 031 + 034 + brain/'
    'SECURITY_MODEL.md §6.';

COMMIT;
