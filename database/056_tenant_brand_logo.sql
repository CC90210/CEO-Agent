-- 056_tenant_brand_logo.sql
-- ---------------------------------------------------------------------------
-- Per-tenant brand logo: stored once in Settings → Branding, auto-applied
-- wherever the tenant's identity is rendered (form intake pages, public
-- form headers, future email signatures). Replaces the per-form
-- branding.logo_url field as the canonical source — the form-builder
-- input still exists as an override but defaults to this value.
--
-- Storage:
--   - tenant-assets bucket (public read; logos are intentionally fetchable
--     from public form pages without auth). Tenant-scoped folder layout
--     means a misconfigured policy can't accidentally leak another
--     tenant's bytes — every object lives under <tenant_id>/.
--   - tenants.logo_url column carries the resolved public URL (cheap
--     for every page that renders the brand to read).
-- ---------------------------------------------------------------------------

ALTER TABLE public.tenants
    ADD COLUMN IF NOT EXISTS logo_url text;

INSERT INTO storage.buckets (id, name, public)
VALUES ('tenant-assets', 'tenant-assets', true)
ON CONFLICT (id) DO NOTHING;

-- Anyone can READ tenant-assets (public form pages need it). The path
-- prefix anchors the namespace so the bucket can't be reused for
-- non-branding assets later without a separate folder convention.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='storage' AND tablename='objects'
          AND policyname='tenant_assets_public_read'
    ) THEN
        CREATE POLICY tenant_assets_public_read ON storage.objects
        FOR SELECT TO public
        USING (bucket_id = 'tenant-assets');
    END IF;
END $$;

-- Writes happen via the service-role route (apps/command-center/app/api/
-- tenant/logo/route.ts) after verifying the operator belongs to the
-- target tenant. Service role bypasses storage RLS so no policy needed
-- for the write path, but be explicit:
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='storage' AND tablename='objects'
          AND policyname='tenant_assets_service_write'
    ) THEN
        CREATE POLICY tenant_assets_service_write ON storage.objects
        FOR ALL TO service_role
        USING (bucket_id = 'tenant-assets')
        WITH CHECK (bucket_id = 'tenant-assets');
    END IF;
END $$;
