-- ============================================================
-- BRAVO V6 — Migration 030: bridge_pairings unique by (tenant, fingerprint)
-- ============================================================
-- PURPOSE
-- /api/auth/pair was minting a NEW bridge_pairings row every time the
-- bridge daemon called it (whenever ~/.oasis/bridge_token was missing —
-- wizard re-run, file deleted, fresh install). CC's MacBook accumulated
-- 4 rows for the same machine_fingerprint after a few setup attempts.
--
-- The application-layer fix in commit 401c355 added a SELECT-then-
-- UPDATE-or-INSERT path keyed by (tenant_id, machine_fingerprint).
-- That works for the only known caller, but:
--   1. It's racy — two concurrent /api/auth/pair calls from the same
--      machine could both see "no existing row" and both INSERT.
--   2. Future routes / direct ops SQL could re-introduce duplicates.
--   3. Application-layer enforcement is brittle; DB-layer is bulletproof.
--
-- This migration adds a partial unique index that enforces "at most ONE
-- non-revoked pairing per (tenant_id, machine_fingerprint)". Revoked
-- rows (revoked_at IS NOT NULL) are excluded from the index, so:
--   - The 3 existing duplicates that are already revoked don't conflict.
--   - Operators can safely revoke + re-pair (revoke creates a non-conflict
--     row history; the new pair is still the only non-revoked one).
--
-- WHY PARTIAL UNIQUE rather than full UNIQUE
-- A row that's been revoked still has its (tenant_id, machine_fingerprint)
-- — the audit trail is the point of revoking instead of deleting. A full
-- UNIQUE would forbid re-pairing a previously-revoked machine, which is
-- exactly the wrong behavior. WHERE revoked_at IS NULL = "live rows
-- only" — the right invariant.
--
-- Rows where machine_fingerprint IS NULL are also excluded (no useful
-- key to dedup on). Those are legacy / hand-created rows that don't
-- come through the pair endpoint.
--
-- ROLLBACK
--   DROP INDEX IF EXISTS idx_bridge_pairings_unique_live_machine;
-- ============================================================

BEGIN;

-- Pre-flight check: if there are any LIVE duplicates today, the index
-- creation will fail. Fail loudly here so the operator knows to revoke
-- the older rows first via:
--   UPDATE bridge_pairings SET revoked_at = NOW()
--    WHERE id IN (<stale ids>);
DO $$
DECLARE
    dup_count int;
BEGIN
    SELECT count(*) INTO dup_count
    FROM (
        SELECT tenant_id, machine_fingerprint, count(*) c
          FROM public.bridge_pairings
         WHERE revoked_at IS NULL
           AND machine_fingerprint IS NOT NULL
         GROUP BY 1, 2
        HAVING count(*) > 1
    ) d;
    IF dup_count > 0 THEN
        RAISE EXCEPTION
            'Cannot create unique index: % live duplicate (tenant_id, machine_fingerprint) groups exist. '
            'Revoke older rows first.', dup_count;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_bridge_pairings_unique_live_machine
    ON public.bridge_pairings (tenant_id, machine_fingerprint)
 WHERE revoked_at IS NULL
   AND machine_fingerprint IS NOT NULL;

COMMIT;

-- After this migration, the application can safely use
--   .upsert({...}, { onConflict: 'tenant_id,machine_fingerprint' })
-- and the DB enforces the invariant atomically. The follow-up commit
-- to apps/command-center/app/api/auth/pair/route.ts uses that pattern
-- — much shorter, race-safe, and impossible to bypass from any caller.
