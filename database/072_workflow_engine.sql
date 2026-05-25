-- ============================================================================
-- Migration 072 — Workflow Engine (V6.9.2 substrate)
--
-- Pattern import from twentyhq/twenty (AGPLv3 — patterns only). Adds the
-- typed workflow engine the dashboard's Automations tab was a skeleton
-- for. Workflows are JSONB definitions of (trigger + ordered steps);
-- workflow_runs are per-fire instances; workflow_run_steps are the
-- per-step audit trail with input/output for debugging.
--
-- DEPENDS ON: migrations 038 (tenants) + 070 (object_metadata).
--
-- Substrate scope (V6.9.2):
--   - Schema for workflow + run + run_step
--   - manual trigger only (operator-clicked)
--   - record-mutation / cron / webhook triggers ship in V6.9.2.1+ (need
--     event-bus wiring + cron registration which are operational changes)
--
-- Engine model (matches Step Registry in lib/workflow-steps/):
--   workflows.definition JSONB shape (validated by run-step dispatcher):
--   {
--     "trigger": { "type": "manual" | "record_mutation" | "cron" | "webhook", ... },
--     "steps": [ { "id": "step1", "type": "record-crud", "input": {...} }, ... ]
--   }
--
-- Apply: python scripts/apply_migration.py database/072_workflow_engine.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. workflow_run_status enum
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workflow_run_status') THEN
        CREATE TYPE public.workflow_run_status AS ENUM (
            'pending',    -- queued; daemon hasn't picked up yet
            'running',    -- daemon claimed; steps in flight
            'complete',   -- all steps ran successfully
            'failed',     -- a step errored or the per-run step cap was hit
            'cancelled'   -- operator cancelled mid-run
        );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. workflows — definitions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workflows (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    slug            text NOT NULL,
    name            text NOT NULL,
    description     text,
    /* trigger JSONB shape: { type: 'manual'|'record_mutation'|'cron'|'webhook', ...op-specific }
       Validation is in the API; no CHECK constraint so the trigger types can
       evolve without re-migration. */
    trigger         jsonb NOT NULL DEFAULT '{"type":"manual"}'::jsonb,
    /* definition JSONB shape: { steps: [ { id, type, input, on_error? }, ... ] }
       Step types are looked up in lib/workflow-steps/run-step.ts dispatcher
       at runtime; unknown types fail the run with a clear error. */
    definition      jsonb NOT NULL DEFAULT '{"steps":[]}'::jsonb,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_workflows_tenant
    ON public.workflows (tenant_id)
    WHERE is_active = true;

ALTER TABLE public.workflows ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.workflows IS
    '072 V6.9.2 — operator-defined workflow definitions. trigger + definition (steps array) JSONB validated by the run-step dispatcher.';

-- ---------------------------------------------------------------------------
-- 3. workflow_runs — per-fire instances
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workflow_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     uuid NOT NULL REFERENCES public.workflows(id) ON DELETE CASCADE,
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    /* What fired this run: { type, source: 'manual'|'event'|'cron'|'webhook', user_id?, event_id?, ... } */
    trigger_event   jsonb NOT NULL DEFAULT '{}'::jsonb,
    status          public.workflow_run_status NOT NULL DEFAULT 'pending',
    started_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    error           text,
    /* Daemon pick-up state for FOR UPDATE SKIP LOCKED pattern */
    claimed_by      text,
    claimed_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_tenant_workflow
    ON public.workflow_runs (tenant_id, workflow_id, started_at DESC);

-- Hot path: daemon claims pending runs with this index
CREATE INDEX IF NOT EXISTS idx_workflow_runs_pending
    ON public.workflow_runs (status, created_at)
    WHERE status = 'pending';

ALTER TABLE public.workflow_runs ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 4. workflow_run_steps — per-step audit trail
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workflow_run_steps (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL REFERENCES public.workflow_runs(id) ON DELETE CASCADE,
    step_index      int NOT NULL,
    step_type       text NOT NULL,
    step_id         text,                                -- operator-facing id from definition.steps[].id
    input           jsonb,
    output          jsonb,
    status          public.workflow_run_status NOT NULL DEFAULT 'pending',
    started_at      timestamptz,
    completed_at    timestamptz,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run
    ON public.workflow_run_steps (run_id, step_index);

ALTER TABLE public.workflow_run_steps ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 5. RLS — tenant-scoped (matches 038/070/071 pattern)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workflows' AND policyname='workflows_member_all') THEN
        CREATE POLICY workflows_member_all ON public.workflows
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workflow_runs' AND policyname='workflow_runs_member_all') THEN
        CREATE POLICY workflow_runs_member_all ON public.workflow_runs
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workflow_run_steps' AND policyname='workflow_run_steps_member_all') THEN
        CREATE POLICY workflow_run_steps_member_all ON public.workflow_run_steps
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM public.workflow_runs r WHERE r.id = workflow_run_steps.run_id AND r.tenant_id = public.current_tenant_id()))
            WITH CHECK (EXISTS (SELECT 1 FROM public.workflow_runs r WHERE r.id = workflow_run_steps.run_id AND r.tenant_id = public.current_tenant_id()));
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 6. updated_at trigger on workflows
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.workflows_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workflows_set_updated_at ON public.workflows;
CREATE TRIGGER workflows_set_updated_at
    BEFORE UPDATE ON public.workflows
    FOR EACH ROW EXECUTE FUNCTION public.workflows_touch_updated_at();

COMMIT;
