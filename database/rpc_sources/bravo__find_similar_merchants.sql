CREATE OR REPLACE FUNCTION public.find_similar_merchants(p_tenant_id uuid, p_business_name text, p_state text DEFAULT NULL::text, p_threshold real DEFAULT 0.4, p_limit integer DEFAULT 10)
 RETURNS TABLE(record_id uuid, entity_type text, business_name text, state text, similarity real, ein text, email text, phone text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
$function$
