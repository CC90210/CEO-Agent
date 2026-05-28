-- ============================================================================
-- Migration 066 — merchant_summary view
--
-- This is the JSONB-to-wide-row translation layer between OASIS's
-- tenant_records substrate and Adon Yess's SunBiz Pipeline frontend
-- bundle. Per cc-pipeline-handoff.md §1, every column Adon's UI expects
-- is projected out of the underlying JSONB data so the frontend can bind
-- without learning anything about tenant_records.
--
-- Source rows: tenant_records WHERE entity_type='lead'.
-- LEFT JOIN: most-recent application via data->>'lead_id'.
-- LEFT JOIN: application_lender_threads aggregations.
--
-- One row per merchant. Renewal applications (multiple per merchant)
-- collapse — we surface the most-recent NON-TERMINAL deal_stage if one
-- exists, else the most-recent overall.
--
-- Defensive on field names: every JSONB extraction goes through COALESCE
-- across the known variant names so the view doesn't break if the
-- producer (frontend, JotForm intake, tt-agent) writes a slightly
-- different key. If a field has no known source, the column is NULL —
-- which the frontend renders as "—" via the existing nonEmptyString
-- helper.
--
-- ADR reference: 0007-merchant-summary-as-translation-layer.md (drafted
-- in Phase 3 of the integration plan).
--
-- This migration is APPLIED-VIA-SCRIPT — contains no UPDATE/DELETE, only
-- CREATE OR REPLACE VIEW. Run via:
--   python scripts/apply_migration.py database/066_merchant_summary_view.sql
-- ============================================================================

BEGIN;

-- security_invoker=true makes the view evaluate RLS using the CALLING
-- user's privileges instead of the view owner's. Without this, Supabase
-- views default to security_definer-like semantics where the view runs
-- as its owner (postgres) and bypasses tenant_records' RLS policies —
-- so a logged-in user from tenant A could SELECT merchant_summary and
-- receive tenant B's data. Codex P1 finding 2026-05-28.
-- Requires Postgres 15+ which Supabase provides on all current projects.
CREATE OR REPLACE VIEW public.merchant_summary
  WITH (security_invoker = true)
