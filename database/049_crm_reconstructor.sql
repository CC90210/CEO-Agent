-- ============================================================================
-- Migration 049 — CRM Reconstructor substrate
--
-- Round 3 of the SunBiz CRM build. Pairs with the 2026-05-16 meeting
-- (Adon ↔ Oasis) that ratified Salesforce-parity Lead + Opportunity
-- pipelines, AI missing-info classification, email-open tracking, and
-- per-lead conversation timeline.
--
-- Adds three tenant-scoped event tables that the Phase 18-20 dashboard
-- work + classifier extension write to:
--
--   email_open_events  — tracking-pixel hits from outbound emails. Read
--                        by the lead drawer Timeline tab + the
--                        sequence_runner email-open-followup handler.
--
--   lead_documents     — per-lead document attachments (bank statements,
--                        void cheques, etc). Populated by:
--                          1) the multi-step intake form (Phase 21)
--                          2) the drag-drop Documents tab in the lead
--                             drawer (Phase 18)
--                        Used by Phase 20's classifier to auto-clear
--                        items from lead.missing_info when a document
--                        of the matching type lands.
--
--   agent_alerts       — operator-facing notifications surfaced in the
--                        daily briefing snapshot + Telegram pings. The
--                        Phase 20 classifier raises one of these on
--                        first detection of missing_info per lead.
--
-- Tenant scoping: every row carries tenant_id (FK tenants(id)). RLS
-- policies follow the tenant_records pattern from migration 038 —
-- members SELECT/INSERT/UPDATE within their tenant; service-role
-- bypasses for daemons + classifier writes.
--
-- Note on lead.missing_info + lead.stage:
--   Lead data lives in tenant_records.data jsonb keyed by
--   entity_type='lead' (see migration 038). Both fields are JSONB
--   additions to that blob, NOT new columns — the manifest data_model
--   in apps/command-center/lib/manifest/seeds.ts is the schema source
--   of truth. This migration adds NO columns to tenant_records.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. email_open_events
-- ----------------------------------------------------------------------------
-- One row per tracking-pixel hit. Multiple opens of the same email are
-- expected (re-opens, forwards, multiple devices); we keep them all so
-- the timeline can render engagement-over-time. Deduplication for
-- "did this lead open this email at all?" is a COUNT > 0 query, not a
-- DB constraint.
--
-- outbound_message_id: matches scripts/send_gateway.py's emitted
-- message_id (the value embedded in the pixel URL). Stored as text
-- because send_gateway uses opaque string ids, not uuids, for some
-- legacy channels.
--
-- suspicious_prefetch: true when opened_at - send timestamp < 60s.
-- Apple Mail Privacy Protection pre-fetches images so opens look
-- instant. Phase 19 down-weights these in the drip fast-forward logic.
CREATE TABLE IF NOT EXISTS public.email_open_events (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    outbound_message_id   text NOT NULL,
    lead_id               uuid,
    opened_at             timestamptz NOT NULL DEFAULT now(),
    user_agent            text,
    ip_hash               text,
    suspicious_prefetch   boolean NOT NULL DEFAULT false,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_open_events_tenant_lead
    ON public.email_open_events (tenant_id, lead_id, opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_open_events_message
    ON public.email_open_events (outbound_message_id);

ALTER TABLE public.email_open_events ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 2. lead_documents
-- ----------------------------------------------------------------------------
-- Per-lead document attachments. The actual file bytes live in Supabase
-- Storage under a tenant-scoped bucket; this table holds the metadata.
--
-- storage_path: tenant-scoped path within the storage bucket, e.g.
--               'sunbiz/leads/{lead_id}/{filename}'. The frontend never
--               reads files via this path directly — it requests a
--               signed URL from the documents API which validates
--               tenant membership before issuing.
--
-- doc_type: classifier output. Open-ended text so we can extend without
--           a migration. Known values produced by the Phase 20
--           classifier:
--               bank_statements_3mo / void_cheque / drivers_license /
--               proof_of_ownership / business_license / tax_returns /
--               other / unclassified
--           The lead.missing_info auto-clear in Phase 20 keys off this
--           string match.
--
-- uploaded_by: free-form (operator email, "form_intake", "ai_classifier")
--              so audit can render provenance without joining a users
--              table. NULL = unknown / legacy.
CREATE TABLE IF NOT EXISTS public.lead_documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    lead_id         uuid NOT NULL,
    filename        text NOT NULL,
    storage_path    text NOT NULL,
    mime_type       text,
    size_bytes      bigint,
    doc_type        text NOT NULL DEFAULT 'unclassified',
    uploaded_by     text,
    uploaded_at     timestamptz NOT NULL DEFAULT now(),
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_lead_documents_tenant_lead
    ON public.lead_documents (tenant_id, lead_id, uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_lead_documents_doc_type
    ON public.lead_documents (tenant_id, doc_type)
    WHERE doc_type <> 'unclassified';

ALTER TABLE public.lead_documents ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 3. agent_alerts
-- ----------------------------------------------------------------------------
-- Operator-facing notifications distinct from drip sends. A drip step
-- talks TO the lead; an agent_alert talks TO the operator about the
-- lead. Surfaced in:
--   - Daily briefing snapshot (Phase 23.3)
--   - Telegram ping via existing bravo-telegram daemon (Phase 20.5)
--   - /today dashboard block on the SunBiz tenant home
--
-- alert_type: enum-like text. Initial set:
--   'missing_info'      — Phase 20 classifier detected unfulfilled doc
--   'email_opened'      — lead opened a sent application but no follow-up
--                          (Phase 22 future use)
--   'lender_response'   — lender thread classifier flagged a reply
--   'manual'            — operator-created reminder
--
-- severity: 'info' / 'warn' / 'urgent'. Telegram pings only fire for
-- 'warn'+'urgent' to avoid notification fatigue.
--
-- dedup_key: optional. When set, an INSERT with the same (tenant_id,
-- dedup_key) is a no-op via the unique index — so the missing_info
-- classifier can call the alert path on every poll without re-pinging
-- CC each cycle. Format convention: 'missing_info:{lead_id}'.
--
-- resolved_at: NULL = open. Operator marks resolved from the drawer or
-- daily briefing UI.
CREATE TABLE IF NOT EXISTS public.agent_alerts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    alert_type      text NOT NULL,
    severity        text NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warn','urgent')),
    subject_type    text,                -- 'lead' / 'application' / 'offer' / 'funded_deal'
    subject_id      uuid,
    title           text NOT NULL,
    body            text,
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
    dedup_key       text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    resolved_at     timestamptz,
    resolved_by     text
);

CREATE INDEX IF NOT EXISTS idx_agent_alerts_open
    ON public.agent_alerts (tenant_id, severity, created_at DESC)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_agent_alerts_subject
    ON public.agent_alerts (tenant_id, subject_type, subject_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_alerts_dedup
    ON public.agent_alerts (tenant_id, dedup_key)
    WHERE dedup_key IS NOT NULL AND resolved_at IS NULL;

ALTER TABLE public.agent_alerts ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 4. RLS — mirror tenant_records pattern (member-scoped CRUD)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    -- email_open_events
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='email_open_events'
          AND policyname='email_open_events_member_all'
    ) THEN
        CREATE POLICY email_open_events_member_all ON public.email_open_events
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    -- lead_documents
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='lead_documents'
          AND policyname='lead_documents_member_all'
    ) THEN
        CREATE POLICY lead_documents_member_all ON public.lead_documents
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;

    -- agent_alerts
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='agent_alerts'
          AND policyname='agent_alerts_member_all'
    ) THEN
        CREATE POLICY agent_alerts_member_all ON public.agent_alerts
            FOR ALL TO authenticated
            USING (tenant_id = public.current_tenant_id())
            WITH CHECK (tenant_id = public.current_tenant_id());
    END IF;
END $$;

COMMIT;
