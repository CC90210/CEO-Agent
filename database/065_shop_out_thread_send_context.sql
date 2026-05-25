-- ============================================================================
-- Migration 065 — Persist send-context on application_lender_threads
--
-- Phase 6.3-bis (2026-05-25). The dashboard's POST /api/applications/[id]/
-- shop-out route queues threads at status='pending' but does NOT persist
-- the operator's body_template overrides or the per-thread attachments
-- the operator confirmed. That means a downstream bridge-side sender
-- (shop_out_sender.py — added in this same Phase) can't faithfully
-- reproduce what the operator approved; it'd have to re-render using
-- defaults, dropping the operator's notes silently. That's a "fake-
-- success" failure mode CC has explicitly told us to never ship.
--
-- This migration adds two optional columns:
--   - body_template:  text — the rendered body the operator approved
--                     (per-lender; substitutions already applied)
--   - attachments:    jsonb — array of {filename, storage_path,
--                     mime_type, size_bytes} the operator confirmed.
--                     Storage paths are tenant-scoped (validated at
--                     the dashboard route boundary), so the sender
--                     reads them as-is without re-validating.
--
-- Both default to NULL — legacy threads without persisted context
-- still pick up sane defaults when the sender runs (DEFAULT body
-- template + all required lead_documents auto-attached).
--
-- Idempotent. Apply via:
--   python scripts/apply_migration.py database/065_shop_out_thread_send_context.sql
-- ============================================================================

BEGIN;

DO $$
DECLARE
    v_added_body integer := 0;
    v_added_atts integer := 0;
BEGIN
    -- body_template ---------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'application_lender_threads'
          AND column_name  = 'body_template'
    ) THEN
        ALTER TABLE public.application_lender_threads
            ADD COLUMN body_template text;
        v_added_body := 1;
        RAISE NOTICE '[065] added column body_template';
    ELSE
        RAISE NOTICE '[065] column body_template already exists — skipping';
    END IF;

    -- attachments -----------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'application_lender_threads'
          AND column_name  = 'attachments'
    ) THEN
        ALTER TABLE public.application_lender_threads
            ADD COLUMN attachments jsonb NOT NULL DEFAULT '[]'::jsonb;
        v_added_atts := 1;
        RAISE NOTICE '[065] added column attachments';
    ELSE
        RAISE NOTICE '[065] column attachments already exists — skipping';
    END IF;

    -- Index supporting the pending-poll query the bridge sender runs:
    --   SELECT ... FROM application_lender_threads
    --   WHERE tenant_id = ? AND status = 'pending'
    --   ORDER BY created_at ASC
    --   LIMIT <batch>
    --
    -- tenant_id already lives in idx_lender_threads_tenant_status (migration
    -- 044) which sorts by status + last_response_at DESC NULLS LAST. That
    -- index is still cheap to scan for pending rows (status filter narrows
    -- hard), so no NEW index is added here. Adding a (tenant_id, status,
    -- created_at) index is a candidate if the pending queue grows to >10k
    -- rows per tenant; defer until then.

    RAISE NOTICE '[065] DONE — columns added: body=% atts=%', v_added_body, v_added_atts;
END $$;

COMMIT;