AS
WITH
-- ------------------------------------------------------------------------
-- 1. Most-recent application per lead.
--    "Most recent" = highest priority (active deal_stages over terminal)
--    + most recent updated_at within the priority bucket.
-- ------------------------------------------------------------------------
ranked_apps AS (
  SELECT
    a.id AS application_id,
    a.tenant_id,
    a.data->>'lead_id' AS lead_id_str,
    a.data,
    a.created_at AS app_created_at,
    a.updated_at AS app_updated_at,
    ROW_NUMBER() OVER (
      PARTITION BY a.tenant_id, a.data->>'lead_id'
      ORDER BY
        CASE a.data->>'deal_stage'
          WHEN 'Application In' THEN 1
          WHEN 'Missing Info'   THEN 1
          WHEN 'Shopping'       THEN 1
          WHEN 'Funded'         THEN 2
          WHEN 'Declined'       THEN 3
          WHEN 'Dead'           THEN 3
          ELSE 4
        END,
        a.updated_at DESC
    ) AS rk
  FROM public.tenant_records a
  WHERE a.entity_type = 'application'
    AND a.data->>'lead_id' IS NOT NULL
),
primary_app AS (
  SELECT * FROM ranked_apps WHERE rk = 1
),
-- ------------------------------------------------------------------------
-- 2. Lender-thread aggregates per application.
--    Approved-count > 0 is what derives Adon's "Approved" deal_stage,
--    surfaced as a synthetic value in the SELECT below.
-- ------------------------------------------------------------------------
thread_counts AS (
  SELECT
    application_id,
    COUNT(*) FILTER (WHERE status = 'sent')           AS shop_sent_count,
    COUNT(*) FILTER (WHERE status = 'responded')      AS shop_replied_count,
    COUNT(*) FILTER (WHERE status = 'approved')       AS shop_offer_count,
    COUNT(*) FILTER (WHERE status = 'declined')       AS shop_declined_count,
    COUNT(*) FILTER (WHERE status = 'pending')        AS shop_pending_count,
    COUNT(*) FILTER (WHERE status = 'info_requested') AS shop_info_requested_count,
    COUNT(*) FILTER (WHERE status = 'no_response')    AS shop_no_response_count,
    MAX(last_response_at) AS last_lender_response_at
  FROM public.application_lender_threads
  GROUP BY application_id
)
SELECT
  -- =====================================================================
  -- IDENTITY (Adon §1 first block)
  -- =====================================================================
  l.id                                                  AS merchant_id,
  l.tenant_id                                           AS tenant_id,
  COALESCE(
    NULLIF(l.data->>'dba', ''),
    NULLIF(l.data->>'business_name', ''),
    NULLIF(l.data->>'company', ''),
    NULLIF(l.data->>'name', '')
  )                                                     AS dba,
  COALESCE(
    NULLIF(l.data->>'legal_name', ''),
    NULLIF(l.data->>'business_name', ''),
    NULLIF(l.data->>'company', '')
  )                                                     AS legal_name,
  NULLIF(l.data->>'state', '')                          AS state,
  NULLIF(l.data->>'city', '')                           AS city,
  COALESCE(
    NULLIF(l.data->>'phone', ''),
    NULLIF(l.data->'phones'->>0, '')
  )                                                     AS phone,
  NULLIF(l.data->>'email', '')                          AS email,
  NULLIF(l.data->>'industry', '')                       AS industry,
  NULLIF(l.data->>'ein', '')                            AS ein,
  NULLIF(l.data->>'time_in_business_years', '')::NUMERIC          AS tib_years,

  -- =====================================================================
  -- OWNER (Adon §1 second block)
  -- Today JARVIS owns this data via mca_analyses; OASIS only has it if
  -- the operator manually copies it back. So these columns are usually
  -- NULL until Phase 2's `callUnderwriting` populates them — at which
  -- point they get written back to l.data.owner.* by the proxy.
  -- =====================================================================
  COALESCE(
    NULLIF(l.data->'owner'->>'full_name', ''),
    NULLIF(l.data->>'owner_name', ''),
    NULLIF(l.data->>'first_name', '') || ' ' || NULLIF(l.data->>'last_name', '')
  )                                                     AS owner_name,
  NULLIF(l.data->'owner'->>'title', '')                 AS owner_title,
  NULLIF(l.data->'owner'->>'ownership_pct', '')::NUMERIC          AS ownership_pct,
  NULLIF(l.data->'owner'->>'date_of_birth', '')         AS owner_dob,
  NULLIF(l.data->'owner'->>'citizenship', '')           AS owner_citizenship,
  -- SSN: server NEVER projects the full SSN — only last 4. If the data
  -- somehow has a full SSN stored, RIGHT() truncates safely.
  CASE
    WHEN l.data->'owner' ? 'ssn_last4'
      THEN l.data->'owner'->>'ssn_last4'
    WHEN l.data->'owner' ? 'ssn'
      THEN RIGHT(l.data->'owner'->>'ssn', 4)
    ELSE NULL
  END                                                   AS ssn_last4,
  NULLIF(l.data->'owner'->>'credit_score', '')::INT               AS credit_score,

  -- =====================================================================
  -- ADDRESSES (physical + home)
  -- =====================================================================
  NULLIF(l.data->'physical_address'->>'line1', '')      AS physical_line1,
  NULLIF(l.data->'physical_address'->>'line2', '')      AS physical_line2,
  NULLIF(l.data->'physical_address'->>'city', '')       AS physical_city,
  NULLIF(l.data->'physical_address'->>'state', '')      AS physical_state,
  NULLIF(l.data->'physical_address'->>'zip', '')        AS physical_zip,
  NULLIF(l.data->'physical_address'->>'years_at', '')::NUMERIC    AS physical_years_at,
  NULLIF(l.data->'home_address'->>'line1', '')          AS home_line1,
  NULLIF(l.data->'home_address'->>'city', '')           AS home_city,
  NULLIF(l.data->'home_address'->>'state', '')          AS home_state,
  NULLIF(l.data->'home_address'->>'zip', '')            AS home_zip,
  NULLIF(l.data->'home_address'->>'years_at', '')::NUMERIC        AS home_years_at,

  -- =====================================================================
  -- AGENT (assignee)
  -- =====================================================================
  COALESCE(
    up.display_name,
    up.full_name,
    NULLIF(l.data->>'agent', ''),
    NULLIF(l.data->>'assigned_to', '')
  )                                                     AS agent,
  -- Initials: use the existing initialsOf logic inline (first letter of
  -- first + last word of display_name).
  CASE
    WHEN up.display_name IS NOT NULL THEN
      UPPER(LEFT(SPLIT_PART(up.display_name, ' ', 1), 1) ||
            LEFT(SPLIT_PART(up.display_name, ' ', GREATEST(2, ARRAY_LENGTH(STRING_TO_ARRAY(up.display_name, ' '), 1))), 1))
    ELSE NULL
  END                                                   AS agent_initials,
  -- Avatar color: deterministic hash-based palette pick. Matches the
  -- frontend's existing helper.
  CASE (HASHTEXT(COALESCE(up.id::text, l.data->>'assigned_user_id', 'unknown')) % 6 + 6) % 6
    WHEN 0 THEN '#C0842F'  -- amber
    WHEN 1 THEN '#2E8392'  -- teal
    WHEN 2 THEN '#7057A7'  -- purple
    WHEN 3 THEN '#32876B'  -- green
    WHEN 4 THEN '#3978BE'  -- blue
    WHEN 5 THEN '#9B3D45'  -- red
  END                                                   AS agent_color,

  -- =====================================================================
  -- TWO-TIER STAGE MODEL (ADR-0006)
  -- =====================================================================
  COALESCE(
    NULLIF(l.data->>'merchant_stage', ''),
    'Lead'  -- safe default for records missing migration 065 stamp
  )                                                     AS merchant_stage,
  -- "Approved" is synthesized: any lender thread is approved AND the
  -- application hasn't transitioned to Funded/Declined/Dead yet.
  CASE
    WHEN COALESCE(tc.shop_offer_count, 0) > 0
         AND COALESCE(pa.data->>'deal_stage', '') NOT IN ('Funded', 'Declined', 'Dead')
      THEN 'Approved'
    ELSE NULLIF(pa.data->>'deal_stage', '')
  END                                                   AS deal_stage,

  -- days_in_stage: time since the latest stage transition. We don't
  -- store stage_entered_at yet (Phase 4 task) — fall back to
  -- updated_at as a proxy.
  GREATEST(
    0,
    EXTRACT(
      DAY FROM NOW() - COALESCE(
        NULLIF(pa.data->>'stage_entered_at', '')::TIMESTAMPTZ,
        pa.app_updated_at,
        l.updated_at
      )
    )::INT
  )                                                     AS days_in_stage,

  -- sla_overdue_days: positive when over the SLA window for the current
  -- deal_stage. Mirrors lib/sunbiz-sla.ts STAGE_SLA_DAYS map (post-7-stage).
  GREATEST(
    0,
    EXTRACT(
      DAY FROM NOW() - COALESCE(pa.app_updated_at, l.updated_at)
    )::INT - CASE pa.data->>'deal_stage'
              WHEN 'Application In' THEN 1
              WHEN 'Missing Info'   THEN 2
              WHEN 'Shopping'       THEN 3
              WHEN 'Funded'         THEN 999  -- not overdue
              WHEN 'Declined'       THEN 999
              WHEN 'Dead'           THEN 999
              ELSE 7
            END
  )                                                     AS sla_overdue_days,

  -- =====================================================================
  -- RISK FLAGS
  -- These derive from JARVIS-owned signals today. Until Phase 2's
  -- jarvis-client lands and writes them back to l.data.*, they default
  -- to FALSE. Frontend code should treat these as best-effort hints,
  -- NOT authoritative — JARVIS underwriting brief is the source of truth.
  -- =====================================================================
  COALESCE(NULLIF(l.data->>'is_hot', '')::BOOLEAN, FALSE)         AS is_hot,
  COALESCE(NULLIF(l.data->>'is_shopped_stale', '')::BOOLEAN, FALSE) AS is_shopped_stale,
  -- Cold = no inbound conversation in 48h. Derives from last_inbound_at
  -- if present, else last_touch_at, else FALSE.
  COALESCE(
    NULLIF(l.data->>'last_inbound_at', '')::TIMESTAMPTZ
      < NOW() - INTERVAL '48 hours',
    FALSE
  )                                                     AS is_cold,
  -- Renewal candidate: merchant_stage=Funded AND term_pct_used > 60%
  -- (JARVIS computes term_pct_used; default null = not eligible).
  (
    COALESCE(l.data->>'merchant_stage', '') = 'Funded'
    AND COALESCE(NULLIF(pa.data->>'term_pct_used', '')::NUMERIC, 0) > 0.60
  )                                                     AS is_renewal_candidate,
  -- High leverage: paper_grade='D' or leverage_ratio > 70%
  (
    COALESCE(pa.data->>'paper_grade', '') = 'D'
    OR COALESCE(NULLIF(pa.data->>'leverage_ratio', '')::NUMERIC, 0) > 0.70
  )                                                     AS is_high_leverage,

  -- =====================================================================
  -- DEAL ECONOMICS (mostly populated by JARVIS underwriting)
  -- =====================================================================
  NULLIF(pa.data->>'paper_grade', '')                   AS paper_grade,
  NULLIF(pa.data->>'leverage_ratio', '')::NUMERIC                 AS leverage_ratio,
  NULLIF(pa.data->>'avg_monthly_revenue', '')::NUMERIC            AS avg_monthly_revenue,
  NULLIF(pa.data->>'nsf_avg_per_month', '')::NUMERIC              AS nsf_avg_per_month,
  COALESCE(NULLIF(pa.data->>'position_count', '')::INT, 0)        AS position_count,
  NULLIF(pa.data->>'requested_amount', '')::NUMERIC               AS funding_potential_usd,
  NULLIF(pa.data->>'current_funded_amount', '')::NUMERIC         AS current_funded_amount,
  NULLIF(pa.data->>'submitted_at', '')::TIMESTAMPTZ               AS submitted_at,
  COALESCE(
    NULLIF(l.data->>'last_touch_at', '')::TIMESTAMPTZ,
    l.updated_at
  )                                                     AS last_touch_at,
  NULLIF(l.data->>'last_sms_at', '')::TIMESTAMPTZ                 AS last_sms_at,
  NULLIF(l.data->>'last_email_at', '')::TIMESTAMPTZ               AS last_email_at,

  -- =====================================================================
  -- LENDER SHOP COUNTS (from application_lender_threads)
  -- =====================================================================
  COALESCE(tc.shop_sent_count, 0)                       AS shop_sent_count,
  COALESCE(tc.shop_replied_count, 0)                    AS shop_replied_count,
  COALESCE(tc.shop_offer_count, 0)                      AS shop_offer_count,
  COALESCE(tc.shop_declined_count, 0)                   AS shop_declined_count,
  COALESCE(tc.shop_pending_count, 0)                    AS shop_pending_count,
  COALESCE(tc.shop_info_requested_count, 0)             AS shop_info_requested_count,
  COALESCE(tc.shop_no_response_count, 0)                AS shop_no_response_count,
  tc.last_lender_response_at                            AS last_lender_response_at,
  -- Best offer: JARVIS-supplied via application JSONB. Frontend may
  -- compute it later from per-thread response summaries.
  NULLIF(pa.data->>'best_offer_amount', '')::NUMERIC              AS best_offer_amount,

  -- =====================================================================
  -- PRIORITY SCORE + REASON (computed inline — no helper function)
  --
  -- 100-pt scale. Weights:
  --   sla_overdue_days * 5    (capped at 50)
  --   is_hot * 30
  --   is_renewal_candidate * 25
  --   is_high_leverage * 15
  --   shop_offer_count * 8    (capped at 16)
  --   is_shopped_stale * 12
  --   is_cold * -10
  -- =====================================================================
  LEAST(100, GREATEST(0,
    LEAST(50, GREATEST(0,
      (EXTRACT(DAY FROM NOW() - COALESCE(pa.app_updated_at, l.updated_at))::INT
        - CASE pa.data->>'deal_stage'
            WHEN 'Application In' THEN 1
            WHEN 'Missing Info'   THEN 2
            WHEN 'Shopping'       THEN 3
            ELSE 7
          END
      ) * 5
    )) +
    CASE WHEN COALESCE(NULLIF(l.data->>'is_hot', '')::BOOLEAN, FALSE) THEN 30 ELSE 0 END +
    CASE WHEN
      COALESCE(l.data->>'merchant_stage', '') = 'Funded'
      AND COALESCE(NULLIF(pa.data->>'term_pct_used', '')::NUMERIC, 0) > 0.60
    THEN 25 ELSE 0 END +
    CASE WHEN COALESCE(pa.data->>'paper_grade', '') = 'D' THEN 15 ELSE 0 END +
    LEAST(16, COALESCE(tc.shop_offer_count, 0) * 8) +
    CASE WHEN COALESCE(NULLIF(l.data->>'is_shopped_stale', '')::BOOLEAN, FALSE) THEN 12 ELSE 0 END -
    CASE WHEN
      COALESCE(NULLIF(l.data->>'last_inbound_at', '')::TIMESTAMPTZ, NOW() - INTERVAL '49 hours')
        < NOW() - INTERVAL '48 hours'
    THEN 10 ELSE 0 END
  ))::INT                                               AS priority_score,

  -- priority_reason: human-readable short string for the row tooltip.
  TRIM(BOTH ', ' FROM (
    CONCAT_WS(', ',
      CASE WHEN
        EXTRACT(DAY FROM NOW() - COALESCE(pa.app_updated_at, l.updated_at))::INT
        - CASE pa.data->>'deal_stage'
            WHEN 'Application In' THEN 1
            WHEN 'Missing Info'   THEN 2
            WHEN 'Shopping'       THEN 3
            ELSE 7
          END > 0
      THEN 'Overdue in ' || COALESCE(pa.data->>'deal_stage', 'pipeline')
      ELSE NULL END,
      CASE WHEN COALESCE(NULLIF(l.data->>'is_hot', '')::BOOLEAN, FALSE) THEN 'hot' ELSE NULL END,
      CASE WHEN
        COALESCE(l.data->>'merchant_stage', '') = 'Funded'
        AND COALESCE(NULLIF(pa.data->>'term_pct_used', '')::NUMERIC, 0) > 0.60
      THEN 'renewal-ready' ELSE NULL END,
      CASE WHEN COALESCE(tc.shop_offer_count, 0) > 0
        THEN tc.shop_offer_count || ' offer' ||
             CASE WHEN tc.shop_offer_count = 1 THEN '' ELSE 's' END
        ELSE NULL END
    )
  ))                                                    AS priority_reason,

  -- =====================================================================
  -- METADATA
  -- =====================================================================
  l.created_at                                          AS created_at,
  l.updated_at                                          AS updated_at,
  pa.application_id                                     AS active_application_id

