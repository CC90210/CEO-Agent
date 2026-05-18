-- 055_lead_documents_storage.sql
-- ---------------------------------------------------------------------------
-- Storage bucket for prospect-uploaded documents (Phase 21 of the SunBiz CRM
-- reconstructor). Migration 049 introduced the `lead_documents` metadata
-- table; this migration creates the bucket the storage_path column points at
-- and gates reads through tenant_id-scoped policies.
--
-- The submit-side route (apps/command-center/app/api/forms/submit/route.ts)
-- uses the service-role client so it bypasses storage RLS for writes — the
-- HMAC-signed form-link is the auth boundary on that path. Operator reads
-- go through a signed-URL API that performs its own tenant check before
-- minting; the policies below are belt-and-braces for direct anon access.
-- ---------------------------------------------------------------------------

INSERT INTO storage.buckets (id, name, public)
VALUES ('lead-documents', 'lead-documents', false)
ON CONFLICT (id) DO NOTHING;

-- Tenant-scoped read. The first path segment of every uploaded file is the
-- tenant_id so we can scope without joining lead_documents on every read.
-- Storage path convention: <tenant_id>/<lead_id>/<filename>.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='storage' AND tablename='objects'
          AND policyname='lead_documents_tenant_read'
    ) THEN
        CREATE POLICY lead_documents_tenant_read ON storage.objects
        FOR SELECT TO authenticated
        USING (
            bucket_id = 'lead-documents'
            AND (storage.foldername(name))[1] IN (
                SELECT tenant_id::text
                FROM public.user_profiles
                WHERE auth_user_id = auth.uid()
            )
        );
    END IF;
END $$;

-- Service-role full access (forms.submit + signed-URL minter run here).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='storage' AND tablename='objects'
          AND policyname='lead_documents_service_all'
    ) THEN
        CREATE POLICY lead_documents_service_all ON storage.objects
        FOR ALL TO service_role
        USING (bucket_id = 'lead-documents')
        WITH CHECK (bucket_id = 'lead-documents');
    END IF;
END $$;
