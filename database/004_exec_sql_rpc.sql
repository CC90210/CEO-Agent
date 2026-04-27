-- ============================================================
-- BRAVO V5.6 — Migration 004: exec_sql RPC (permanent migration path)
-- Apply via: python scripts/apply_migration.py database/004_exec_sql_rpc.sql
-- ============================================================
-- PURPOSE
-- Creates an exec_sql(sql TEXT) RPC function that future migrations can
-- call through the standard service-role key path. This eliminates the
-- dependency on the 30-day-expiring Supabase Personal Access Token for
-- routine migration work.
--
-- After migration 004 is applied once via the Management API (token-based
-- path), scripts/apply_migration.py can call this RPC using the never-
-- expiring BRAVO_SUPABASE_SERVICE_ROLE_KEY. No more 30-day rotation pain.
--
-- SECURITY
-- 1. SECURITY DEFINER so the function runs with the creator's privileges.
--    The service role (what supabase_tool.py uses) already has full DDL
--    access in practice, so this doesn't grant new privileges — it just
--    exposes them through a callable interface.
-- 2. Server-side DDL guard. The function rejects any SQL that contains
--    DROP TABLE, TRUNCATE, DROP DATABASE, or DROP SCHEMA. This is defence
--    in depth: the client-side guard in apply_migration.py catches these
--    before dispatch, but a second layer means a bug in the client can't
--    bypass it.
-- 3. REVOKE EXECUTE from PUBLIC, GRANT only to service_role. The anon
--    role cannot call this function — only authenticated service-role
--    holders (the server-side agent code) can.
--
-- USAGE
--   Client-side (Python):
--     client.rpc('exec_sql', {'sql_query': 'ALTER TABLE ...'}).execute()
-- ============================================================

CREATE OR REPLACE FUNCTION exec_sql(sql_query TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  upper_sql TEXT;
BEGIN
  -- Server-side guard: refuse destructive DDL regardless of caller claims.
  -- Matches the client-side BLOCKED_PATTERNS in apply_migration.py.
  upper_sql := upper(sql_query);
  IF upper_sql ~ '\mDROP\s+TABLE\M' THEN
    RAISE EXCEPTION 'exec_sql: DROP TABLE is refused by server-side guard. '
                    'Use the Supabase Dashboard for destructive DDL.';
  END IF;
  IF upper_sql ~ '\mTRUNCATE\s+TABLE\M' OR upper_sql ~ '\mTRUNCATE\s+\w+\M' THEN
    RAISE EXCEPTION 'exec_sql: TRUNCATE is refused by server-side guard.';
  END IF;
  IF upper_sql ~ '\mDROP\s+DATABASE\M' THEN
    RAISE EXCEPTION 'exec_sql: DROP DATABASE is refused by server-side guard.';
  END IF;
  IF upper_sql ~ '\mDROP\s+SCHEMA\M' THEN
    RAISE EXCEPTION 'exec_sql: DROP SCHEMA is refused by server-side guard.';
  END IF;

  EXECUTE sql_query;
  RETURN jsonb_build_object(
    'status', 'ok',
    'executed_at', NOW()
  );
END;
$$;

-- Lock down the RPC. Only the service role may call it (agent code paths).
REVOKE ALL ON FUNCTION exec_sql(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec_sql(TEXT) FROM anon;
REVOKE ALL ON FUNCTION exec_sql(TEXT) FROM authenticated;
GRANT EXECUTE ON FUNCTION exec_sql(TEXT) TO service_role;

COMMENT ON FUNCTION exec_sql(TEXT) IS
  'Execute arbitrary DDL/DML from the service-role path. Refuses DROP TABLE, '
  'TRUNCATE, DROP DATABASE, DROP SCHEMA server-side. Created 2026-04-20 to '
  'eliminate dependency on the 30-day Supabase Personal Access Token for '
  'routine migrations. See scripts/apply_migration.py for caller wiring.';

-- ============================================================
-- END OF MIGRATION 004
-- ============================================================
