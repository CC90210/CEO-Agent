-- ============================================================================
-- Migration 070 — RLS policies for migration 069 tables
--
-- Codex adversarial review (2026-05-25) flagged migration 069 as
-- creating 14 tenant-scoped tables without RLS, leaving tenant_id as
-- application-convention only. A misconfigured client-side anon-key
-- access path could leak / mutate follow-ups, cold outreach recipients,
-- lender feedback, agent memory notes, etc. across tenants.
--
-- This migration:
--   1. Enables RLS on all 14 tables created by 069
--   2. Adds canonical service-role bypass + authenticated tenant-scope
--      policies matching the empire's existing RLS pattern (see
--      migration 044 / 054 for the reference shape)
--   3. Special-cases known_funding_companies as an empire-wide read-
--      only registry (no per-tenant scope; all authenticated users may
--      read, only service_role may write)
--
-- Idempotent — every DROP POLICY IF EXISTS / CREATE POLICY pair can
-- re-run cleanly on a previously-applied DB.
--
-- NOTE: application_lender_threads (also touched by 069) already has
-- RLS from migration 044 — no changes needed for that table.
--
-- Apply: python scripts/apply_migration.py database/070_sunbiz_meeting2_rls.sql --project bravo
-- Verify: python scripts/audit_rls_coverage.py --project bravo
--   OR:
--   SELECT tablename, rowsecurity FROM pg_tables
--     WHERE schemaname = 'public'
--       AND tablename IN (
--         'application_underwriting', 'follow_up_tasks', 'daily_plan_items',
--         'cold_lead_lists', 'cold_leads',
--         'cold_outreach_campaigns', 'cold_outreach_recipients',
--         'shop_out_warnings', 'known_funding_companies',
--         'offer_sources', 'email_thread_monitors',
--         'lender_feedback', 'personalized_form_links', 'agent_memory_notes'
--       );
--   -- expect rowsecurity = true on all 14
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. application_underwriting
-- ============================================================================
ALTER TABLE public.application_underwriting ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "application_underwriting_service_role_all" ON public.application_underwriting;
CREATE POLICY "application_underwriting_service_role_all" ON public.application_underwriting
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "application_underwriting_tenant_read" ON public.application_underwriting;
CREATE POLICY "application_underwriting_tenant_read" ON public.application_underwriting
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "application_underwriting_tenant_write" ON public.application_underwriting;
CREATE POLICY "application_underwriting_tenant_write" ON public.application_underwriting
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "application_underwriting_tenant_update" ON public.application_underwriting;
CREATE POLICY "application_underwriting_tenant_update" ON public.application_underwriting
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "application_underwriting_tenant_delete" ON public.application_underwriting;
CREATE POLICY "application_underwriting_tenant_delete" ON public.application_underwriting
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 2. follow_up_tasks
-- ============================================================================
ALTER TABLE public.follow_up_tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "follow_up_tasks_service_role_all" ON public.follow_up_tasks;
CREATE POLICY "follow_up_tasks_service_role_all" ON public.follow_up_tasks
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "follow_up_tasks_tenant_read" ON public.follow_up_tasks;
CREATE POLICY "follow_up_tasks_tenant_read" ON public.follow_up_tasks
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "follow_up_tasks_tenant_write" ON public.follow_up_tasks;
CREATE POLICY "follow_up_tasks_tenant_write" ON public.follow_up_tasks
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "follow_up_tasks_tenant_update" ON public.follow_up_tasks;
CREATE POLICY "follow_up_tasks_tenant_update" ON public.follow_up_tasks
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "follow_up_tasks_tenant_delete" ON public.follow_up_tasks;
CREATE POLICY "follow_up_tasks_tenant_delete" ON public.follow_up_tasks
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 3. daily_plan_items
-- ============================================================================
ALTER TABLE public.daily_plan_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "daily_plan_items_service_role_all" ON public.daily_plan_items;
CREATE POLICY "daily_plan_items_service_role_all" ON public.daily_plan_items
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "daily_plan_items_tenant_read" ON public.daily_plan_items;
CREATE POLICY "daily_plan_items_tenant_read" ON public.daily_plan_items
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "daily_plan_items_tenant_write" ON public.daily_plan_items;
CREATE POLICY "daily_plan_items_tenant_write" ON public.daily_plan_items
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "daily_plan_items_tenant_update" ON public.daily_plan_items;
CREATE POLICY "daily_plan_items_tenant_update" ON public.daily_plan_items
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "daily_plan_items_tenant_delete" ON public.daily_plan_items;
CREATE POLICY "daily_plan_items_tenant_delete" ON public.daily_plan_items
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 4. cold_lead_lists
-- ============================================================================
ALTER TABLE public.cold_lead_lists ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cold_lead_lists_service_role_all" ON public.cold_lead_lists;
CREATE POLICY "cold_lead_lists_service_role_all" ON public.cold_lead_lists
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "cold_lead_lists_tenant_read" ON public.cold_lead_lists;
CREATE POLICY "cold_lead_lists_tenant_read" ON public.cold_lead_lists
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_lead_lists_tenant_write" ON public.cold_lead_lists;
CREATE POLICY "cold_lead_lists_tenant_write" ON public.cold_lead_lists
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_lead_lists_tenant_update" ON public.cold_lead_lists;
CREATE POLICY "cold_lead_lists_tenant_update" ON public.cold_lead_lists
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_lead_lists_tenant_delete" ON public.cold_lead_lists;
CREATE POLICY "cold_lead_lists_tenant_delete" ON public.cold_lead_lists
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 5. cold_leads
-- ============================================================================
ALTER TABLE public.cold_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cold_leads_service_role_all" ON public.cold_leads;
CREATE POLICY "cold_leads_service_role_all" ON public.cold_leads
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "cold_leads_tenant_read" ON public.cold_leads;
CREATE POLICY "cold_leads_tenant_read" ON public.cold_leads
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_leads_tenant_write" ON public.cold_leads;
CREATE POLICY "cold_leads_tenant_write" ON public.cold_leads
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_leads_tenant_update" ON public.cold_leads;
CREATE POLICY "cold_leads_tenant_update" ON public.cold_leads
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_leads_tenant_delete" ON public.cold_leads;
CREATE POLICY "cold_leads_tenant_delete" ON public.cold_leads
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 6. cold_outreach_campaigns
-- ============================================================================
ALTER TABLE public.cold_outreach_campaigns ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cold_outreach_campaigns_service_role_all" ON public.cold_outreach_campaigns;
CREATE POLICY "cold_outreach_campaigns_service_role_all" ON public.cold_outreach_campaigns
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "cold_outreach_campaigns_tenant_read" ON public.cold_outreach_campaigns;
CREATE POLICY "cold_outreach_campaigns_tenant_read" ON public.cold_outreach_campaigns
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_outreach_campaigns_tenant_write" ON public.cold_outreach_campaigns;
CREATE POLICY "cold_outreach_campaigns_tenant_write" ON public.cold_outreach_campaigns
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_outreach_campaigns_tenant_update" ON public.cold_outreach_campaigns;
CREATE POLICY "cold_outreach_campaigns_tenant_update" ON public.cold_outreach_campaigns
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_outreach_campaigns_tenant_delete" ON public.cold_outreach_campaigns;
CREATE POLICY "cold_outreach_campaigns_tenant_delete" ON public.cold_outreach_campaigns
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 7. cold_outreach_recipients
-- ============================================================================
ALTER TABLE public.cold_outreach_recipients ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cold_outreach_recipients_service_role_all" ON public.cold_outreach_recipients;
CREATE POLICY "cold_outreach_recipients_service_role_all" ON public.cold_outreach_recipients
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "cold_outreach_recipients_tenant_read" ON public.cold_outreach_recipients;
CREATE POLICY "cold_outreach_recipients_tenant_read" ON public.cold_outreach_recipients
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_outreach_recipients_tenant_write" ON public.cold_outreach_recipients;
CREATE POLICY "cold_outreach_recipients_tenant_write" ON public.cold_outreach_recipients
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_outreach_recipients_tenant_update" ON public.cold_outreach_recipients;
CREATE POLICY "cold_outreach_recipients_tenant_update" ON public.cold_outreach_recipients
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "cold_outreach_recipients_tenant_delete" ON public.cold_outreach_recipients;
CREATE POLICY "cold_outreach_recipients_tenant_delete" ON public.cold_outreach_recipients
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 8. shop_out_warnings
-- ============================================================================
ALTER TABLE public.shop_out_warnings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "shop_out_warnings_service_role_all" ON public.shop_out_warnings;
CREATE POLICY "shop_out_warnings_service_role_all" ON public.shop_out_warnings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "shop_out_warnings_tenant_read" ON public.shop_out_warnings;
CREATE POLICY "shop_out_warnings_tenant_read" ON public.shop_out_warnings
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "shop_out_warnings_tenant_write" ON public.shop_out_warnings;
CREATE POLICY "shop_out_warnings_tenant_write" ON public.shop_out_warnings
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "shop_out_warnings_tenant_update" ON public.shop_out_warnings;
CREATE POLICY "shop_out_warnings_tenant_update" ON public.shop_out_warnings
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "shop_out_warnings_tenant_delete" ON public.shop_out_warnings;
CREATE POLICY "shop_out_warnings_tenant_delete" ON public.shop_out_warnings
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 9. known_funding_companies — SPECIAL CASE: empire-wide reference table
--
-- No tenant_id column — this is a shared MCA registry used by the
-- underwriting agent across all tenants. All authenticated users may
-- read it; only service_role may write (admin-managed registry, no
-- operator-side mutation path).
-- ============================================================================
ALTER TABLE public.known_funding_companies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "known_funding_companies_service_role_all" ON public.known_funding_companies;
CREATE POLICY "known_funding_companies_service_role_all" ON public.known_funding_companies
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "known_funding_companies_authenticated_read" ON public.known_funding_companies;
CREATE POLICY "known_funding_companies_authenticated_read" ON public.known_funding_companies
    FOR SELECT TO authenticated USING (true);

