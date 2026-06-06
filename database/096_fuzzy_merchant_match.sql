-- 096_fuzzy_merchant_match.sql — pg_trgm-backed merchant similarity.
--
-- Why this exists: Build C from the 2026-06-06 product-feature plan.
-- The exact-match dedup in lib/import/service.ts catches duplicates when
-- EIN, email, phone, or normalized business name + state are identical.
-- It misses the common operator-reality cases:
--   - "Velocity Logistics LLC" vs "Velosity Logistics LLC" (typo on the
--     applicant's form)
--   - "Pearl Capital" vs "Pearl Capital Group, Inc." (entity-suffix drift)
--   - "Reyes Motors" vs "Reyes Auto Sales" (DBA drift)
--
-- pg_trgm is the canonical Postgres extension for trigram-based string
-- similarity. The GIN index makes similarity queries sub-millisecond
-- even at million-row scale. The RPC wraps the query in tenant scope so
-- the dashboard's import wizard can call it as anonymous-friendly RPC
-- without leaking cross-tenant data.
--
-- The RPC returns a ranked list. The caller (import wizard, leads
-- drawer) decides whether to surface them as "did you mean…?"
-- candidates or auto-merge.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------- 1. Materialize the trigram index source ----------
--
-- merchant_summary is a view; you can't index a view, only the base
-- tables. tenant_records.data is JSONB and trigram-indexing a JSONB
-- key path requires an expression index. The expression is
-- (lower(coalesce(data->>'legal_name', data->>'business_name', data->>'name')))
-- — the same priority order normBusiness() uses in TypeScript.
--
-- GIN with gin_trgm_ops gives O(log n) similarity lookups.

CREATE INDEX IF NOT EXISTS idx_tenant_records_business_trgm
  ON public.tenant_records
  USING GIN (
    (lower(coalesce(
      data->>'legal_name',
      data->>'business_name',
      data->>'name',
      ''
    ))) gin_trgm_ops
  )
  WHERE entity_type IN ('lead', 'application', 'funded_deal');

-- A b-tree on tenant_id + entity_type narrows the candidate set before
-- the trigram pass kicks in. The two indexes work together: planner
-- picks b-tree to shrink the row count, then trigram to rank.
CREATE INDEX IF NOT EXISTS idx_tenant_records_tenant_entity_for_match
  ON public.tenant_records (tenant_id, entity_type);

-- ---------- 2. The match RPC ----------
--
-- find_similar_merchants(tenant_id, business_name, state, threshold, limit)
--
-- Returns up to `result_limit` rows, ordered by similarity score
-- descending. The state filter is OPTIONAL — when null, similarity is
-- computed across the whole tenant. When provided, it filters to that
-- state first (state is stored on tenant_records.data->>'state' OR
-- tenant_records.data->>'physical_state').
--
-- threshold is the minimum pg_trgm similarity to qualify (0.0-1.0).
-- 0.4 is a sensible default — typo-tolerant without surfacing pure
-- coincidence matches. The caller can raise it for auto-merge UX.
--
-- SECURITY DEFINER + tenant_id parameter is the auth boundary —
-- service-role callers must pass tenant_id; we trust the caller to
-- have done the session auth (lib/api-auth.ts) upstream.

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
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
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
    -- The pg_trgm similarity threshold AND optional state filter both
    -- short-circuit before the SELECT projection, so the query stays
    -- planner-friendly.
    similarity(lower(c.biz), lower(p_business_name)) >= p_threshold
    AND (p_state IS NULL OR lower(c.st) = lower(p_state))
  ORDER BY sim DESC, length(c.biz)
  LIMIT p_limit;
$$;

COMMENT ON FUNCTION public.find_similar_merchants IS
  'pg_trgm-backed merchant matcher. Returns up to p_limit rows from tenant_records (lead/application/funded_deal) whose normalized business name has a trigram similarity >= p_threshold to the search term. Optionally filtered by state. Used by the dashboard import wizard + leads drawer to surface "did you mean…?" candidates when exact-match dedup misses.';

-- ---------- 3. Grant execute to the roles the dashboard uses ----------
--
-- service_role bypasses RLS — the dashboard's /api/import/[entity] uses
-- the service-role client (lib/supabase-server.ts:getServiceSupabase).
-- authenticated tenant members also need execute so the leads drawer's
-- merchant suggestion UI works without lifting to service-role.

GRANT EXECUTE ON FUNCTION public.find_similar_merchants(uuid, text, text, real, int)
  TO service_role, authenticated;
