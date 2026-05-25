-- ============================================================================
-- Migration 069 — SunBiz second-meeting expansion (schema foundation)
--
-- The 2026-05-25 SunBiz product meeting added a substantial scope on top of
-- the Phase 1-12 restructure. This migration is the load-bearing schema
-- foundation for everything that follows. Single transactional file so the
-- entire foundation goes live atomically.
--
-- Tables added (12):
--   application_underwriting      -- automatic underwriting run output + metrics
--   follow_up_tasks               -- the Follow-Up Machine queue
--   daily_plan_items              -- per-day priority queue surface
--   cold_lead_lists               -- imported cold lists (NOT warm pipeline)
--   cold_leads                    -- members of a cold list
--   cold_outreach_campaigns       -- multi-channel blast campaigns
--   cold_outreach_recipients      -- per-recipient delivery state
--   shop_out_warnings             -- severity + override-note log (Proceed Anyway)
--   known_funding_companies       -- MCA registry for underwriting agent
--   offer_sources                 -- offer attribution (email/portal/manual)
--   email_thread_monitors         -- email-scanner cursor state per tenant
--   lender_feedback               -- intelligence learning tuples
--   personalized_form_links       -- token-backed per-lead form links
--   agent_memory_notes            -- tenant/lead-scoped operator notes
--
-- Indexes are conservative: every tenant_id, every (tenant_id, status) pair,
-- one composite per common WHERE pattern. No CHECK constraints on JSONB
-- payload columns — keeps schema migrations cheap while validation lives in
-- the API layer where errors can be surfaced to the operator.
--
-- All inserts/updates from the dashboard route through tenant-scoped service
-- functions; we rely on RLS being enabled by the manifest layer. Migration
-- adds the tables but does NOT enable RLS — RLS toggle is a separate
-- migration so the schema can be reviewed in isolation.
--
-- Apply: python scripts/apply_migration.py database/069_sunbiz_meeting2_expansion.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- application_underwriting — automatic underwriting agent output
-- ============================================================================
-- One row per (application_id, run_at). Re-runs are append-only so the
-- operator can see the progression as bank statements are added/replaced.
CREATE TABLE IF NOT EXISTS public.application_underwriting (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    application_id  uuid NOT NULL,
    run_at          timestamptz NOT NULL DEFAULT now(),
    triggered_by    text NOT NULL DEFAULT 'automatic',  -- 'automatic' | 'manual' | 'rerun'
    triggered_by_user_id uuid,
    status          text NOT NULL DEFAULT 'pending',    -- 'pending' | 'parsing' | 'complete' | 'error'
    parser_output   jsonb,                              -- statement_parser.py raw JSON
    debt_analysis   jsonb,                              -- debt_detector.py output
    sales_angle     text,                               -- sales_angle.py copy
    avg_monthly_revenue numeric(14,2),
    avg_daily_balance   numeric(14,2),
    nsf_count       int,
    deposit_consistency_pct numeric(5,2),
    debt_service_monthly numeric(14,2),
    debt_to_revenue_ratio numeric(8,4),
    lender_count    int,
    risk_flags      jsonb DEFAULT '[]'::jsonb,          -- ['stacked', 'declining_revenue', ...]
    readiness_score int,                                 -- 0-100 suggested
    error_message   text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_underwriting_tenant_app
    ON public.application_underwriting(tenant_id, application_id, run_at DESC);

CREATE INDEX IF NOT EXISTS idx_app_underwriting_status
    ON public.application_underwriting(tenant_id, status)
    WHERE status IN ('pending', 'parsing');

COMMENT ON TABLE public.application_underwriting IS
    '069 — automatic underwriting run output. Append-only; readiness_score is the agent suggestion, not a binding decision.';

-- ============================================================================
-- follow_up_tasks — the Follow-Up Machine queue
-- ============================================================================
-- Daily generator writes to this table; operator drains via the queue UI.
-- Snooze sets snoozed_until and the queue UI hides rows until that timestamp.
CREATE TABLE IF NOT EXISTS public.follow_up_tasks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    lead_id         uuid,                                -- nullable so we can task on applications too
    application_id  uuid,
    assignee_user_id uuid,                               -- nullable = unassigned
    reason          text NOT NULL,                       -- 'missing_info' | 'stalled' | 'no_response' | 'manual'
    reason_detail   text,                                -- one-line why
    due_at          timestamptz NOT NULL,
    status          text NOT NULL DEFAULT 'open',        -- 'open' | 'in_progress' | 'completed' | 'snoozed' | 'cancelled'
    attempt_count   int NOT NULL DEFAULT 0,
    last_attempt_at timestamptz,
    last_attempt_outcome text,                            -- 'no_answer' | 'voicemail' | 'connected' | 'callback_requested'
    snoozed_until   timestamptz,
    completed_at    timestamptz,
    completed_note  text,
    source          text NOT NULL DEFAULT 'auto',        -- 'auto' (daemon) | 'manual' (operator)
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_follow_up_tenant_status_due
    ON public.follow_up_tasks(tenant_id, status, due_at)
    WHERE status IN ('open', 'in_progress');

CREATE INDEX IF NOT EXISTS idx_follow_up_lead
    ON public.follow_up_tasks(tenant_id, lead_id, created_at DESC)
    WHERE lead_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_follow_up_application
    ON public.follow_up_tasks(tenant_id, application_id, created_at DESC)
    WHERE application_id IS NOT NULL;

COMMENT ON TABLE public.follow_up_tasks IS
    '069 — Follow-Up Machine queue. Auto-generated daily; snooze sets snoozed_until and the UI filters by that.';

-- ============================================================================
-- daily_plan_items — per-day priority queue
-- ============================================================================
-- The Daily Plan / Calls tab reads from here. Generator runs at 6am ET,
-- writes one row per (tenant_id, plan_date, lead_id_or_application_id, category).
-- Operator can dismiss items; dismissal hides for the rest of the day.
CREATE TABLE IF NOT EXISTS public.daily_plan_items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    plan_date       date NOT NULL,
    assignee_user_id uuid,
    lead_id         uuid,
    application_id  uuid,
    category        text NOT NULL,                       -- 'priority_call' | 'missing_info' | 'stuck' | 'new_offer' | 'shop_today' | 'renewal_eligible'
    priority        int NOT NULL DEFAULT 50,              -- 0-100, higher = render first
    reason          text NOT NULL,                       -- one-line why this is on today's plan
    metadata        jsonb DEFAULT '{}'::jsonb,           -- category-specific extras
    status          text NOT NULL DEFAULT 'open',        -- 'open' | 'done' | 'dismissed'
    completed_at    timestamptz,
    dismissed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_daily_plan_tenant_date
    ON public.daily_plan_items(tenant_id, plan_date, priority DESC, category);

CREATE INDEX IF NOT EXISTS idx_daily_plan_assignee
    ON public.daily_plan_items(tenant_id, assignee_user_id, plan_date, status)
    WHERE assignee_user_id IS NOT NULL;

COMMENT ON TABLE public.daily_plan_items IS
    '069 — Daily Plan/Calls queue. Generated daily at 6am ET; operator dismisses or completes per row.';

-- ============================================================================
-- cold_lead_lists + cold_leads — cold-list import storage (NOT warm pipeline)
-- ============================================================================
-- The Import page lets the operator paste/upload a cold list that becomes
-- shop-out targets later, NOT lead pipeline entries. Promoting a cold_lead
-- to a real lead (entity_type='lead' in tenant_records) is an explicit
-- operator action — the cold list is intentionally a holding pen.
CREATE TABLE IF NOT EXISTS public.cold_lead_lists (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    name            text NOT NULL,
    source          text,                                -- 'csv_upload' | 'manual_paste' | 'api_import'
    description     text,
    row_count       int NOT NULL DEFAULT 0,
    promoted_count  int NOT NULL DEFAULT 0,
    created_by_user_id uuid,
    created_at      timestamptz NOT NULL DEFAULT now(),
    archived_at     timestamptz
);

CREATE INDEX IF NOT EXISTS idx_cold_lists_tenant
    ON public.cold_lead_lists(tenant_id, created_at DESC)
    WHERE archived_at IS NULL;

CREATE TABLE IF NOT EXISTS public.cold_leads (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    list_id         uuid NOT NULL REFERENCES public.cold_lead_lists(id) ON DELETE CASCADE,
    business_name   text,
    contact_name    text,
    phone           text,
    email           text,
    raw             jsonb DEFAULT '{}'::jsonb,           -- original CSV row
    stage           text NOT NULL DEFAULT 'imported',    -- chevron stages: imported | contacted | replied | qualified | promoted | dead
    promoted_lead_id uuid,                                -- set when operator promotes to warm pipeline
    last_contacted_at timestamptz,
    attempt_count   int NOT NULL DEFAULT 0,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cold_leads_tenant_list_stage
    ON public.cold_leads(tenant_id, list_id, stage);

CREATE INDEX IF NOT EXISTS idx_cold_leads_promoted
    ON public.cold_leads(tenant_id, promoted_lead_id)
    WHERE promoted_lead_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cold_leads_dedup
    ON public.cold_leads(tenant_id, list_id, COALESCE(LOWER(email), ''), COALESCE(phone, ''));

COMMENT ON TABLE public.cold_lead_lists IS
    '069 — cold list holding pen. Import lands here, NOT tenant_records, until explicit promotion.';

COMMENT ON TABLE public.cold_leads IS
    '069 — members of a cold list. Six stages (imported/contacted/replied/qualified/promoted/dead) render in the Arcadian chevron rail mirror of Lead Pipeline.';

-- ============================================================================
-- cold_outreach_campaigns + cold_outreach_recipients — campaign blast
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.cold_outreach_campaigns (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    name            text NOT NULL,
    channel         text NOT NULL,                       -- 'sms_twilio' | 'sms_texttorrent' | 'email'
    message_body    text NOT NULL,                       -- template; supports {{first_name}}, {{business_name}}
    subject         text,                                -- email only
    cold_list_id    uuid REFERENCES public.cold_lead_lists(id),
    recipient_filter jsonb DEFAULT '{}'::jsonb,         -- {stage: 'imported', max_attempts: 3, ...}
    status          text NOT NULL DEFAULT 'draft',       -- 'draft' | 'queued' | 'sending' | 'complete' | 'cancelled' | 'error'
    scheduled_for   timestamptz,
    started_at      timestamptz,
    completed_at    timestamptz,
    total_recipients int NOT NULL DEFAULT 0,
    sent_count      int NOT NULL DEFAULT 0,
    failed_count    int NOT NULL DEFAULT 0,
    daily_cap       int NOT NULL DEFAULT 500,            -- respect ESP/carrier limits
    created_by_user_id uuid,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outreach_campaigns_tenant_status
    ON public.cold_outreach_campaigns(tenant_id, status, scheduled_for)
    WHERE status IN ('queued', 'sending');

CREATE TABLE IF NOT EXISTS public.cold_outreach_recipients (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    campaign_id     uuid NOT NULL REFERENCES public.cold_outreach_campaigns(id) ON DELETE CASCADE,
    cold_lead_id    uuid REFERENCES public.cold_leads(id) ON DELETE SET NULL,
    lead_id         uuid,                                -- if recipient came from warm pipeline
    contact_address text NOT NULL,                       -- email or phone
    status          text NOT NULL DEFAULT 'pending',     -- 'pending' | 'sending' | 'sent' | 'delivered' | 'failed' | 'unsubscribed' | 'replied'
    sent_at         timestamptz,
    delivery_status_at timestamptz,
    last_error      text,
    interaction_id  text,                                -- lead_interactions.id from send_gateway
    response_at     timestamptz,
    response_summary text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outreach_recipients_campaign_status
    ON public.cold_outreach_recipients(campaign_id, status, sent_at);

CREATE INDEX IF NOT EXISTS idx_outreach_recipients_tenant_pending
    ON public.cold_outreach_recipients(tenant_id, status)
    WHERE status = 'pending';

COMMENT ON TABLE public.cold_outreach_campaigns IS
    '069 — cold-outreach blast campaigns. Drained by scripts/cold_outreach_runner.py via send_gateway; respects daily_cap + CASL automatically.';

-- ============================================================================
-- shop_out_warnings — severity + override-note log (Proceed Anyway)
-- ============================================================================
-- Shopping Out is changing from hard-block to warn-with-override.
-- Each detected mismatch becomes a row; if the operator hits Proceed Anyway,
-- override_note + overridden_by populated. Pending rows (no override) just
-- mean the operator dismissed/cancelled the send.
CREATE TABLE IF NOT EXISTS public.shop_out_warnings (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    application_id  uuid NOT NULL,
    lender_id       uuid NOT NULL,
    severity        text NOT NULL,                       -- 'info' | 'warning' | 'high_risk'
    reason_code     text NOT NULL,                       -- 'below_min_revenue' | 'product_mismatch' | 'fico_floor' | ...
    reason_detail   text NOT NULL,                       -- one-line human-readable
    detected_at     timestamptz NOT NULL DEFAULT now(),
    overridden      boolean NOT NULL DEFAULT false,
    override_note   text,
    overridden_by_user_id uuid,
    overridden_at   timestamptz,
    thread_id       uuid,                                -- set if send proceeded
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shop_warnings_tenant_app
    ON public.shop_out_warnings(tenant_id, application_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_shop_warnings_overridden
    ON public.shop_out_warnings(tenant_id, overridden, severity)
    WHERE overridden = true;

COMMENT ON TABLE public.shop_out_warnings IS
    '069 — Shopping Out severity-tier warnings + override audit. Replaces the prior hard-block behaviour per the 2026-05-25 meeting.';

-- ============================================================================
-- known_funding_companies — MCA registry (extract from hardcoded list)
-- ============================================================================
-- statement_parser.py currently hardcodes Forward Financing, OnDeck, Velocity,
-- Kapitus, Yellowstone, etc. Lift to a queryable, admin-updatable table so
-- adding a new lender doesn't require code edit + redeploy.
CREATE TABLE IF NOT EXISTS public.known_funding_companies (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL UNIQUE,
    aliases         text[] DEFAULT ARRAY[]::text[],
    website         text,
    industry_signal_keywords text[] DEFAULT ARRAY[]::text[],  -- search in bank statement memos
    typical_term_days int,
    typical_buy_rate_min numeric(5,2),
    typical_buy_rate_max numeric(5,2),
    category        text,                                -- 'mca' | 'loc' | 'term_loan'
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_known_funding_active
    ON public.known_funding_companies(active, name)
    WHERE active = true;

-- Seed the registry with the previously-hardcoded list (idempotent inserts).
INSERT INTO public.known_funding_companies (name, aliases, industry_signal_keywords, category) VALUES
    ('Forward Financing', ARRAY['Forward Fin'], ARRAY['FWD FIN', 'FORWARD FINANCING'], 'mca'),
    ('OnDeck', ARRAY['On Deck Capital'], ARRAY['ONDECK', 'ON DECK'], 'mca'),
    ('Velocity', ARRAY['Velocity Capital'], ARRAY['VELOCITY CAP', 'VELOCITY CAPITAL'], 'mca'),
    ('Kapitus', ARRAY['Strategic Funding Source'], ARRAY['KAPITUS', 'SFS CAPITAL'], 'mca'),
    ('Yellowstone Capital', ARRAY['Yellowstone'], ARRAY['YELLOWSTONE', 'YS CAP'], 'mca'),
    ('Mantis Funding', ARRAY['Mantis'], ARRAY['MANTIS FUNDING'], 'mca'),
    ('Rapid Capital Funding', ARRAY['RCF'], ARRAY['RAPID CAP', 'RCF FUNDING'], 'mca'),
    ('BlueVine', ARRAY['Blue Vine'], ARRAY['BLUEVINE', 'BLUE VINE'], 'loc'),
    ('Kabbage', NULL, ARRAY['KABBAGE'], 'loc'),
    ('Funding Circle', NULL, ARRAY['FUNDING CIRCLE'], 'term_loan'),
    ('CAN Capital', ARRAY['CAN Cap'], ARRAY['CAN CAPITAL', 'CAN CAP'], 'mca'),
    ('Square Capital', ARRAY['Square Loans'], ARRAY['SQUARE CAP', 'SQ CAPITAL'], 'mca'),
    ('Stripe Capital', NULL, ARRAY['STRIPE CAP', 'STRIPE CAPITAL'], 'mca'),
    ('PayPal Working Capital', ARRAY['PayPal WC'], ARRAY['PAYPAL WC', 'PAYPAL WORKING'], 'mca'),
    ('Credibly', NULL, ARRAY['CREDIBLY'], 'mca'),
    ('Fundbox', NULL, ARRAY['FUNDBOX'], 'loc'),
    ('National Funding', NULL, ARRAY['NATIONAL FUNDING'], 'mca'),
    ('Reliant Funding', NULL, ARRAY['RELIANT FUNDING'], 'mca')
ON CONFLICT (name) DO NOTHING;

COMMENT ON TABLE public.known_funding_companies IS
    '069 — MCA/loan-shop registry. statement_parser.py loads this at boot to detect existing positions from bank statement memos.';

-- ============================================================================
-- offer_sources — attribution per offer record
-- ============================================================================
-- An offer can come from an email scan, a portal extract, or manual entry.
-- This table answers "where did this number come from?" for audit + debugging.
CREATE TABLE IF NOT EXISTS public.offer_sources (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    offer_record_id uuid NOT NULL,                       -- tenant_records.id where entity_type='offer'
    source_type     text NOT NULL,                       -- 'email_scan' | 'portal_extract' | 'manual_entry'
    source_email_id text,                                -- gmail message ID if email_scan
    source_portal_url text,                              -- lender portal URL if portal_extract
    source_user_id  uuid,                                -- operator who manually entered
    extracted_at    timestamptz NOT NULL DEFAULT now(),
    extraction_confidence numeric(4,3),                  -- 0.000-1.000 from the extractor
    raw_extraction  jsonb,                                -- pre-normalization extractor output
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_offer_sources_tenant_offer
    ON public.offer_sources(tenant_id, offer_record_id);

CREATE INDEX IF NOT EXISTS idx_offer_sources_email
    ON public.offer_sources(source_email_id)
    WHERE source_email_id IS NOT NULL;

-- ============================================================================
-- email_thread_monitors — email-scanner cursor state per tenant
-- ============================================================================
-- The Email Offer Scanner daemon polls Gmail per tenant. This table holds
-- the cursor (last_message_id) + last_checked_at so restarts don't double-scan.
CREATE TABLE IF NOT EXISTS public.email_thread_monitors (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    monitor_kind    text NOT NULL,                       -- 'lender_offers' | 'lender_responses' | 'funding_confirmations'
    gmail_label     text NOT NULL,                       -- the label/query the daemon polls
    last_checked_at timestamptz,
    last_message_id text,                                -- gmail message ID cursor
    next_check_at   timestamptz NOT NULL DEFAULT now(),
    status          text NOT NULL DEFAULT 'active',      -- 'active' | 'paused' | 'error'
    last_error      text,
    messages_seen   int NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_monitors_tenant_kind
    ON public.email_thread_monitors(tenant_id, monitor_kind);

CREATE INDEX IF NOT EXISTS idx_email_monitors_due
    ON public.email_thread_monitors(status, next_check_at)
    WHERE status = 'active';

-- ============================================================================
-- lender_feedback — intelligence learning tuples
-- ============================================================================
-- Every shop-out outcome (approved / declined / no_response) becomes a row.
-- The lender recommender reads this to bias future suggestions toward
-- lenders who approve deals of similar shape (industry × revenue × FICO).
CREATE TABLE IF NOT EXISTS public.lender_feedback (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    lender_id       uuid NOT NULL,                       -- tenant_records.id where entity_type='lender'
    application_id  uuid NOT NULL,
    thread_id       uuid,                                -- application_lender_threads.id
    outcome         text NOT NULL,                       -- 'approved' | 'declined' | 'info_requested' | 'no_response'
    industry        text,                                -- application snapshot fields below
    monthly_revenue numeric(14,2),
    time_in_business_months int,
    fico            int,
    requested_amount numeric(14,2),
    funded_amount   numeric(14,2),
    funded_term_days int,
    funded_buy_rate numeric(5,2),
    decline_reason  text,
    extracted_at    timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lender_feedback_tenant_lender_outcome
    ON public.lender_feedback(tenant_id, lender_id, outcome, extracted_at DESC);

CREATE INDEX IF NOT EXISTS idx_lender_feedback_industry
    ON public.lender_feedback(tenant_id, industry, outcome)
    WHERE industry IS NOT NULL;

COMMENT ON TABLE public.lender_feedback IS
    '069 — every shop-out outcome captured as a learning tuple. Read by the lender recommender for bias-toward-approval scoring.';

-- ============================================================================
-- personalized_form_links — token-backed per-lead form links
-- ============================================================================
-- Existing HMAC-based stateless tokens (lib/form-links.ts) work, but we need
-- visibility into "did this token get opened/submitted" without grepping logs.
-- This table is the visibility layer; the HMAC remains the auth mechanism.
CREATE TABLE IF NOT EXISTS public.personalized_form_links (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    lead_id         uuid NOT NULL,
    form_id         uuid NOT NULL,
    form_step       int NOT NULL DEFAULT 1,              -- 1 | 2 | 3 for the SunBiz three-step funnel
    token           text NOT NULL UNIQUE,                -- HMAC-signed; matches what /f/<tenant>/<form>/<token> verifies
    sent_via        text,                                -- 'email' | 'sms' | 'manual_share' | 'drip'
    sent_at         timestamptz,
    expires_at      timestamptz NOT NULL,
    first_opened_at timestamptz,
    last_opened_at  timestamptz,
    open_count      int NOT NULL DEFAULT 0,
    submitted_at    timestamptz,
    submission_id   uuid,                                -- form_submissions.id once submitted
    revoked_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_form_links_lead
    ON public.personalized_form_links(tenant_id, lead_id, form_id, form_step, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_form_links_unsubmitted
    ON public.personalized_form_links(tenant_id, expires_at)
    WHERE submitted_at IS NULL AND revoked_at IS NULL;

COMMENT ON TABLE public.personalized_form_links IS
    '069 — per-lead form link visibility. HMAC token is still the auth check; this table answers "did the link get opened, when, and by whom".';

-- ============================================================================
-- agent_memory_notes — tenant/lead-scoped operator notes
-- ============================================================================
-- Free-text notes that aren't part of the structured lead profile. Used by
-- the Daily Plan / Calls flow for "voicemail left, asked for callback Tue".
CREATE TABLE IF NOT EXISTS public.agent_memory_notes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL,
    entity_type     text NOT NULL,                       -- 'lead' | 'application' | 'lender' | 'tenant'
    entity_id       uuid,                                -- nullable for tenant-scoped notes
    note_text       text NOT NULL,
    author_user_id  uuid,
    author_kind     text NOT NULL DEFAULT 'operator',    -- 'operator' | 'agent' | 'system'
    tags            text[] DEFAULT ARRAY[]::text[],
    pinned          boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_notes_tenant_entity
    ON public.agent_memory_notes(tenant_id, entity_type, entity_id, created_at DESC)
    WHERE entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_notes_pinned
    ON public.agent_memory_notes(tenant_id, pinned, created_at DESC)
    WHERE pinned = true;

-- ============================================================================
-- application_lender_threads — add owner_phone, severity_warnings_acknowledged
-- ============================================================================
-- shop_out_sender.py needs to substitute the assigned-rep's phone into the
-- outbound template. Cleaner to store the resolved phone on the thread than
-- re-resolve at send time (operator may reassign the rep between queue + send).
ALTER TABLE public.application_lender_threads
    ADD COLUMN IF NOT EXISTS owner_phone text;

ALTER TABLE public.application_lender_threads
    ADD COLUMN IF NOT EXISTS warnings_acknowledged jsonb DEFAULT '[]'::jsonb;
-- warnings_acknowledged = [{ warning_id, severity, override_note, overridden_at }, ...]
-- Stores the snapshot of which warnings the operator chose to override; the
-- shop_out_warnings table is the canonical record, this is the per-thread mirror.

COMMENT ON COLUMN public.application_lender_threads.owner_phone IS
    '069 — assigned-rep phone snapshot, substituted into template at send time. Resolves owner phone at queue time, not send time, so rep reassignment after queue doesn''t silently change the outbound.';

-- ============================================================================
-- tenant_records — add assigned_rep convention (no DDL needed; documented here)
-- ============================================================================
-- Applications now optionally carry data.assigned_rep_user_id +
-- data.assigned_rep_phone in their JSONB blob. Shopping Out reads these
-- when queueing threads. No schema change — JSONB is open.

-- ============================================================================
-- tenant_manifests.settings — document expected new keys (no DDL)
-- ============================================================================
-- Optional manifest.settings keys consumed by the new daemons:
--   renewal_eligibility_threshold_pct (int 1-99, default 40)  [already in use]
--   daily_plan_generation_time_local  (HH:MM, default '06:00')
--   follow_up_generation_time_local   (HH:MM, default '06:30')
--   cold_outreach_daily_cap           (int, default 500)
--   underwriting_auto_trigger         (bool, default true)
--   shop_out_severity_blocking        (bool, default false)
-- All read with sensible defaults so absence doesn't break anything.

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT table_name FROM information_schema.tables
--     WHERE table_schema = 'public'
--       AND table_name IN (
--         'application_underwriting', 'follow_up_tasks', 'daily_plan_items',
--         'cold_lead_lists', 'cold_leads',
--         'cold_outreach_campaigns', 'cold_outreach_recipients',
--         'shop_out_warnings', 'known_funding_companies',
--         'offer_sources', 'email_thread_monitors',
--         'lender_feedback', 'personalized_form_links', 'agent_memory_notes'
--       )
--    ORDER BY table_name;
--   -- expect 14 rows
--
--   SELECT count(*) FROM public.known_funding_companies WHERE active = true;
--   -- expect ≥ 18
-- ============================================================================
