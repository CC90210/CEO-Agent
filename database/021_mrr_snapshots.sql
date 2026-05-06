-- Migration 021 — Real daily MRR history
--
-- Replaces the synthetic mrrHistory() output on the Today page with persisted
-- daily snapshots. The "MRR added (7d)" tile becomes a real number.
--
-- Tenant-scoped, one row per (tenant_id, snapshot_date). Idempotent upsert
-- via unique constraint, so the nightly cron can run multiple times without
-- creating duplicates.
--
-- Apply with: python scripts/apply_migration.py database/021_mrr_snapshots.sql

BEGIN;

CREATE TABLE IF NOT EXISTS public.mrr_snapshots (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    snapshot_date   date NOT NULL,
    mrr_usd         numeric(12,2) NOT NULL DEFAULT 0,
    target_usd      numeric(12,2),
    source          text NOT NULL DEFAULT 'profile',  -- 'profile' | 'stripe' | 'manual'
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_mrr_snapshots_tenant_date
    ON public.mrr_snapshots (tenant_id, snapshot_date DESC);

ALTER TABLE public.mrr_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY mrr_snap_tenant_select ON public.mrr_snapshots
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY mrr_snap_tenant_write ON public.mrr_snapshots
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMIT;
