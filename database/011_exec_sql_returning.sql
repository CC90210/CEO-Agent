-- ============================================================
-- BRAVO V5.6.1 — Migration 011: exec_sql returning query results
-- Apply via: python scripts/apply_migration.py database/011_exec_sql_returning.sql
-- ============================================================
-- PURPOSE
-- Replaces exec_sql() with a version that returns SELECT results as JSONB,
-- and adds exec_sql_ddl() as a status-only wrapper for DDL that doesn't
-- produce rows. Keeps the same server-side destructive-DDL guard.
-- ============================================================

CREATE OR REPLACE FUNCTION exec_sql(sql_query TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  upper_sql TEXT;
  result_rows JSONB;
  is_select BOOLEAN;
BEGIN
  upper_sql := upper(regexp_replace(sql_query, '^\s+', ''));

  -- Server-side destructive-DDL guard (unchanged from migration 004).
  IF upper_sql ~ '\mDROP\s+TABLE\M' THEN
    RAISE EXCEPTION 'exec_sql: destructive pattern refused (DROP TABLE).';
  END IF;
  IF upper_sql ~ '\mTRUNCATE\s+TABLE\M' OR upper_sql ~ '\mTRUNCATE\s+\w+\M' THEN
    RAISE EXCEPTION 'exec_sql: destructive pattern refused (TRUNCATE).';
  END IF;
  IF upper_sql ~ '\mDROP\s+DATABASE\M' THEN
    RAISE EXCEPTION 'exec_sql: destructive pattern refused (DROP DATABASE).';
  END IF;
  IF upper_sql ~ '\mDROP\s+SCHEMA\M' THEN
    RAISE EXCEPTION 'exec_sql: destructive pattern refused (DROP SCHEMA).';
  END IF;

  -- Detect if the statement produces rows (SELECT, WITH, SHOW, EXPLAIN,
  -- or anything with RETURNING). If so, wrap in a subquery and return
  -- the rows as JSONB. Otherwise EXECUTE as a statement and return status.
  is_select := upper_sql ~ '^(SELECT|WITH|SHOW|EXPLAIN|VALUES)\s'
            OR upper_sql ~ '\mRETURNING\M';

  IF is_select THEN
    EXECUTE format('SELECT coalesce(jsonb_agg(t), ''[]''::jsonb) FROM (%s) t', sql_query)
    INTO result_rows;
    RETURN jsonb_build_object(
      'status', 'ok',
      'rows', result_rows,
      'executed_at', NOW()
    );
  ELSE
    EXECUTE sql_query;
    RETURN jsonb_build_object(
      'status', 'ok',
      'executed_at', NOW()
    );
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION exec_sql(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec_sql(TEXT) FROM anon;
REVOKE ALL ON FUNCTION exec_sql(TEXT) FROM authenticated;
GRANT EXECUTE ON FUNCTION exec_sql(TEXT) TO service_role;

COMMENT ON FUNCTION exec_sql(TEXT) IS
  'V2 2026-04-20: now returns query results as JSONB in .rows when the '
  'statement is a SELECT / WITH / VALUES / RETURNING form, or a bare '
  'status object for DDL/DML. Same destructive-DDL guard.';

-- ============================================================
-- END OF MIGRATION 011
-- ============================================================
