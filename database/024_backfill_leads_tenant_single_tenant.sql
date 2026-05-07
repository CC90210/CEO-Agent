-- 024_backfill_leads_tenant_single_tenant.sql
--
-- The 023 backfill couldn't fill lead_interactions.tenant_id when the parent
-- leads row also had tenant_id=NULL. Some leads (Current Plumbing, etc.)
-- were inserted by code paths that pre-date migration 018. This migration
-- backfills BOTH leads + lead_interactions, but only when the database
-- has a single non-null tenant — i.e. single-operator deployment. Multi-
-- tenant servers stay safe (this migration is a no-op there).
--
-- Apply with: python scripts/apply_migration.py database/024_backfill_leads_tenant_single_tenant.sql

BEGIN;

DO $$
DECLARE
    v_tenant_count int;
    v_only_tenant uuid;
BEGIN
    SELECT COUNT(DISTINCT tenant_id)
    INTO v_tenant_count
    FROM public.user_profiles
    WHERE tenant_id IS NOT NULL;

    SELECT tenant_id INTO v_only_tenant
    FROM public.user_profiles
    WHERE tenant_id IS NOT NULL
    LIMIT 1;

    IF v_tenant_count = 1 AND v_only_tenant IS NOT NULL THEN
        RAISE NOTICE 'Single-tenant backfill: assigning tenant % to all NULL rows', v_only_tenant;

        UPDATE public.leads
        SET tenant_id = v_only_tenant
        WHERE tenant_id IS NULL;

        UPDATE public.lead_interactions
        SET tenant_id = v_only_tenant
        WHERE tenant_id IS NULL;
    ELSE
        RAISE NOTICE 'Multi-tenant detected (%) — skipping single-tenant backfill', v_tenant_count;
    END IF;
END $$;

COMMIT;
