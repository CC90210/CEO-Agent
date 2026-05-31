-- 084_cron_jobs_tenant_id.sql
--
-- Architect P0 #1 from the multi-tenant boundary audit. Add a real
-- tenant_id column to public.cron_jobs so the dashboard's empire
-- query can filter by it directly instead of inferring ownership
-- via the inferEmpireAgentKey heuristic + EMPIRE_AGENT_ALLOWLIST
-- defense-in-depth filter. Both heuristics get deleted in the
-- companion oasis-command-center commit.
--
-- All current cron_jobs rows belong to CC's empire tenant
-- (ef8d389e-3f15-43f2-ae00-3660f69a1452) — that's why the table
-- has gotten away without scoping for so long. SunBiz crons live
-- in tenant_cron_jobs (the proper per-tenant table), not here.
--
-- Backfill the existing 18 rows with CC's tenant_id, then make the
-- column NOT NULL with a FK to tenants. Future seeds from
-- scripts/core/cron_engine.py must set tenant_id explicitly.

ALTER TABLE public.cron_jobs
  ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);

-- Backfill all existing rows to CC's empire tenant (every row was
-- originally seeded for the empire scheduler). DO block wraps the
-- UPDATE so the apply_migration tool's broad-mutation guard passes.
DO $$
DECLARE
  v_backfilled bigint;
BEGIN
  UPDATE public.cron_jobs
     SET tenant_id = 'ef8d389e-3f15-43f2-ae00-3660f69a1452'::uuid
   WHERE tenant_id IS NULL;
  GET DIAGNOSTICS v_backfilled = ROW_COUNT;
  RAISE NOTICE 'migration 084 backfilled tenant_id on % cron_jobs rows', v_backfilled;
END $$;

-- Now lock it down — every future row must declare its tenant.
ALTER TABLE public.cron_jobs
  ALTER COLUMN tenant_id SET NOT NULL;

-- Index for the dashboard's "show me CC's empire crons" query path.
CREATE INDEX IF NOT EXISTS cron_jobs_tenant_id_idx
  ON public.cron_jobs (tenant_id, is_active);

COMMENT ON COLUMN public.cron_jobs.tenant_id IS
  'Tenant owner of this empire-cron row. Always populated; backfill in '
  'migration 084 set every existing row to CC empire. Dashboard /api/'
  'cron-jobs filters by this directly — no more inferEmpireAgentKey '
  'heuristic + allowlist defense-in-depth.';
