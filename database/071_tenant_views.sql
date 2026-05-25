-- ============================================================================
-- Migration 071 — Saved Views (V6.9.1 substrate)
--
-- Pattern imported from twentyhq/twenty (AGPLv3 — patterns only, no code).
-- Promotes view configuration (which columns, what filters, what sort) from
-- session/URL state to first-class DB rows so operators can save named
-- views, share them workspace-wide, and have agents read what columns
-- are visible without parsing URL params.
--
-- DEPENDS ON: migration 070 (object_metadata, field_metadata).
--
-- Precedence rule (paired with V6.9.0):
--   - manifest.pages[].kind continues to own which RENDERER fires
--     (table | kanban | calendar | gallery | ...).
--   - views row owns which FIELDS show + filter + sort + per-column width.
--   - URL params (?stage=, ?sortBy=, ?q=) remain as fallback for ad-hoc
--     filtering when no view is selected (preserves Phase-1 behavior).
--
-- Ownership semantics (`views.owner_user_id`):
--   - NULL  → workspace-shared view, visible to every tenant member
--   - UUID  → per-user view, visible only to that user (private filter)
--   At most one workspace-shared view per (tenant_id, object_metadata_id)
--   carries is_default=true; the loader uses that when no viewId is given.
--
-- Tables created (4, all additive + idempotent):
--   views          named view definition (kind + ownership + default)
--   view_fields    which fields appear, in what order, at what width
--   view_filters   field + operator + value, joined by conjunction
--   view_sorts     field + direction, multi-key ordering
--
-- Apply: python scripts/apply_migration.py database/071_tenant_views.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. view_kind enum
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'view_kind') THEN
        CREATE TYPE public.view_kind AS ENUM (
            'table',
            'kanban',
            'calendar',
            'gallery'
        );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. view_filter_operator enum — 10 operators matching twenty's stable set
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'view_filter_operator') THEN
        CREATE TYPE public.view_filter_operator AS ENUM (
            'eq',
            'neq',
            'gt',
            'lt',
            'gte',
            'lte',
            'contains',
            'starts_with',
            'in',
            'is_null'
        );
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3. views
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.views (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    object_metadata_id  uuid NOT NULL REFERENCES public.object_metadata(id) ON DELETE CASCADE,
    slug                text NOT NULL,
    name                text NOT NULL,
    kind                public.view_kind NOT NULL DEFAULT 'table',
    owner_user_id       uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    is_default          boolean NOT NULL DEFAULT false,
    is_active           boolean NOT NULL DEFAULT true,
    /* kanban-specific: which select field drives the columns. NULL for table/
       calendar/gallery views. FK enforced by API, not DB, so the column can
       reference field_metadata.name (operator-friendly) instead of UUID. */
    kanban_field_name   text,
    description         text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, object_metadata_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_views_tenant_object
    ON public.views (tenant_id, object_metadata_id)
    WHERE is_active = true;

ALTER TABLE public.views ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.views IS
    '071 V6.9.1 — saved view definitions. Workspace-shared when owner_user_id IS NULL; per-user otherwise. is_default flags the loader default per (tenant, object).';

-- ---------------------------------------------------------------------------
-- 4. view_fields — column visibility + ordering + width
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.view_fields (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    view_id             uuid NOT NULL REFERENCES public.views(id) ON DELETE CASCADE,
    field_metadata_id   uuid NOT NULL REFERENCES public.field_metadata(id) ON DELETE CASCADE,
    position            int NOT NULL DEFAULT 0,
    width               int,                             -- pixel hint for table; NULL = auto
    is_visible          boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (view_id, field_metadata_id)
);

CREATE INDEX IF NOT EXISTS idx_view_fields_view
    ON public.view_fields (view_id, position)
    WHERE is_visible = true;

ALTER TABLE public.view_fields ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 5. view_filters — field op value (joined by conjunction)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.view_filters (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    view_id             uuid NOT NULL REFERENCES public.views(id) ON DELETE CASCADE,
    field_metadata_id   uuid NOT NULL REFERENCES public.field_metadata(id) ON DELETE CASCADE,
    operator            public.view_filter_operator NOT NULL,
    value               jsonb,                           -- shape depends on operator + field type; null when operator='is_null'
    conjunction         text NOT NULL DEFAULT 'AND' CHECK (conjunction IN ('AND', 'OR')),
    position            int NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_view_filters_view
    ON public.view_filters (view_id, position);

ALTER TABLE public.view_filters ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 6. view_sorts — multi-key ordering
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.view_sorts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    view_id             uuid NOT NULL REFERENCES public.views(id) ON DELETE CASCADE,
    field_metadata_id   uuid NOT NULL REFERENCES public.field_metadata(id) ON DELETE CASCADE,
    direction           text NOT NULL DEFAULT 'ASC' CHECK (direction IN ('ASC', 'DESC')),
    position            int NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (view_id, field_metadata_id)
);

CREATE INDEX IF NOT EXISTS idx_view_sorts_view
    ON public.view_sorts (view_id, position);

ALTER TABLE public.view_sorts ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 7. RLS — tenant-scoped on `views`; children inherit via parent FK lookup
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='views' AND policyname='views_member_all'
    ) THEN
        CREATE POLICY views_member_all ON public.views
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='view_fields' AND policyname='view_fields_member_all'
    ) THEN
        CREATE POLICY view_fields_member_all ON public.view_fields
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM public.views v WHERE v.id = view_fields.view_id AND v.tenant_id = public.current_tenant_id()))
            WITH CHECK (EXISTS (SELECT 1 FROM public.views v WHERE v.id = view_fields.view_id AND v.tenant_id = public.current_tenant_id()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='view_filters' AND policyname='view_filters_member_all'
    ) THEN
        CREATE POLICY view_filters_member_all ON public.view_filters
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM public.views v WHERE v.id = view_filters.view_id AND v.tenant_id = public.current_tenant_id()))
            WITH CHECK (EXISTS (SELECT 1 FROM public.views v WHERE v.id = view_filters.view_id AND v.tenant_id = public.current_tenant_id()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='view_sorts' AND policyname='view_sorts_member_all'
    ) THEN
        CREATE POLICY view_sorts_member_all ON public.view_sorts
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM public.views v WHERE v.id = view_sorts.view_id AND v.tenant_id = public.current_tenant_id()))
            WITH CHECK (EXISTS (SELECT 1 FROM public.views v WHERE v.id = view_sorts.view_id AND v.tenant_id = public.current_tenant_id()));
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 8. updated_at trigger on views (the only table that needs it; the
--    children are append/replace-style and shouldn't auto-touch)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.views_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS views_set_updated_at ON public.views;
CREATE TRIGGER views_set_updated_at
    BEFORE UPDATE ON public.views
    FOR EACH ROW EXECUTE FUNCTION public.views_touch_updated_at();

COMMIT;
