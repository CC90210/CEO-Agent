-- 061_chat_attachments.sql
-- ---------------------------------------------------------------------------
-- Private chat attachment storage for the Agent Command Center.
--
-- Files uploaded in the ChatWidget land in Supabase Storage first, then a
-- tenant-scoped metadata row is inserted here. The model only receives a
-- bounded text excerpt by default; server-side tools can fetch the full
-- object when the operator explicitly asks for a workflow like importing
-- leads from an attached CSV.
-- ---------------------------------------------------------------------------

BEGIN;

CREATE TABLE IF NOT EXISTS public.chat_attachments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    auth_user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id      uuid REFERENCES public.chat_sessions(id) ON DELETE SET NULL,
    agent_key       text,
    filename        text NOT NULL,
    storage_bucket  text NOT NULL DEFAULT 'chat-attachments',
    storage_path    text NOT NULL,
    mime_type       text,
    size_bytes      bigint NOT NULL DEFAULT 0,
    parser          text NOT NULL DEFAULT 'metadata_only',
    text_excerpt    text,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_tenant_user_created
    ON public.chat_attachments (tenant_id, auth_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_session
    ON public.chat_attachments (tenant_id, session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'chat_attachments'
          AND constraint_name = 'chat_attachments_storage_path_tenant_prefix'
    ) THEN
        ALTER TABLE public.chat_attachments
            ADD CONSTRAINT chat_attachments_storage_path_tenant_prefix
            CHECK (storage_path LIKE tenant_id::text || '/%');
    END IF;
END $$;

ALTER TABLE public.chat_attachments ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='chat_attachments'
          AND policyname='chat_attachments_member_select'
    ) THEN
        CREATE POLICY chat_attachments_member_select ON public.chat_attachments
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id());
    END IF;
END $$;

INSERT INTO storage.buckets (id, name, public)
VALUES ('chat-attachments', 'chat-attachments', false)
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='storage' AND tablename='objects'
          AND policyname='chat_attachments_tenant_read'
    ) THEN
        CREATE POLICY chat_attachments_tenant_read ON storage.objects
        FOR SELECT TO authenticated
        USING (
            bucket_id = 'chat-attachments'
            AND (storage.foldername(name))[1] IN (
                SELECT tenant_id::text
                FROM public.user_profiles
                WHERE auth_user_id = auth.uid()
            )
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='storage' AND tablename='objects'
          AND policyname='chat_attachments_service_all'
    ) THEN
        CREATE POLICY chat_attachments_service_all ON storage.objects
        FOR ALL TO service_role
        USING (bucket_id = 'chat-attachments')
        WITH CHECK (bucket_id = 'chat-attachments');
    END IF;
END $$;

COMMIT;
