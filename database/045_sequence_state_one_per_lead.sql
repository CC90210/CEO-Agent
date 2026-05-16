-- 045_sequence_state_one_per_lead.sql
--
-- Closes Codex adversarial review finding #3 from the 2026-05-15 SunBiz
-- CRM review (see brain/SUNBIZ_CRM_KNOWN_GAPS.md).
--
-- BUG: scripts/sequence_runner.py enrollment path calls _has_active_state
-- (SELECT) then _enroll_step (INSERT). Two concurrent agent_events for
-- the same (sequence_id, lead_id) both observe "no active state" and
-- both insert. The duplicate state rows then both fire step 0, so the
-- lead gets TWO copies of the first drip touch (different message_ids
-- so the send_gateway dedup doesn't catch them — they look like
-- distinct sends from the gateway's POV).
--
-- FIX: a partial UNIQUE index on sequence_state (sequence_id, lead_id)
-- WHERE status IN ('scheduled', 'failed'). The status filter is what
-- makes this "one in-flight enrollment per (sequence, lead)" rather
-- than "this lead can never re-enroll" — terminal statuses (sent,
-- cancelled) don't participate in the uniqueness, so a one_per_lead=
-- false sequence can re-enroll after a previous run completes.
--
-- After applying this migration, scripts/sequence_runner.py should
-- switch _enroll_step from plain INSERT to INSERT ... ON CONFLICT
-- (sequence_id, lead_id) WHERE status IN ('scheduled','failed') DO
-- NOTHING. Until that script change ships, the index still helps —
-- the second insert raises a unique-violation error which surfaces in
-- the daemon log and prevents the duplicate row.
--
-- Required column: sequence_state(sequence_id, lead_id) already exists
-- from migration 043. Verify before applying.

BEGIN;

-- Defensive: if migration 043 hasn't been applied to this Supabase
-- project yet, error early with a clean message instead of partially
-- creating an index against a phantom table.
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

-- The actual guarantee. PARTIAL index so only active enrollments are
-- uniqueness-constrained; once a row hits status='sent' or 'cancelled'
-- it drops out of the index and a fresh enrollment can land.
--
-- IF NOT EXISTS guards re-runs of this migration script.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sequence_state_one_active_per_lead
    ON public.sequence_state (sequence_id, lead_id)
    WHERE status IN ('scheduled', 'failed');

COMMENT ON INDEX public.idx_sequence_state_one_active_per_lead IS
  'Codex finding #3 (2026-05-15): prevents double-enrollment of the '
  'same (sequence_id, lead_id) when two concurrent agent_events fire '
  'within the SELECT-then-INSERT race window. Partial: only in-flight '
  '(scheduled/failed) rows participate so completed runs do not block '
  're-enrollment for non-one_per_lead sequences.';

COMMIT;