-- ============================================================================
-- 10. offer_sources
-- ============================================================================
ALTER TABLE public.offer_sources ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "offer_sources_service_role_all" ON public.offer_sources;
CREATE POLICY "offer_sources_service_role_all" ON public.offer_sources
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "offer_sources_tenant_read" ON public.offer_sources;
CREATE POLICY "offer_sources_tenant_read" ON public.offer_sources
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "offer_sources_tenant_write" ON public.offer_sources;
CREATE POLICY "offer_sources_tenant_write" ON public.offer_sources
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "offer_sources_tenant_update" ON public.offer_sources;
CREATE POLICY "offer_sources_tenant_update" ON public.offer_sources
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "offer_sources_tenant_delete" ON public.offer_sources;
CREATE POLICY "offer_sources_tenant_delete" ON public.offer_sources
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 11. email_thread_monitors
-- ============================================================================
ALTER TABLE public.email_thread_monitors ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "email_thread_monitors_service_role_all" ON public.email_thread_monitors;
CREATE POLICY "email_thread_monitors_service_role_all" ON public.email_thread_monitors
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "email_thread_monitors_tenant_read" ON public.email_thread_monitors;
CREATE POLICY "email_thread_monitors_tenant_read" ON public.email_thread_monitors
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "email_thread_monitors_tenant_write" ON public.email_thread_monitors;
CREATE POLICY "email_thread_monitors_tenant_write" ON public.email_thread_monitors
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "email_thread_monitors_tenant_update" ON public.email_thread_monitors;
CREATE POLICY "email_thread_monitors_tenant_update" ON public.email_thread_monitors
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "email_thread_monitors_tenant_delete" ON public.email_thread_monitors;
CREATE POLICY "email_thread_monitors_tenant_delete" ON public.email_thread_monitors
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 12. lender_feedback
-- ============================================================================
ALTER TABLE public.lender_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lender_feedback_service_role_all" ON public.lender_feedback;
CREATE POLICY "lender_feedback_service_role_all" ON public.lender_feedback
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "lender_feedback_tenant_read" ON public.lender_feedback;
CREATE POLICY "lender_feedback_tenant_read" ON public.lender_feedback
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "lender_feedback_tenant_write" ON public.lender_feedback;
CREATE POLICY "lender_feedback_tenant_write" ON public.lender_feedback
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "lender_feedback_tenant_update" ON public.lender_feedback;
CREATE POLICY "lender_feedback_tenant_update" ON public.lender_feedback
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "lender_feedback_tenant_delete" ON public.lender_feedback;
CREATE POLICY "lender_feedback_tenant_delete" ON public.lender_feedback
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 13. personalized_form_links
-- ============================================================================
ALTER TABLE public.personalized_form_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "personalized_form_links_service_role_all" ON public.personalized_form_links;
CREATE POLICY "personalized_form_links_service_role_all" ON public.personalized_form_links
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "personalized_form_links_tenant_read" ON public.personalized_form_links;
CREATE POLICY "personalized_form_links_tenant_read" ON public.personalized_form_links
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "personalized_form_links_tenant_write" ON public.personalized_form_links;
CREATE POLICY "personalized_form_links_tenant_write" ON public.personalized_form_links
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "personalized_form_links_tenant_update" ON public.personalized_form_links;
CREATE POLICY "personalized_form_links_tenant_update" ON public.personalized_form_links
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "personalized_form_links_tenant_delete" ON public.personalized_form_links;
CREATE POLICY "personalized_form_links_tenant_delete" ON public.personalized_form_links
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 14. agent_memory_notes
-- ============================================================================
ALTER TABLE public.agent_memory_notes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent_memory_notes_service_role_all" ON public.agent_memory_notes;
CREATE POLICY "agent_memory_notes_service_role_all" ON public.agent_memory_notes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "agent_memory_notes_tenant_read" ON public.agent_memory_notes;
CREATE POLICY "agent_memory_notes_tenant_read" ON public.agent_memory_notes
    FOR SELECT TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "agent_memory_notes_tenant_write" ON public.agent_memory_notes;
