-- ============================================================================
-- Migration 073 — V6.9.5 cross-table tenant integrity (hotfix)
--
-- Codex audit (2026-05-25) flagged that 071 + 072 lack composite tenant
-- integrity: a `views` row's tenant_id could differ from its
-- object_metadata's tenant_id without the DB stopping it. Same for
-- workflow_runs vs workflows. RLS catches reads, but a malicious or buggy
-- writer could insert cross-tenant rows that pass RLS at insert time and
-- then surface to the wrong tenant via direct id lookups.
--
-- This migration adds CHECK triggers (not generated columns — Postgres
-- can't enforce a generated FK column easily across tables) that compare
-- the child's tenant_id against the parent's at insert/update time.
--
-- Apply: python scripts/apply_migration.py database/073_v695_tenant_integrity.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. views.tenant_id MUST match object_metadata.tenant_id
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.views_tenant_integrity_check()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_tenant uuid;
BEGIN
    SELECT tenant_id INTO parent_tenant
    FROM public.object_metadata
    WHERE id = NEW.object_metadata_id;
    IF parent_tenant IS NULL THEN
        RAISE EXCEPTION 'views.object_metadata_id % does not exist', NEW.object_metadata_id;
    END IF;
    IF parent_tenant <> NEW.tenant_id THEN
        RAISE EXCEPTION 'views.tenant_id % does not match object_metadata.tenant_id %',
            NEW.tenant_id, parent_tenant;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS views_tenant_integrity ON public.views;
CREATE TRIGGER views_tenant_integrity
    BEFORE INSERT OR UPDATE OF tenant_id, object_metadata_id ON public.views
    FOR EACH ROW EXECUTE FUNCTION public.views_tenant_integrity_check();

-- ---------------------------------------------------------------------------
-- 2. workflow_runs.tenant_id MUST match workflows.tenant_id
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.workflow_runs_tenant_integrity_check()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_tenant uuid;
BEGIN
    SELECT tenant_id INTO parent_tenant
    FROM public.workflows
    WHERE id = NEW.workflow_id;
    IF parent_tenant IS NULL THEN
        RAISE EXCEPTION 'workflow_runs.workflow_id % does not exist', NEW.workflow_id;
    END IF;
    IF parent_tenant <> NEW.tenant_id THEN
        RAISE EXCEPTION 'workflow_runs.tenant_id % does not match workflows.tenant_id %',
            NEW.tenant_id, parent_tenant;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workflow_runs_tenant_integrity ON public.workflow_runs;
CREATE TRIGGER workflow_runs_tenant_integrity
    BEFORE INSERT OR UPDATE OF tenant_id, workflow_id ON public.workflow_runs
    FOR EACH ROW EXECUTE FUNCTION public.workflow_runs_tenant_integrity_check();

-- ---------------------------------------------------------------------------
-- 3. view_fields/filters/sorts — verify field_metadata's object_id matches
--    the view's object_metadata_id (prevents binding a field from object X
--    to a view defined against object Y)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.view_field_object_integrity_check()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    view_object uuid;
    field_object uuid;
BEGIN
    SELECT object_metadata_id INTO view_object FROM public.views WHERE id = NEW.view_id;
    SELECT object_id INTO field_object FROM public.field_metadata WHERE id = NEW.field_metadata_id;
    IF view_object IS NULL OR field_object IS NULL THEN
        RAISE EXCEPTION 'view_id % or field_metadata_id % does not exist', NEW.view_id, NEW.field_metadata_id;
    END IF;
    IF view_object <> field_object THEN
        RAISE EXCEPTION 'view_fields/filters/sorts: field_metadata belongs to object % but view is bound to object %',
            field_object, view_object;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS view_fields_object_integrity ON public.view_fields;
CREATE TRIGGER view_fields_object_integrity
    BEFORE INSERT OR UPDATE ON public.view_fields
    FOR EACH ROW EXECUTE FUNCTION public.view_field_object_integrity_check();

DROP TRIGGER IF EXISTS view_filters_object_integrity ON public.view_filters;
CREATE TRIGGER view_filters_object_integrity
    BEFORE INSERT OR UPDATE ON public.view_filters
    FOR EACH ROW EXECUTE FUNCTION public.view_field_object_integrity_check();

DROP TRIGGER IF EXISTS view_sorts_object_integrity ON public.view_sorts;
CREATE TRIGGER view_sorts_object_integrity
    BEFORE INSERT OR UPDATE ON public.view_sorts
    FOR EACH ROW EXECUTE FUNCTION public.view_field_object_integrity_check();

COMMIT;
