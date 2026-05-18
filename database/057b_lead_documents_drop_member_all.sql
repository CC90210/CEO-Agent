-- 057b_lead_documents_drop_member_all.sql
-- ---------------------------------------------------------------------------
-- MANUAL — apply via Supabase Dashboard SQL editor. apply_migration.py
-- refuses DROP POLICY by safety policy.
--
-- Companion to 057_lead_documents_storage_path_check.sql. The CHECK
-- constraint in that migration already makes cross-tenant storage_path
-- insertion impossible at the DB layer; this file just narrows the
-- over-permissive FOR ALL policy down to SELECT-only for authenticated
-- tenant members. Server-side writes still work because the public
-- form submit route uses the service-role client, which bypasses RLS.
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS lead_documents_member_all ON public.lead_documents;

CREATE POLICY lead_documents_member_select ON public.lead_documents
    FOR SELECT TO authenticated
    USING (tenant_id = public.current_tenant_id());
