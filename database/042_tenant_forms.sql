-- Migration 042 — Tenant-defined forms + submissions (JotForm replacement)
--
-- Phase 3 of the SunBiz CRM build (2026-05-15). Replaces the JotForm
-- 3rd-party intake with first-party forms that operators design in the
-- dashboard. Personalized per-lead links (HMAC-signed via
-- lib/form-links.ts) drop the prospect into a branded multi-step funnel.
-- Submissions trigger lead.stage transitions and feed the Phase 4 drip
-- engine via the BRAVO_RECORD_STATUS_CHANGED event publisher already
-- wired in Phase 2.
--
-- Architecture:
--
--   Dashboard CRUD     →  forms             ← /f/<slug>/<form_slug>/<lead_token>
--   /api/forms/*          (definitions)        public form page renderer
--                                                       │
--                                                       ▼
--   Phase 2 status     ←  form_submissions  ← /api/forms/submit
--   change publisher      (one row per
--                          step completion)
--
-- JotForm fade-out: existing JotForm webhook stays running in parallel
-- through Phase 4 so SunBiz operations don't lose intake during cutover.
-- Cut on the day after the drip engine ships per the plan's open
-- decision #1.
--
-- Apply via: python scripts/apply_migration.py database/042_tenant_forms.sql

BEGIN;

-- ============================================================================
-- forms — operator-designed form definitions, per tenant
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.forms (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- URL-safe slug, unique per tenant. Used in /f/<tenant>/<form_slug>/<token>.
    slug          text NOT NULL,
    -- Operator-given name. Free text, shown in /forms list + form builder.
    name          text NOT NULL,
    description   text,
    -- Branding overlay — primary color, accent color, logo, header copy.
    -- JSONB so SunBiz can theme separately from SUGA without a schema
    -- change. Shape validated at the app layer (lib/forms/types.ts).
    branding      jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Steps array — each step has its own fields[]. Multi-step funnels
    -- (basic info -> app -> bank statements) are first-class. Single-step
    -- forms just have one element.
    --
    -- Shape:
    --   [
    --     {
    --       "key": "basic",
    --       "title": "Tell us about your business",
    --       "fields": [
    --         { "name": "business_name", "type": "text", "required": true },
    --         { "name": "monthly_revenue", "type": "currency", "required": true },
    --         ...
    --       ]
    --     },
    --     ...
    --   ]
    --
    -- Field types: text, email, phone, currency, number, textarea, select,
    -- multiselect, date, signature, file_upload, hidden, rating.
    steps         jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- When set, form submission transitions the source lead to this
    -- stage (e.g. signed_application). Phase 2's publisher then fires
    -- BRAVO_RECORD_STATUS_CHANGED which the Phase 4 drip engine consumes.
    -- One per step possible — `step_outcomes` jsonb on submission tracks
    -- per-step stage targets if the operator wants progressive transitions.
    on_complete_stage text,
    -- Per-step stage transitions. Example:
    --   { "0": "sent_application",
    --     "1": "signed_application",
    --     "2": "submitted" }
    -- Indexed by step_index (string keys because jsonb).
    step_outcomes jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Toggle without delete. Public form page renders 404 when disabled.
    enabled       boolean NOT NULL DEFAULT true,
    -- Optional redirect target after final-step submission. NULL → render
    -- the form's built-in "Thanks" screen.
    redirect_url  text,
    -- Who created it (audit). Edits don't update this; updated_at + the
    -- agent_events audit trail track edits.
    created_by    uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_forms_tenant_enabled
    ON public.forms (tenant_id, enabled)
    WHERE enabled = true;

CREATE TRIGGER trg_forms_updated_at
    BEFORE UPDATE ON public.forms
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

-- ============================================================================
-- form_submissions — one row per step completion (so partial fills persist)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.form_submissions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id         uuid NOT NULL REFERENCES public.forms(id) ON DELETE CASCADE,
    -- Denormalized for RLS — every form_submission filter starts with
    -- tenant_id so the policy can match cheaply without joining forms.
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- The lead this submission ties back to. Stored as text (not FK)
    -- because tenant_records is a JSONB wide-row table — there's no
    -- referential integrity at the DB layer. The HMAC-signed lead_token
    -- in the URL is the auth boundary; we trust it after verify.
    lead_id         text NOT NULL,
    -- Zero-indexed step number within the form's steps[]. Multi-step
    -- funnels generate one row per step so a partial fill leaves a
    -- breadcrumb the operator can see on /leads.
    step_index      integer NOT NULL DEFAULT 0,
    -- The actual submitted values. Map of field-name -> value.
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- File uploads metadata (the actual blobs live in Supabase Storage
    -- or on the operator's machine via the bridge — see lib/forms/uploads.ts).
    -- Shape: [{ field_name, storage_path, mime_type, size_bytes }]
    file_attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
    ip_address      inet,
    user_agent      text,
    submitted_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_form_submissions_form
    ON public.form_submissions (form_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_form_submissions_lead
    ON public.form_submissions (tenant_id, lead_id, submitted_at DESC);

-- ============================================================================
-- form_views — page-load telemetry for the "viewed_application" stage trigger
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.form_views (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    form_id         uuid NOT NULL REFERENCES public.forms(id) ON DELETE CASCADE,
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    lead_id         text NOT NULL,
    ip_address      inet,
    user_agent      text,
    viewed_at       timestamptz NOT NULL DEFAULT now()
);

-- Used by /api/forms/view to check "have we recorded a view in the last
-- hour?" before re-firing the BRAVO_LEAD_LINK_VIEWED event. Prevents
-- a page refresh from triggering the drip 50 times.
CREATE INDEX IF NOT EXISTS idx_form_views_lead_recent
    ON public.form_views (tenant_id, lead_id, viewed_at DESC);

-- ============================================================================
-- RLS — operators see/edit only their tenant's forms + submissions + views
-- ============================================================================
ALTER TABLE public.forms ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.form_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.form_views ENABLE ROW LEVEL SECURITY;

CREATE POLICY forms_tenant_all ON public.forms
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY form_submissions_tenant_read ON public.form_submissions
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- Note: /api/forms/submit + /api/forms/view use the service-role client
-- to insert (HMAC token is the auth boundary, not a session cookie), so
-- those writes bypass RLS by design. No INSERT policy needed for the
-- public path. Operators reading their own tenant's submissions still
-- goes through RLS via the SELECT policy above.

CREATE POLICY form_views_tenant_read ON public.form_views
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMENT ON TABLE public.forms IS
  'Tenant-designed forms — JotForm replacement. Personalized per-lead '
  'URLs land prospects on /f/<tenant_slug>/<form_slug>/<lead_token>.';

COMMENT ON TABLE public.form_submissions IS
  'One row per form step completion. Multi-step funnels generate '
  'multiple rows per lead. Submissions transition lead.stage per the '
  'form''s step_outcomes map; the Phase 2 publisher fires drip events.';

COMMENT ON TABLE public.form_views IS
  'Page-load telemetry. /api/forms/view inserts on first viewing of a '
  'personalized link, transitioning lead.stage to viewed_application. '
  'Rate-limited at the route layer to one event per (lead, hour).';

COMMIT;
