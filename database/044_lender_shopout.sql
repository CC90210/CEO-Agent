-- Migration 044 — Lender shop-out: extended lender fields + per-application
-- lender-thread tracking
--
-- Phase 6 of the SunBiz CRM build (2026-05-15). Jordan's meeting framed
-- the "shopping out" process as the critical funding-shop function:
-- operator picks N lenders, attaches the lead's bank statements, fires
-- a separate email thread to each lender (with team CC), and tracks
-- per-lender approval / decline / info-requested status as replies
-- come back.
--
-- Two data changes ship together:
--
-- 1. Extended lender catalog. The pre-Phase-6 lender entity only had
--    name + contact + product_types. The meeting added match-fitness
--    fields (min_revenue, max_funded, time_in_business, fico_floor)
--    so the shop-out UI can pre-rank lenders against a deal's profile
--    instead of operators eyeballing a 50-lender spreadsheet.
--
-- 2. Application.lender_threads tracking. Each shop-out email gets a
--    row here keyed by (application_id, lender_id) with the Gmail
--    thread_id and a status enum. Phase 6.4's response classifier
--    daemon polls Gmail labels and updates status as lenders reply.
--
-- Apply via: python scripts/apply_migration.py database/044_lender_shopout.sql

BEGIN;

-- ============================================================================
-- application_lender_threads — per-(application, lender) shop-out tracking
-- ============================================================================
--
-- Modeled as a SEPARATE TABLE (vs jsonb on the application row) because:
--   1. Each lender thread has its own lifecycle independent of the others
--      (lender A approves, lender B declines, lender C is silent — three
--      timelines, three update paths)
--   2. The response classifier daemon (Phase 6.4) writes one row at a
--      time. A jsonb array on the application row would require read-
--      modify-write with concurrency risk.
--   3. Indexes on status + last_response_at give the operator UI cheap
--      "show me all stalled lenders this week" queries.
CREATE TABLE IF NOT EXISTS public.application_lender_threads (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Application is a tenant_records row (entity_type='application');
    -- stored as text (no FK) since tenant_records is JSONB wide-row.
    application_id    text NOT NULL,
    -- Lender is similarly a tenant_records row (entity_type='lender').
    lender_id         text NOT NULL,
    -- Denormalized for RLS — every thread filter starts with tenant_id
    -- so the policy can match cheaply without joining tenant_records.
    tenant_id         uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- Gmail thread ID the shop-out email belongs to. NULL during the
    -- brief window between row creation and email send.
    gmail_thread_id   text,
    -- Subject line we used (operator can edit per-lender; helpful for
    -- the operator UI to show the actual outreach copy without joining
    -- to Gmail).
    subject           text,
    -- Lifecycle:
    --   pending       — created, email not yet sent (transient)
    --   sent          — email shipped; awaiting response
    --   responded     — any reply received; classifier hasn't decided
    --                   yet (rare — usually classifier runs within ~5min)
    --   approved      — lender returned an offer
    --   declined      — lender passed
    --   info_requested — lender asked for additional docs / clarification
    --   no_response   — silent past the SLA window (e.g. 7 days)
    --   error         — bounce, send failure, or classifier confused
    status            text NOT NULL DEFAULT 'pending'
                      CHECK (status IN (
                          'pending', 'sent', 'responded',
                          'approved', 'declined', 'info_requested',
                          'no_response', 'error'
                      )),
    -- Operator-set CC list (Ezra, Ethan, Emily on SunBiz). Stored as
    -- jsonb array of email strings. Audit-only — the actual To/CC
    -- happens at send time.
    cc_emails         jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- Last response timestamp + summary the classifier extracted so
    -- operators can see "approved at amount X / term Y" without
    -- opening Gmail. Free-text from the classifier.
    last_response_at  timestamptz,
    last_response_summary text,
    -- Most recent error message (bounce, classifier failure, etc.)
    last_error        text,
    -- Lifecycle audit
    sent_at           timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    -- One thread per (application, lender) pair. Re-shop creates a new
    -- application row (operator's choice) — we don't want to re-pollute
    -- an existing thread with a second outreach.
    UNIQUE (application_id, lender_id)
);

CREATE INDEX IF NOT EXISTS idx_lender_threads_tenant_status
    ON public.application_lender_threads (tenant_id, status, last_response_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_lender_threads_application
    ON public.application_lender_threads (application_id);
CREATE INDEX IF NOT EXISTS idx_lender_threads_gmail
    ON public.application_lender_threads (tenant_id, gmail_thread_id)
    WHERE gmail_thread_id IS NOT NULL;

CREATE TRIGGER trg_lender_threads_updated_at
    BEFORE UPDATE ON public.application_lender_threads
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

ALTER TABLE public.application_lender_threads ENABLE ROW LEVEL SECURITY;

CREATE POLICY lender_threads_tenant_all ON public.application_lender_threads
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMENT ON TABLE public.application_lender_threads IS
  'One row per (application, lender) shop-out. Phase 6 of SunBiz CRM. '
  'Response classifier daemon updates status as Gmail replies land. '
  'Operator UI shows the per-application lender matrix on the application '
  'detail page.';

-- ============================================================================
-- Extended lender entity — handled via manifest update + comments only.
-- ============================================================================
--
-- The lender entity lives in tenant_records as JSONB (per the V6
-- universal records pattern), so there's no Postgres column to add.
-- The manifest's data_model.lender.fields list is the authoritative
-- schema — we extend it in lib/manifest/seeds.ts (SUN_SEED) as part of
-- Phase 6.1, not here. Migration 044 only adds the new table.
--
-- Meeting-agreed extra fields on the lender entity (added in the
-- SUN_SEED commit accompanying this migration):
--   product_types[]       -- e.g. ["mca","term_loan","line_of_credit"]
--   min_monthly_revenue   -- match floor
--   max_funded_amount     -- ceiling per deal
--   min_time_in_business_months
--   fico_floor            -- operator skips when applicant FICO < floor
--   sla_response_days     -- the daemon's "no_response" cutoff
--   notes                 -- free-text operator memory

COMMIT;
