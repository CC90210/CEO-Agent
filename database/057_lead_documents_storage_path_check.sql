-- 057_lead_documents_storage_path_check.sql
-- ---------------------------------------------------------------------------
-- Defense-in-depth CHECK constraint on lead_documents.storage_path —
-- root-cause fix for the confused-deputy finding Codex surfaced
-- 2026-05-18.
--
-- The existing FOR ALL RLS policy (migration 049, line 208) lets
-- authenticated tenant members INSERT/UPDATE lead_documents rows
-- including the storage_path column. A malicious employee could
-- craft a row pointing at a foreign tenant's storage path; the
-- service-role signed-URL minter at /api/lead-documents/[id] would
-- then sign it. The app-level fix in commit 74db28b added a
-- defense-in-depth prefix check in the minter — this constraint
-- closes the door at the DB layer so no row can EXIST with a
-- misanchored storage_path, regardless of which code path inserted it.
--
-- Companion file (manual): database/057b_lead_documents_drop_member_all.sql
-- contains the DROP POLICY + CREATE SELECT-only policy. apply_migration.py
-- refuses DROP POLICY by design — run that one via the Supabase
-- Dashboard SQL editor. This CHECK constraint stands alone as the
-- security boundary; the policy tightening is operator-experience polish.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'lead_documents'
          AND constraint_name = 'lead_documents_storage_path_tenant_prefix'
    ) THEN
        ALTER TABLE public.lead_documents
            ADD CONSTRAINT lead_documents_storage_path_tenant_prefix
            CHECK (storage_path LIKE tenant_id::text || '/%');
    END IF;
END $$;
