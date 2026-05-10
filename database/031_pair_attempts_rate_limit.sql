-- ============================================================
-- BRAVO V6 — Migration 031: pair_attempts log + rate-limit gate
-- ============================================================
-- PURPOSE
-- /api/auth/pair currently has no rate limit. A bad actor with a stolen
-- OASIS_OUTBOUND_HMAC_SECRET (or just guessing valid profile_id UUIDs)
-- could hammer the endpoint. The constant-time HMAC compare from
-- Tier C1 prevents timing-leak; rate-limiting prevents brute-force.
--
-- Single-purpose table — NOT a general audit_log. We deliberately
-- scope this to the pair endpoint so it stays small + indexable. A
-- broader audit_log table is in SECURITY_MODEL.md as future work
-- and would supersede this if/when it ships.
--
-- USAGE PATTERN (in /api/auth/pair):
--   1. Before HMAC verify: SELECT count(*) WHERE profile_id=$1
--      AND attempted_at > now() - interval '60 seconds'
--      AND outcome IN ('invalid_hmac', 'invalid_bearer'). If > 10,
--      return 429 + record outcome='rate_limited'.
--   2. After verify (success OR fail): INSERT a row with the outcome.
--
-- TTL: rows older than 24h serve no operational purpose. Could be
-- pruned by a periodic job; at low volume the table stays small enough
-- that pruning is a future optimization, not a blocker.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.pair_attempts (
    id           bigserial   PRIMARY KEY,
    profile_id   text        NOT NULL,
    outcome      text        NOT NULL,
    attempted_at timestamptz NOT NULL DEFAULT now(),
    ip           inet
);

-- The check constraint documents the outcome vocabulary at the DB level
-- so the application can't silently log a bogus value. Update both sides
-- (constraint + route code) when adding a new outcome.
ALTER TABLE public.pair_attempts
    DROP CONSTRAINT IF EXISTS pair_attempts_outcome_check;
ALTER TABLE public.pair_attempts
    ADD CONSTRAINT pair_attempts_outcome_check
    CHECK (outcome IN ('ok', 'invalid_hmac', 'invalid_bearer', 'rate_limited', 'missing_headers'));

-- Hot path is "count failures by profile in last N seconds" — a (profile_id,
-- attempted_at DESC) index makes that an index-only scan.
CREATE INDEX IF NOT EXISTS idx_pair_attempts_profile_recent
    ON public.pair_attempts (profile_id, attempted_at DESC);

-- Service role only. This table holds security-sensitive metadata (which
-- profile_ids are being probed, from which IPs); not exposed to tenant
-- users. RLS enabled with no policy = effective lock-down for non-service
-- callers. Service-role queries bypass RLS by design.
ALTER TABLE public.pair_attempts ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.pair_attempts IS
    'Audit + rate-limit log for /api/auth/pair. See migration 031 + brain/SECURITY_MODEL.md §4.';

COMMIT;
