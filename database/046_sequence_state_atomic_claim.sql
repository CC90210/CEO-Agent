-- 046_sequence_state_atomic_claim.sql
--
-- Closes Codex adversarial review finding #1 from the 2026-05-15 SunBiz
-- CRM review (see brain/SUNBIZ_CRM_KNOWN_GAPS.md). Round 3 R3-5.
--
-- BUG: scripts/sequence_runner.py execution_tick runs:
--      SELECT * FROM sequence_state WHERE status='scheduled' AND scheduled_for <= now() LIMIT 50
--  then iterates and calls _send_step BEFORE any status update. Two
--  workers (or a daemon that overlaps with a PM2 restart across a
--  tick boundary) can both read the same scheduled row + both
--  physically dispatch the send. send_gateway's cooldown is downstream
--  — by the time it would catch the duplicate, the second message has
--  already left for the lead.
--
-- FIX: atomic claim BEFORE _send_step. Add claimed_at + claimed_by
--  columns, then have execution_tick call a SECURITY DEFINER RPC that
--  does the claim in one UPDATE...RETURNING. The row whose UPDATE
--  returns 1 proceeds to dispatch; rows where the UPDATE returns 0
--  were already claimed by another worker and the daemon moves on.
--
-- After migration applies + sequence_runner.py picks up the new
-- _send_step path, the execution path becomes:
--
--      for row in due_rows:
--          claimed = rpc('claim_sequence_state_row', {row_id: row.id, claimer: worker_id})
--          if not claimed: continue                   # another worker won the race
--          result = _send_step(sb, claimed, sequence) # actually dispatch
--
-- Requires sequence_state table from migration 043. Defensive check
-- below errors early if 043 hasn't been applied to this Supabase
-- project yet.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'sequence_state'
    ) THEN
        RAISE EXCEPTION 'sequence_state table not found — apply database/043_drip_sequences.sql first.';
    END IF;
END
$$;

-- ============================================================================
-- Claim columns
-- ============================================================================
-- claimed_at: timestamp when a worker successfully claimed this row for
--             dispatch. NULL means unclaimed (available for any worker).
--             Set inside the RPC below; reset to NULL only when the row
--             transitions back to status='scheduled' (e.g. cooldown
--             reschedule — sequence_runner already updates scheduled_for
--             without touching the claim columns, but we explicitly
--             clear on requeue to be safe).
-- claimed_by: opaque worker identifier (PM2 instance id, hostname, etc.).
--             Useful for debugging "which daemon picked up this row".
--             Free-form text; not enforced.

ALTER TABLE public.sequence_state
    ADD COLUMN IF NOT EXISTS claimed_at  timestamptz,
    ADD COLUMN IF NOT EXISTS claimed_by  text;

-- Partial index supporting the claim's WHERE clause. The 045 partial
-- unique index already covers (sequence_id, lead_id) for in-flight
-- enrollments; this one covers the per-row claim filter.
CREATE INDEX IF NOT EXISTS idx_sequence_state_claimable
    ON public.sequence_state (scheduled_for)
    WHERE status = 'scheduled' AND claimed_at IS NULL;

-- ============================================================================
-- The claim RPC
-- ============================================================================
-- Single atomic UPDATE...RETURNING. The WHERE clause is the race
-- guard: the row must still be status='scheduled' AND claimed_at IS NULL
-- at the moment of UPDATE. Postgres acquires a row-level lock for the
-- UPDATE so only one concurrent caller's WHERE evaluates true; the
-- other caller's UPDATE matches zero rows and returns an empty set.
--
-- SECURITY DEFINER so the service-role daemon doesn't need explicit
-- grants on sequence_state to call this from the Python supabase
-- client — same pattern other RPCs in earlier migrations use.

CREATE OR REPLACE FUNCTION public.claim_sequence_state_row(
    row_id uuid,
    claimer text DEFAULT NULL
)
RETURNS SETOF public.sequence_state
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    UPDATE public.sequence_state
       SET claimed_at = now(),
           claimed_by = COALESCE(claimer, 'sequence_runner')
     WHERE id = row_id
       AND status = 'scheduled'
       AND claimed_at IS NULL
    RETURNING *;
$$;

COMMENT ON FUNCTION public.claim_sequence_state_row(uuid, text) IS
  'Codex finding #1 (2026-05-15): atomic claim for sequence_state rows '
  'before dispatch. Called by sequence_runner.execution_tick — '
  'a non-empty return means this caller wins the race and may '
  'dispatch the row; an empty return means another worker already '
  'claimed it. Pairs with the claimed_at / claimed_by columns + '
  'idx_sequence_state_claimable partial index in this same migration.';

-- ============================================================================
-- Release helper — used by execution_tick when send_gateway returned
-- cooldown (transient block, retry later). Without this, a cooldowned
-- row would stay claimed_at != NULL and never be re-picked.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.release_sequence_state_claim(row_id uuid)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    UPDATE public.sequence_state
       SET claimed_at = NULL,
           claimed_by = NULL
     WHERE id = row_id;
$$;

COMMENT ON FUNCTION public.release_sequence_state_claim(uuid) IS
  'Clear the claim on a sequence_state row so it can be picked up '
  'again on the next execution_tick. Used after a cooldown / transient '
  'reschedule. Terminal status updates (sent / failed / cancelled / '
  'suppressed) do NOT need a release call — the partial claim index '
  'only matches status=scheduled, so a sent/failed row is naturally '
  'out of contention regardless of claim state.';

COMMIT;