CREATE POLICY "agent_memory_notes_tenant_write" ON public.agent_memory_notes
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "agent_memory_notes_tenant_update" ON public.agent_memory_notes;
CREATE POLICY "agent_memory_notes_tenant_update" ON public.agent_memory_notes
    FOR UPDATE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    )
    WITH CHECK (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "agent_memory_notes_tenant_delete" ON public.agent_memory_notes;
CREATE POLICY "agent_memory_notes_tenant_delete" ON public.agent_memory_notes
    FOR DELETE TO authenticated
    USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT tablename, rowsecurity FROM pg_tables
--     WHERE schemaname = 'public'
--       AND tablename IN (
--         'application_underwriting', 'follow_up_tasks', 'daily_plan_items',
--         'cold_lead_lists', 'cold_leads',
--         'cold_outreach_campaigns', 'cold_outreach_recipients',
--         'shop_out_warnings', 'known_funding_companies',
--         'offer_sources', 'email_thread_monitors',
--         'lender_feedback', 'personalized_form_links', 'agent_memory_notes'
--       );
--   -- expect rowsecurity = true on all 14
--
--   SELECT tablename, policyname, cmd, roles
--     FROM pg_policies
--    WHERE schemaname = 'public'
--      AND tablename IN (
--         'application_underwriting', 'follow_up_tasks', 'daily_plan_items',
--         'cold_lead_lists', 'cold_leads',
--         'cold_outreach_campaigns', 'cold_outreach_recipients',
--         'shop_out_warnings', 'known_funding_companies',
--         'offer_sources', 'email_thread_monitors',
--         'lender_feedback', 'personalized_form_links', 'agent_memory_notes'
--      )
--    ORDER BY tablename, policyname;
--   -- expect 5 policies per tenant-scoped table (service_role_all, tenant_read,
--   --   tenant_write, tenant_update, tenant_delete)
--   -- expect 2 policies for known_funding_companies (service_role_all,
--   --   authenticated_read)
-- ============================================================================
