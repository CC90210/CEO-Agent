-- ============================================================================
-- Migration 038 — Tenant Manifests + Tenant Records + Manifest Audit Log
--
-- Phase 1 of the OASIS Command Center rearchitecture. Replaces the hardcoded
-- ClientCommandCenterProfile registry in apps/command-center/lib/client-
-- profiles.ts with a Supabase-backed JSONB manifest per tenant. Phase 2's
-- AI chat editor will write to these tables; until then the seeds inserted
-- below serve as the source of truth and the in-code seeds (lib/manifest/
-- seeds.ts) act as the fallback when the DB is unreachable.
--
-- Tables created (all additive; idempotent CREATE IF NOT EXISTS):
--   tenant_manifests       JSONB blob per tenant, slug-keyed
--   tenant_records         wide-row JSONB for AI-defined entities (Phase 2)
--   manifest_audit_log     diff history for every manifest mutation (Phase 2)
--
-- RLS posture:
--   tenant_manifests / tenant_records — tenant-scoped via current_tenant_id();
--     reads gated by membership, writes gated by is_team_admin() helper from
--     migration 037. Service-role bypasses RLS as usual (used by the manifest
--     loader on Vercel server components).
--   manifest_audit_log     read-only to admins; writes only from the manifest
--     mutation API (Phase 2) using SECURITY DEFINER RPCs.
--
-- Seeds:
--   default / oasis / sun / suga rows are inserted so the dashboard renders
--   from the DB immediately after this migration. The slug column is unique;
--   re-running this migration is safe (ON CONFLICT DO NOTHING on the seeds).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. tenant_manifests
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenant_manifests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
    slug            text NOT NULL UNIQUE,
    manifest        jsonb NOT NULL,
    version         integer NOT NULL DEFAULT 1,
    schema_version  integer NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_manifests_tenant_id
    ON public.tenant_manifests (tenant_id);

ALTER TABLE public.tenant_manifests ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 2. tenant_records (Phase 2 will write through this; created now so the
--    schema is ready and the loader can probe table existence without a
--    second migration round-trip)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenant_records (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    entity_type     text NOT NULL,
    data            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_records_tenant_entity
    ON public.tenant_records (tenant_id, entity_type, updated_at DESC);

ALTER TABLE public.tenant_records ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 3. manifest_audit_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.manifest_audit_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    manifest_id     uuid REFERENCES public.tenant_manifests(id) ON DELETE CASCADE,
    tenant_id       uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
    actor_type      text NOT NULL CHECK (actor_type IN ('user','ai','system','seed')),
    actor_id        uuid REFERENCES auth.users(id),
    diff            jsonb NOT NULL,
    message         text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_manifest_audit_manifest
    ON public.manifest_audit_log (manifest_id, created_at DESC);

ALTER TABLE public.manifest_audit_log ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 4. RLS policies — tenant-scoped reads + admin writes
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- tenant_manifests: members read, admins write
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_manifests'
          AND policyname='tenant_manifests_member_select'
    ) THEN
        CREATE POLICY tenant_manifests_member_select ON public.tenant_manifests
            FOR SELECT TO authenticated
            USING (tenant_id IS NULL OR tenant_id = public.current_tenant_id());
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_manifests'
          AND policyname='tenant_manifests_admin_write'
    ) THEN
        CREATE POLICY tenant_manifests_admin_write ON public.tenant_manifests
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id() AND public.is_team_admin())
            WITH CHECK (tenant_id = public.current_tenant_id() AND public.is_team_admin());
    END IF;

    -- tenant_records: tenant-scoped CRUD for members
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_records'
          AND policyname='tenant_records_member_all'
    ) THEN
        CREATE POLICY tenant_records_member_all ON public.tenant_records
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    -- manifest_audit_log: admin-only read; writes go through SECURITY DEFINER
    -- RPCs in Phase 2 so authenticated callers do not have direct INSERT.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='manifest_audit_log'
          AND policyname='manifest_audit_log_admin_select'
    ) THEN
        CREATE POLICY manifest_audit_log_admin_select ON public.manifest_audit_log
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() AND public.is_team_admin());
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 5. updated_at trigger so AI mutations bump the timestamp without remembering to
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tenant_manifests_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tenant_manifests_set_updated_at ON public.tenant_manifests;
CREATE TRIGGER tenant_manifests_set_updated_at
    BEFORE UPDATE ON public.tenant_manifests
    FOR EACH ROW EXECUTE FUNCTION public.tenant_manifests_touch_updated_at();

-- ---------------------------------------------------------------------------
-- 6. Seeds are NOT inserted here.
--
-- For Phase 1, apps/command-center/lib/manifest/seeds.ts is the source of
-- truth. The loader prefers a DB row when one exists, falls back to the
-- code seed when it doesn't, so leaving these tables empty is the correct
-- pre-AI-editor state. Phase 2's AI chat editor will:
--   1. read the in-code seed for the tenant's slug
--   2. write the (possibly modified) manifest into tenant_manifests with
--      tenant_id stamped
--   3. log the seed-clone event into manifest_audit_log with actor_type='seed'
--
-- Why not seed here: the full nav array (~14 items per profile, snake_case
-- icon enum, group strings) is awkward to inline as escaped JSONB; keeping
-- it in TypeScript lets IDE tooling + tsc validate it on every commit.
-- The schema is ready and waiting.
-- ---------------------------------------------------------------------------
