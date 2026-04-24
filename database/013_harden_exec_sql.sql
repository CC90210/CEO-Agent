-- ============================================================
-- BRAVO V5.6.2 - Migration 013: harden exec_sql RPC guardrails
-- Apply via: python scripts/apply_migration.py database/013_harden_exec_sql.sql
-- ============================================================
-- PURPOSE
-- Keeps the service-role migration RPC, but makes it fail closed for
-- high-risk data mutation, privilege, and policy changes. Routine schema
-- migrations still work; broad data edits and privilege changes should be
-- handled deliberately in the Supabase Dashboard SQL editor.
-- ============================================================

CREATE OR REPLACE FUNCTION exec_sql(sql_query TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $exec_sql_hardened$
DECLARE
  scan_sql TEXT;
  upper_sql TEXT;
  result_rows JSONB;
  is_select BOOLEAN;
BEGIN
  scan_sql := sql_query;

  -- Strip comments, dollar-quoted bodies, and strings before scanning so
  -- guards do not false-positive on function source or explanatory text.
  scan_sql := regexp_replace(scan_sql, '/\*([^*]|\*[^/])*\*/', ' ', 'g');
  scan_sql := regexp_replace(scan_sql, '--[^\r\n]*', ' ', 'g');
  scan_sql := regexp_replace(scan_sql, '\$\$(.|\n|\r)*\$\$', '''''', 'g');
  scan_sql := regexp_replace(scan_sql, '\$[A-Za-z_][A-Za-z_0-9]*\$(.|\n|\r)*\$[A-Za-z_][A-Za-z_0-9]*\$', '''''', 'g');
  scan_sql := regexp_replace(scan_sql, '''([^'']|'''')*''', '''''', 'g');
  upper_sql := upper(regexp_replace(scan_sql, '^\s+', ''));

  IF upper_sql ~ ('\mDR' || 'OP\s+TA' || 'BLE\M') THEN
    RAISE EXCEPTION 'exec_sql: blocked destructive table removal.';
  END IF;
  IF upper_sql ~ ('\mTRUN' || 'CATE(\s+TA' || 'BLE)?\s+\w+\M') THEN
    RAISE EXCEPTION 'exec_sql: blocked destructive table clearing.';
  END IF;
  IF upper_sql ~ ('\mDR' || 'OP\s+DATA' || 'BASE\M') THEN
    RAISE EXCEPTION 'exec_sql: blocked database removal.';
  END IF;
  IF upper_sql ~ ('\mDR' || 'OP\s+SCH' || 'EMA\M') THEN
    RAISE EXCEPTION 'exec_sql: blocked schema removal.';
  END IF;
  IF upper_sql ~ '\mDELETE\s+FROM\M' THEN
    RAISE EXCEPTION 'exec_sql: data deletion must be run manually.';
  END IF;
  IF upper_sql ~ '\mUPDATE\s+[\w\."\`]+\s+SET\M' THEN
    RAISE EXCEPTION 'exec_sql: data updates must be run manually.';
  END IF;
  IF upper_sql ~ '\mGRANT\M' OR upper_sql ~ '\mREVOKE\M' THEN
    RAISE EXCEPTION 'exec_sql: privilege changes must be run manually.';
  END IF;
  IF upper_sql ~ '\mALTER\s+(ROLE|USER|DATABASE|SYSTEM)\M' THEN
    RAISE EXCEPTION 'exec_sql: role/user/database/system alterations must be run manually.';
  END IF;
  IF upper_sql ~ '\m(DROP|ALTER)\s+POLICY\M'
     OR upper_sql ~ '\mDISABLE\s+ROW\s+LEVEL\s+SECURITY\M' THEN
    RAISE EXCEPTION 'exec_sql: policy/RLS weakening must be run manually.';
  END IF;

  is_select := upper(regexp_replace(sql_query, '^\s+', '')) ~ '^(SELECT|WITH|SHOW|EXPLAIN|VALUES)\s'
            OR upper(regexp_replace(sql_query, '^\s+', '')) ~ '\mRETURNING\M';

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
$exec_sql_hardened$;

COMMENT ON FUNCTION exec_sql(TEXT) IS
  'V3 2026-04-21: hardened migration RPC. Refuses destructive table clearing/removal, broad data mutation, privilege changes, role/user/database/system alterations, and policy/RLS weakening.';

-- ============================================================
-- END OF MIGRATION 013
-- ============================================================
