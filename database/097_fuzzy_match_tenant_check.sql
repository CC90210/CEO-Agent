-- 097_fuzzy_match_tenant_check.sql — defense-in-depth for find_similar_merchants.
--
-- Migration 096 shipped find_similar_merchants as SECURITY DEFINER and
-- trusted the caller to pass an authentic tenant_id. Today the only
-- caller is /api/merchants/fuzzy-match which derives tenant_id from
-- resolveSessionContext() (impossible for the client to forge). But
-- SECURITY DEFINER means a future endpoint that forgets to derive
-- server-side could let an authenticated user query another tenant's
-- merchants by passing their tenant_id in the request body.
--
-- This migration replaces the function to add an explicit
-- tenant-membership check INSIDE the function when the caller's role
-- is authenticated. service_role still bypasses (trusted by design —
-- only server-side code holds the service-role key).
--
-- Without this defense the leak path is purely theoretical (every
-- current caller derives tenant_id server-side) but the cost of the
-- check is one indexed lookup against user_profiles, ~0.2ms — well
-- worth the foot-gun prevention.

CREATE OR REPLACE FUNCTION public.find_similar_merchants(
  p_tenant_id       uuid,
  p_business_name   text,
  p_state           text DEFAULT NULL,
  p_threshold       real DEFAULT 0.4,
  p_limit           int  DEFAULT 10
)
RETURNS TABLE (
  record_id      uuid,
  entity_type    text,
  business_name  text,
  state          text,
  similarity     real,
  ein            text,
  email          text,
  phone          text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_caller_role text;
  v_caller_uid  uuid;
  v_belongs     boolean;
BEGIN
  -- current_setting('request.jwt.claim.role') is the canonical way to
  -- read the caller's auth role from inside a Supabase function. It's
  -- set by PostgREST on every request. When NULL we treat it as
  -- service_role (server-side direct connection — same as a
  -- compromise of the service key, which is already game over).
  BEGIN
    v_caller_role := current_setting('request.jwt.claim.role', true);
  EXCEPTION WHEN OTHERS THEN
    v_caller_role := NULL;
  END;

  IF v_caller_role = 'authenticated' THEN
    -- For authenticated users, confirm they're a member of the tenant
    -- they're querying. auth.uid() is the user_profiles.auth_user_id
    -- and user_profiles.tenant_id is the authoritative membership row.
    v_caller_uid := auth.uid();
    IF v_caller_uid IS NULL THEN
      RAISE EXCEPTION 'unauthenticated' USING ERRCODE = '42501';
    END IF;
    SELECT EXISTS (
      SELECT 1 FROM public.user_profiles
      WHERE auth_user_id = v_caller_uid
        AND tenant_id = p_tenant_id
    ) INTO v_belongs;
    IF NOT v_belongs THEN
      RAISE EXCEPTION 'cross_tenant_query_denied' USING ERRCODE = '42501';
    END IF;
  END IF;
  -- service_role + any other role (anon shouldn't have EXECUTE)
  -- falls through to the unguarded query — trusted callers.

  RETURN QUERY
  WITH candidates AS (
    SELECT
      tr.id,
      tr.entity_type,
      coalesce(tr.data->>'legal_name', tr.data->>'business_name', tr.data->>'name') AS biz,
      coalesce(tr.data->>'state', tr.data->>'physical_state')                       AS st,
      tr.data->>'ein'   AS ein,
      tr.data->>'email' AS email,
      tr.data->>'phone' AS phone
    FROM public.tenant_records tr
    WHERE tr.tenant_id = p_tenant_id
      AND tr.entity_type IN ('lead', 'application', 'funded_deal')
      AND coalesce(tr.data->>'legal_name', tr.data->>'business_name', tr.data->>'name') IS NOT NULL
  )
  SELECT
    c.id,
    c.entity_type,
    c.biz,
    c.st,
    similarity(lower(c.biz), lower(p_business_name)) AS sim,
    c.ein,
    c.email,
    c.phone
  FROM candidates c
  WHERE
    similarity(lower(c.biz), lower(p_business_name)) >= p_threshold
    AND (p_state IS NULL OR lower(c.st) = lower(p_state))
  ORDER BY sim DESC, length(c.biz)
  LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION public.find_similar_merchants IS
  'pg_trgm-backed merchant matcher. Returns up to p_limit rows from tenant_records (lead/application/funded_deal) whose normalized business name has a trigram similarity >= p_threshold to the search term. Optionally filtered by state. SECURITY DEFINER with a tenant-membership check for authenticated callers — service_role bypasses by design.';
