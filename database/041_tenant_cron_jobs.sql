-- Migration 041 — Tenant-scoped cron jobs managed from the dashboard
--
-- Phase I of giggly-reef harness completeness. Operators can now create
-- and manage cron jobs from the dashboard /automations page; the bridge
-- daemon polls this table every minute and materializes matching rows
-- into its local cron_engine.py SEED_JOBS so the actual cron tick still
-- runs on the operator's machine (where the tools, credentials, and
-- subprocess capabilities live).
--
-- Architecture (CC selected 2026-05-15):
--   Dashboard CRUD  →  tenant_cron_jobs  ←  bridge poll loop (60s)
--                            ↑
--                            tenant_id scoped, RLS enforced
--
-- Why a table on Supabase instead of bridge-local config:
--   - Survives operator machine reboots (cron jobs are durable; bridge
--     state isn't).
--   - Multi-tenant ready: each tenant owns their cron list independent
--     of which machine the bridge runs on.
--   - Editable from anywhere the operator can reach the dashboard.
--   - History/audit comes from the standard Supabase tooling.
--
-- Apply via: python scripts/apply_migration.py database/041_tenant_cron_jobs.sql

BEGIN;

-- ============================================================================
-- tenant_cron_jobs — the operator's scheduled automations
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tenant_cron_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- Agent that "owns" this job. Used for display grouping AND for the
    -- bridge to know which agent's repo to cwd into when executing.
    -- Falls back to "bravo" when missing (single-agent setups).
    agent_key       text NOT NULL DEFAULT 'bravo',
    -- Operator-given name. Free text, max ~80 chars enforced at app layer.
    name            text NOT NULL,
    -- Optional one-liner of what this job does. Surfaced in the UI list.
    description     text,
    -- Standard cron expression (5-field: minute hour day month dow).
    -- Validated at app layer via a parser; this column just stores it.
    schedule        text NOT NULL,
    -- What runs on each tick. Discriminated union by `action_type`:
    --   action_type="script_run"
    --     action_payload = { "script": "snapshots/leads_snapshot.py",
    --                        "args": ["--json"] }
    --   action_type="snapshot_run"
    --     action_payload = { "snapshot": "leads_snapshot.py" }
    --     (same as script_run with a fixed scripts/snapshots/ prefix)
    --   action_type="agent_prompt"
    --     action_payload = { "prompt": "Run the daily briefing" }
    --     (spawns a chat turn against the agent_key with this prompt)
    --   action_type="webhook_post"
    --     action_payload = { "url": "https://...", "body": {...} }
    --     (lightweight HTTP POST — used for n8n triggers etc.)
    action_type     text NOT NULL,
    action_payload  jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Toggle without delete. Bridge polls only enabled rows.
    enabled         boolean NOT NULL DEFAULT true,
    -- Run-tracking — bumped by the bridge after each successful execution.
    -- Read by the dashboard for "last fired" / "next due" UX.
    last_run_at     timestamptz,
    last_run_status text CHECK (last_run_status IN ('success', 'error', NULL) OR last_run_status IS NULL),
    last_run_output text,
    last_run_error  text,
    run_count       integer NOT NULL DEFAULT 0,
    -- Who created it (for audit). NULL for system-seeded rows.
    created_by      uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_cron_jobs_tenant_enabled
    ON public.tenant_cron_jobs (tenant_id, enabled)
    WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_tenant_cron_jobs_agent
    ON public.tenant_cron_jobs (tenant_id, agent_key);

CREATE TRIGGER trg_tenant_cron_jobs_updated_at
    BEFORE UPDATE ON public.tenant_cron_jobs
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

ALTER TABLE public.tenant_cron_jobs ENABLE ROW LEVEL SECURITY;

-- Operators see + edit only their own tenant's cron jobs. Same pattern
-- chat_sessions / chat_messages uses.
CREATE POLICY tcj_tenant_select ON public.tenant_cron_jobs
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY tcj_tenant_write ON public.tenant_cron_jobs
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMENT ON TABLE public.tenant_cron_jobs IS
  'Operator-defined scheduled automations. Dashboard CRUDs via '
  '/api/cron-jobs; bridge daemon polls every 60s via /api/cron-jobs/poll '
  'and materializes into local cron_engine.py SEED_JOBS for execution.';

COMMIT;
