-- 095_daily_plan_items.sql
-- ============================================================================
-- Blocker 2 (VPS finalization 2026-06-06): make daily_plan_items upserts work.
--
-- ADAPTATION NOTE: the original plan was to CREATE the daily_plan_items table,
-- but it ALREADY EXISTS — sunbiz-agent migration 069_sunbiz_meeting2_expansion
-- created it with the correct columns (tenant_id, plan_date, lead_id,
-- application_id, category, priority, reason, metadata, status, ...). What 069
-- did NOT add is a UNIQUE index on the generator's conflict target. The
-- daily_plan_generator upserts with:
--     ON CONFLICT (tenant_id, plan_date, lead_id, category)
-- and Postgres can only infer that from a UNIQUE index on EXACTLY those four
-- columns. Without it every upsert fails 42P10 ("no unique or exclusion
-- constraint matching the ON CONFLICT specification") and the Daily Plan /
-- Calls tab stays empty (observed: 2,484+ consecutive failures).
--
-- So this migration is additive + idempotent: it creates ONLY the missing
-- unique index. No CREATE TABLE, no column changes, no data mutation — safe to
-- run against the live table. (Cross-repo note: depends on sunbiz 069 having
-- already created the table, which it has.)
--
-- lead_id is nullable, but the generator always supplies a non-null lead_id
-- (lead UUID, or the lender-thread id for new_offer), so NULLS DISTINCT default
-- behaviour is fine — there is nothing to collapse.
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS daily_plan_items_tenant_date_lead_category_uniq
    ON public.daily_plan_items (tenant_id, plan_date, lead_id, category);
