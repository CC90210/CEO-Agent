-- ============================================================
-- Migration 103: Harden SECURITY DEFINER functions — pin search_path
-- ============================================================
-- Empire DB (phctllmtsogkovoilwos). Security audit 2026-06-21 (P1-2):
-- 14 SECURITY DEFINER functions in `public` had no `search_path` pinned, so a
-- caller who creates a same-named object in a schema earlier on their search_path
-- could hijack the function's resolution (CVE-class: mutable search_path in
-- SECURITY DEFINER). Pinning to `public, pg_temp` is non-breaking (it's what they
-- already resolve to) and reversible (`ALTER FUNCTION ... RESET search_path`).
--
-- Idempotent: re-running only touches functions that still lack a pin.
-- Generated from the live catalog, not hand-typed.
-- ============================================================

DO $mig$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.prosecdef
      AND NOT EXISTS (
        SELECT 1 FROM unnest(coalesce(p.proconfig, '{}')) c
        WHERE c LIKE 'search_path=%'
      )
  LOOP
    EXECUTE format('ALTER FUNCTION %s SET search_path = public, pg_temp', r.sig);
    RAISE NOTICE 'pinned search_path on %', r.sig;
  END LOOP;
END
$mig$;