FROM public.tenant_records l
LEFT JOIN primary_app pa
       ON pa.tenant_id = l.tenant_id
      AND pa.lead_id_str = l.id::text
LEFT JOIN thread_counts tc
       ON tc.application_id = pa.application_id
LEFT JOIN public.user_profiles up
       ON up.id::text = l.data->>'assigned_user_id'
WHERE l.entity_type = 'lead';

-- ============================================================================
-- ROW-LEVEL SECURITY
-- ============================================================================
-- The view inherits RLS from its base tables (tenant_records,
-- application_lender_threads, user_profiles) — each already enforces
-- tenant_id scoping via their own policies. So `SELECT * FROM
-- merchant_summary` from a logged-in user only returns rows from their
-- tenant. No additional policy needed on the view itself.

-- Grant SELECT to the standard roles so the dashboard can query it
-- through the existing supabase-server.ts client.
GRANT SELECT ON public.merchant_summary TO authenticated;
GRANT SELECT ON public.merchant_summary TO service_role;

-- ============================================================================
-- PERFORMANCE NOTES
-- ============================================================================
-- Target: <200ms with 100 active merchants (Adon's spec).
--
-- The view's hot path:
--   1. Filter tenant_records on entity_type='lead' AND tenant_id
--      (uses idx_tenant_records_tenant_entity from migration 038)
--   2. Sub-select primary_app — uses idx_tenant_records_application_lead_id
--      (added in migration 065)
--   3. Sub-select thread_counts — uses idx_lender_threads_application
--      (from migration 044)
--   4. user_profiles join — uses the primary key index
--
-- If the view materializes slowly at scale, the standard upgrade path is
-- to add a materialized view refreshed on event (BRAVO_RECORD_STATUS_CHANGED)
-- — Phase 4 if needed.
-- ============================================================================

COMMIT;
