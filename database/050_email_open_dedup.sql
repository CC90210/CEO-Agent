-- ============================================================================
-- Migration 050 — email_open_events dedup hardening
--
-- Background: the /api/track/open/[id] pixel endpoint accepts unauthenticated
-- GETs (it has to — mail clients fetch the pixel without a session). The
-- route resolves tenant_id by lookup, so cross-tenant data leakage is
-- impossible, but a known reservation_id can be hit repeatedly to inflate
-- the row count for that message. Pre-launch volume is fine; this index
-- closes the vector before commercial SMS / cold email blasts go live.
--
-- Strategy: partial unique index on (outbound_message_id, ip_hash, opened_at::date).
-- Same recipient (by ip hash) hitting the same message on the same day
-- counts as one open. Re-opens across days still count. IP hash null —
-- e.g. when behind a corporate proxy that strips x-forwarded-for — falls
-- through to the regular index (no dedup), which is the right trade —
-- we'd rather over-count anonymous opens than silently drop a legit one.
--
-- The route's INSERT must add `ON CONFLICT ... DO NOTHING` to take
-- advantage of this index; without the route change, the second hit
-- raises a unique-violation that lands in server logs. Route change
-- ships in the same commit as this migration.
-- ============================================================================

BEGIN;

-- (outbound_message_id, ip_hash) — same recipient (by ip-hash) only
-- counts once per message regardless of how many times they re-open.
-- Operator timeline cares "did they open" not "how often", so collapsing
-- re-opens is acceptable. opened_at::date can't be in the index because
-- Postgres' date cast isn't IMMUTABLE (timezone-sensitive); a simpler
-- (msg, ip) unique constraint is the strongest IMMUTABLE form.
--
-- Anonymous opens (ip_hash NULL — corporate proxy stripped the header)
-- skip the constraint via the partial index WHERE clause so we still
-- record them. The trade-off vs alternative: over-count anonymous opens
-- rather than silently drop them.

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_open_events_dedup
    ON public.email_open_events (outbound_message_id, ip_hash)
    WHERE ip_hash IS NOT NULL;

COMMENT ON INDEX public.idx_email_open_events_dedup IS
  'One open per (message, ip-hash). Closes the tracking-pixel spam '
  'vector for known reservation_ids. Anonymous opens (ip_hash IS NULL) '
  'are excluded from the constraint so the route still records them.';

COMMIT;
