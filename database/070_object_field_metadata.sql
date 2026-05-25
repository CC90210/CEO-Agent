-- ============================================================================
-- Migration 070 — Object Metadata + Field Metadata (V6.9.0 substrate)
--
-- Foundation of V6.9 CRM Substrate. Patterns extracted from twentyhq/twenty
-- (AGPLv3 — patterns only, no code copied). Replaces the inline-JSON-only
-- data_model in tenant_manifests with first-class DB-backed entity + field
-- registries.
--
-- WHY (per ~/.claude/plans/i-m-dropping-you-a-magical-cat.md):
--   - Inline manifest.data_model[] can be parsed but not introspected by the AI
--     editor (gap #8 from docs/AGENT_COMMAND_CENTER_HANDOFF.md). DB rows make
--     the entity/field surface queryable, mutable per-tenant, and the foundation
--     for V6.9.1 (saved views — FK target) and V6.9.4 (AI manifest editor).
--   - 16-type enum is a deliberate superset of the 7 inline types so future
--     custom-field UX (currency / address / rich_text / relation) lands without
--     a second migration.
--
-- FORWARD-ONLY SEMANTICS (split-brain mitigation per researcher's risk note):
--   New entity types use object_metadata + field_metadata. Existing
--   tenant_records.data JSONB stays unchanged. The schema-introspector
--   (lib/schema-introspector.ts) falls back to manifest.data_model[] when no
--   row exists, so this migration is non-breaking. No backfill required.
--
-- Tables created (3, all additive + idempotent):
--   object_metadata        per-tenant entity-type registry
--   field_metadata         typed fields under an object_metadata
--   (field_metadata_type)  enum: 16 types (text/number/boolean/date/datetime/
--                          enum/json + currency/address/rich_text/link/
--                          multi_select/rating/phone/email/relation)
--
-- RLS posture:
--   Tenant-scoped via current_tenant_id() (same pattern as 038's
--   tenant_records / tenant_manifests). Service-role bypasses RLS as usual
--   (loader uses service-role server-side).
--
-- Apply: python scripts/apply_migration.py database/070_object_field_metadata.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. field_metadata_type enum
--
-- Stable shape — adding new types is an additive ALTER TYPE; removing a type
-- requires a deprecation migration that nulls field_metadata rows referencing
-- it first. Don't reorder values (Postgres enum order is stable but visible).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'field_metadata_type') THEN
        CREATE TYPE public.field_metadata_type AS ENUM (
            'text',          -- short string, single line
            'number',        -- numeric (use options.precision for scale hints)
            'boolean',
            'date',          -- date-only (no time component)
            'datetime',      -- timestamptz
            'enum',          -- one-of from options.enum_values[]
            'json',          -- arbitrary JSON blob (escape hatch)
            'currency',      -- numeric + currency code in options.currency
            'address',       -- structured: street/city/region/postal/country
            'rich_text',     -- markdown / tiptap-style structured text
            'link',          -- URL with optional display label
            'multi_select',  -- many-of from options.enum_values[]
            'rating',        -- 0-5 (or 0-options.max) integer
            'phone',         -- E.164-validated string
            'email',         -- validated email string
            'relation'       -- FK to another object_metadata; options.target_object_slug + options.cardinality
        );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. object_metadata
--
-- One row per (tenant_id, slug). is_system distinguishes built-in entity
-- types (lead, application, lender) from operator-defined ones; system rows
-- are protected from delete by the API layer (no DB constraint — schema
-- evolution shouldn't require a re-migration to flip is_system).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.object_metadata (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    slug            text NOT NULL,
    label           text NOT NULL,
    label_plural    text NOT NULL,
    icon            text,                                -- ManifestNavIconKey hint (LayoutDashboard, Users, etc.)
    description     text,
    is_system       boolean NOT NULL DEFAULT false,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_object_metadata_tenant
    ON public.object_metadata (tenant_id)
    WHERE is_active = true;

ALTER TABLE public.object_metadata ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.object_metadata IS
    '070 V6.9.0 — per-tenant entity-type registry. Replaces inline manifest.data_model[] for new entity types; existing tenant_records JSONB remains valid via schema-introspector fallback.';

-- ---------------------------------------------------------------------------
-- 3. field_metadata
--
-- One row per (object_id, name). Position controls form-render order; the
-- API treats gaps in position as fine — it sorts at read time. options JSONB
-- holds type-specific config (enum_values, currency code, target_object_slug,
-- etc.); no DB constraint on its shape because validation lives in the API.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.field_metadata (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    object_id       uuid NOT NULL REFERENCES public.object_metadata(id) ON DELETE CASCADE,
    name            text NOT NULL,
    label           text NOT NULL,
    type            public.field_metadata_type NOT NULL,
    default_value   jsonb,
    options         jsonb DEFAULT '{}'::jsonb,           -- type-specific: { enum_values, currency, target_object_slug, max, precision, ... }
    is_required     boolean NOT NULL DEFAULT false,
    is_unique       boolean NOT NULL DEFAULT false,      -- enforced in API; no UNIQUE INDEX (would conflict with JSONB-stored values)
    is_system       boolean NOT NULL DEFAULT false,
    is_active       boolean NOT NULL DEFAULT true,
    position        int NOT NULL DEFAULT 0,
    description     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (object_id, name)
);

CREATE INDEX IF NOT EXISTS idx_field_metadata_object
    ON public.field_metadata (object_id, position)
    WHERE is_active = true;

ALTER TABLE public.field_metadata ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.field_metadata IS
    '070 V6.9.0 — typed field registry under object_metadata. Type enum has 16 values incl. currency/address/rich_text/multi_select/rating/relation. options JSONB is type-specific.';

-- ---------------------------------------------------------------------------
-- 4. RLS policies — tenant-scoped via current_tenant_id() (matches 038)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='object_metadata'
          AND policyname='object_metadata_member_all'
    ) THEN
        CREATE POLICY object_metadata_member_all ON public.object_metadata
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    -- field_metadata RLS piggy-backs on object_metadata's tenant scope via FK;
    -- a member who can see the parent object can see/mutate its fields.
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='field_metadata'
          AND policyname='field_metadata_member_all'
    ) THEN
        CREATE POLICY field_metadata_member_all ON public.field_metadata
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM public.object_metadata om
                    WHERE om.id = field_metadata.object_id
                      AND om.tenant_id = public.current_tenant_id()
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM public.object_metadata om
                    WHERE om.id = field_metadata.object_id
                      AND om.tenant_id = public.current_tenant_id()
                )
            );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 5. updated_at triggers (matches 038's tenant_manifests pattern)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.object_metadata_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS object_metadata_set_updated_at ON public.object_metadata;
CREATE TRIGGER object_metadata_set_updated_at
    BEFORE UPDATE ON public.object_metadata
    FOR EACH ROW EXECUTE FUNCTION public.object_metadata_touch_updated_at();

CREATE OR REPLACE FUNCTION public.field_metadata_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS field_metadata_set_updated_at ON public.field_metadata;
CREATE TRIGGER field_metadata_set_updated_at
    BEFORE UPDATE ON public.field_metadata
    FOR EACH ROW EXECUTE FUNCTION public.field_metadata_touch_updated_at();

COMMIT;
