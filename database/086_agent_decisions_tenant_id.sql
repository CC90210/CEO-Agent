-- 086_agent_decisions_tenant_id.sql
--
-- Same shape as migration 084 (cron_jobs) — add the missing tenant_id
-- column to agent_decisions so the read query can filter by it
-- directly. The dashboard's recentDecisions() helper accepts tenantId
-- today but couldn't act on it because the column didn't exist; it
-- gated on agent_name instead, which is a workable proxy but breaks
-- the moment two tenants share an agent slug.
--
-- All current rows belong to CC's empire (autonomous_agent.py runs
-- exclusively for the empire today). Backfill + lock NOT NULL.

ALTER TABLE public.agent_decisions
  ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);

DO $$
DECLARE
  v_backfilled bigint;
BEGIN
  UPDATE public.agent_decisions
     SET tenant_id = 'ef8d389e-3f15-43f2-ae00-3660f69a1452'::uuid
   WHERE tenant_id IS NULL;
  GET DIAGNOSTICS v_backfilled = ROW_COUNT;
  RAISE NOTICE 'migration 086 backfilled tenant_id on % agent_decisions rows', v_backfilled;
END $$;

ALTER TABLE public.agent_decisions
  ALTER COLUMN tenant_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS agent_decisions_tenant_id_idx
  ON public.agent_decisions (tenant_id, created_at DESC);

COMMENT ON COLUMN public.agent_decisions.tenant_id IS
  'Tenant owner of the agent that recorded this decision. Backfilled in '
  '086 to CC empire. recentDecisions() in lib/queries.ts filters by this.';
