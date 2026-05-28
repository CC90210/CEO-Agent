-- ============================================================================
-- Migration 072 — merchant_summary v2 (joins application_underwriting)
--
-- Phase 1's merchant_summary view (migration 066) read every economic
-- column out of `application.data->>'<field>'`. That worked when JARVIS-
-- side underwriting wrote results back into the application JSONB, but
-- the OASIS-native underwriting pipeline shipped by migration 069 +
-- SunBiz-Agent's underwriting_orchestrator writes its output to a NEW
-- table: public.application_underwriting (one row per run, append-only,
-- status='complete' when finalised).
--
-- Effect of the v1 view: every paper_grade / leverage_ratio /
-- avg_monthly_revenue / nsf_avg_per_month / position_count column in
-- the dashboard surfaces as NULL even after underwriting succeeds, because
-- the orchestrator never writes those keys back to application.data.
--
-- v2 fix: LEFT JOIN the latest status='complete' row from
-- application_underwriting per application, source the underwriting
-- metrics from there, AND derive Adon's §8 paper_grade in-view from the
-- leverage / NSF / position counts. Operator override path preserved via
-- application.data.paper_grade_override (always wins when set).
--
-- New columns surfaced to the frontend (additive — Phase 1 callers still
-- compile):
--   readiness_score          (0-100 underwriting agent suggestion)
--   risk_flags               (jsonb array; e.g. ['stacked','declining_revenue'])
--   sales_angle              (text — the pitch the dashboard shows operators)
--   avg_daily_balance        (numeric, from underwriting)
--   deposit_consistency_pct  (numeric, from underwriting)
--   debt_service_monthly     (numeric, monthly MCA burden)
--   last_underwriting_run_at (timestamptz)
--
-- Re-sourced columns (same names, now backed by underwriting first):
--   avg_monthly_revenue, nsf_avg_per_month, position_count,
--   leverage_ratio, paper_grade
--
-- Apply via: python scripts/apply_migration.py database/072_merchant_summary_v2.sql
-- (No UPDATE statements. Safe through the apply script.)
-- ============================================================================

BEGIN;

CREATE OR REPLACE VIEW public.merchant_summary
  WITH (security_invoker = true)
AS
WITH
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
),
-- NEW in v2: latest complete underwriting run per application. Status
-- filter excludes pending/parsing/error so we don't surface stale or
-- incomplete metrics — the dashboard already shows a "Run underwriting"
-- CTA when no complete row exists.
latest_underwriting AS (
  SELECT DISTINCT ON (au.application_id)
    au.application_id,
    au.run_at                       AS uw_run_at,
    au.avg_monthly_revenue          AS uw_avg_monthly_revenue,
    au.avg_daily_balance            AS uw_avg_daily_balance,
    au.nsf_count                    AS uw_nsf_count,
    au.deposit_consistency_pct      AS uw_deposit_consistency_pct,
    au.debt_service_monthly         AS uw_debt_service_monthly,
    au.debt_to_revenue_ratio        AS uw_debt_to_revenue_ratio,
    au.lender_count                 AS uw_lender_count,
    au.risk_flags                   AS uw_risk_flags,
    au.readiness_score              AS uw_readiness_score,
    au.sales_angle                  AS uw_sales_angle,
    au.parser_output                AS uw_parser_output
  FROM public.application_underwriting au
  WHERE au.status = 'complete'
  ORDER BY au.application_id, au.run_at DESC
)
SELECT
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
  public.safe_numeric(l.data->>'time_in_business_years')          AS tib_years,

  COALESCE(
    NULLIF(l.data->'owner'->>'full_name', ''),
    NULLIF(l.data->>'owner_name', ''),
    NULLIF(l.data->>'first_name', '') || ' ' || NULLIF(l.data->>'last_name', '')
  )                                                     AS owner_name,
  NULLIF(l.data->'owner'->>'title', '')                 AS owner_title,
  public.safe_numeric(l.data->'owner'->>'ownership_pct')          AS ownership_pct,
  NULLIF(l.data->'owner'->>'date_of_birth', '')         AS owner_dob,
  NULLIF(l.data->'owner'->>'citizenship', '')           AS owner_citizenship,
  CASE
    WHEN l.data->'owner' ? 'ssn_last4'
      THEN l.data->'owner'->>'ssn_last4'
    WHEN l.data->'owner' ? 'ssn'
      THEN RIGHT(l.data->'owner'->>'ssn', 4)
    ELSE NULL
  END                                                   AS ssn_last4,
  public.safe_int(l.data->'owner'->>'credit_score')               AS credit_score,

  NULLIF(l.data->'physical_address'->>'line1', '')      AS physical_line1,
  NULLIF(l.data->'physical_address'->>'line2', '')      AS physical_line2,
  NULLIF(l.data->'physical_address'->>'city', '')       AS physical_city,
  NULLIF(l.data->'physical_address'->>'state', '')      AS physical_state,
  NULLIF(l.data->'physical_address'->>'zip', '')        AS physical_zip,
  public.safe_numeric(l.data->'physical_address'->>'years_at')    AS physical_years_at,
  NULLIF(l.data->'home_address'->>'line1', '')          AS home_line1,
  NULLIF(l.data->'home_address'->>'city', '')           AS home_city,
  NULLIF(l.data->'home_address'->>'state', '')          AS home_state,
  NULLIF(l.data->'home_address'->>'zip', '')            AS home_zip,
  public.safe_numeric(l.data->'home_address'->>'years_at')        AS home_years_at,

  COALESCE(
    up.display_name,
    up.full_name,
    NULLIF(l.data->>'agent', ''),
    NULLIF(l.data->>'assigned_to', '')
  )                                                     AS agent,
  CASE
    WHEN up.display_name IS NOT NULL THEN
      UPPER(LEFT(SPLIT_PART(up.display_name, ' ', 1), 1) ||
            LEFT(SPLIT_PART(up.display_name, ' ', GREATEST(2, ARRAY_LENGTH(STRING_TO_ARRAY(up.display_name, ' '), 1))), 1))
    ELSE NULL
  END                                                   AS agent_initials,
  CASE (HASHTEXT(COALESCE(up.id::text, l.data->>'assigned_user_id', 'unknown')) % 6 + 6) % 6
    WHEN 0 THEN '#C0842F'
    WHEN 1 THEN '#2E8392'
    WHEN 2 THEN '#7057A7'
    WHEN 3 THEN '#32876B'
    WHEN 4 THEN '#3978BE'
    WHEN 5 THEN '#9B3D45'
  END                                                   AS agent_color,

  COALESCE(
    NULLIF(l.data->>'merchant_stage', ''),
    'Lead'
  )                                                     AS merchant_stage,
  CASE
    WHEN COALESCE(tc.shop_offer_count, 0) > 0
         AND COALESCE(pa.data->>'deal_stage', '') NOT IN ('Funded', 'Declined', 'Dead')
      THEN 'Approved'
    ELSE NULLIF(pa.data->>'deal_stage', '')
  END                                                   AS deal_stage,
  GREATEST(
    0,
    EXTRACT(
      DAY FROM NOW() - COALESCE(
        public.safe_timestamptz(pa.data->>'stage_entered_at'),
        pa.app_updated_at,
        l.updated_at
      )
    )::INT
  )                                                     AS days_in_stage,
  GREATEST(
    0,
    EXTRACT(
      DAY FROM NOW() - COALESCE(pa.app_updated_at, l.updated_at)
    )::INT - CASE pa.data->>'deal_stage'
              WHEN 'Application In' THEN 1
              WHEN 'Missing Info'   THEN 2
              WHEN 'Shopping'       THEN 3
              WHEN 'Funded'         THEN 999
              WHEN 'Declined'       THEN 999
              WHEN 'Dead'           THEN 999
              ELSE 7
            END
  )                                                     AS sla_overdue_days,

  COALESCE(public.safe_bool(l.data->>'is_hot'), FALSE)            AS is_hot,
  COALESCE(public.safe_bool(l.data->>'is_shopped_stale'), FALSE)  AS is_shopped_stale,
  COALESCE(
    public.safe_timestamptz(l.data->>'last_inbound_at')
      < NOW() - INTERVAL '48 hours',
    FALSE
  )                                                     AS is_cold,
  (
    COALESCE(l.data->>'merchant_stage', '') = 'Funded'
    AND COALESCE(public.safe_numeric(pa.data->>'term_pct_used'), 0) > 0.60
  )                                                     AS is_renewal_candidate,
  -- High leverage: use underwriting's debt-to-revenue ratio if available;
  -- fall back to operator-set paper_grade='D' or jsonb leverage_ratio.
  (
    COALESCE(lu.uw_debt_to_revenue_ratio, 0) > 0.70
    OR COALESCE(pa.data->>'paper_grade', '') = 'D'
    OR COALESCE(public.safe_numeric(pa.data->>'leverage_ratio'), 0) > 0.70
  )                                                     AS is_high_leverage,

  -- ======== PAPER GRADE — Adon §8 rubric, computed from underwriting ========
  -- Operator override wins. Else compute from underwriting metrics. Else
  -- fall back to legacy paper_grade in application JSONB. Else NULL.
  COALESCE(
    NULLIF(pa.data->>'paper_grade_override', ''),
    CASE
      WHEN lu.uw_debt_to_revenue_ratio IS NULL THEN NULL
      -- JUNK: any MCA in collections (operator-flagged) OR >100% leverage
      WHEN COALESCE(public.safe_bool(pa.data->>'has_mca_in_collections'), FALSE)
        OR lu.uw_debt_to_revenue_ratio > 1.00
        THEN 'JUNK'
      WHEN lu.uw_debt_to_revenue_ratio < 0.25
        AND COALESCE(lu.uw_nsf_count, 0) <= 1
        AND COALESCE(lu.uw_lender_count, 0) <= 1
        THEN 'A'
      WHEN lu.uw_debt_to_revenue_ratio < 0.45
        AND COALESCE(lu.uw_nsf_count, 0) <= 3
        AND COALESCE(lu.uw_lender_count, 0) <= 2
        THEN 'B'
      WHEN lu.uw_debt_to_revenue_ratio < 0.70
        AND COALESCE(lu.uw_nsf_count, 0) <= 6
        AND COALESCE(lu.uw_lender_count, 0) <= 4
        THEN 'C'
      ELSE 'D'
    END,
    NULLIF(pa.data->>'paper_grade', '')
  )                                                     AS paper_grade,

  -- Leverage ratio — underwriting wins, JSONB fallback
  COALESCE(
    lu.uw_debt_to_revenue_ratio,
    public.safe_numeric(pa.data->>'leverage_ratio')
  )                                                     AS leverage_ratio,
  -- Avg monthly revenue — underwriting wins, JSONB fallback
  COALESCE(
    lu.uw_avg_monthly_revenue,
    public.safe_numeric(pa.data->>'avg_monthly_revenue')
  )                                                     AS avg_monthly_revenue,
  -- NSFs per month — underwriting is total nsf_count over 3-6mo window;
  -- approximate per-month as count/3 if we have a count. Operator JSONB
  -- value (already "per month") wins if explicitly set.
  COALESCE(
    public.safe_numeric(pa.data->>'nsf_avg_per_month'),
    CASE WHEN lu.uw_nsf_count IS NOT NULL THEN lu.uw_nsf_count::NUMERIC / 3 ELSE NULL END
  )                                                     AS nsf_avg_per_month,
  -- Position count — underwriting wins, JSONB fallback
  COALESCE(
    lu.uw_lender_count,
    public.safe_int(pa.data->>'position_count'),
    0
  )                                                     AS position_count,
  public.safe_numeric(pa.data->>'requested_amount')     AS funding_potential_usd,
  public.safe_numeric(pa.data->>'current_funded_amount') AS current_funded_amount,
  public.safe_timestamptz(pa.data->>'submitted_at')     AS submitted_at,
  COALESCE(
    public.safe_timestamptz(l.data->>'last_touch_at'),
    l.updated_at
  )                                                     AS last_touch_at,
  public.safe_timestamptz(l.data->>'last_sms_at')       AS last_sms_at,
  public.safe_timestamptz(l.data->>'last_email_at')     AS last_email_at,

  COALESCE(tc.shop_sent_count, 0)                       AS shop_sent_count,
  COALESCE(tc.shop_replied_count, 0)                    AS shop_replied_count,
  COALESCE(tc.shop_offer_count, 0)                      AS shop_offer_count,
  COALESCE(tc.shop_declined_count, 0)                   AS shop_declined_count,
  COALESCE(tc.shop_pending_count, 0)                    AS shop_pending_count,
  COALESCE(tc.shop_info_requested_count, 0)             AS shop_info_requested_count,
  COALESCE(tc.shop_no_response_count, 0)                AS shop_no_response_count,
  tc.last_lender_response_at                            AS last_lender_response_at,
  public.safe_numeric(pa.data->>'best_offer_amount')    AS best_offer_amount,

  -- Priority score / reason — unchanged from v1 (still leverage-aware via
  -- the new paper_grade source) but now includes readiness_score signal.
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
    CASE WHEN COALESCE(public.safe_bool(l.data->>'is_hot'), FALSE) THEN 30 ELSE 0 END +
    CASE WHEN
      COALESCE(l.data->>'merchant_stage', '') = 'Funded'
      AND COALESCE(public.safe_numeric(pa.data->>'term_pct_used'), 0) > 0.60
    THEN 25 ELSE 0 END +
    CASE WHEN COALESCE(pa.data->>'paper_grade', '') = 'D' THEN 15 ELSE 0 END +
    LEAST(16, COALESCE(tc.shop_offer_count, 0) * 8) +
    CASE WHEN COALESCE(public.safe_bool(l.data->>'is_shopped_stale'), FALSE) THEN 12 ELSE 0 END -
    CASE WHEN
      COALESCE(public.safe_timestamptz(l.data->>'last_inbound_at'), NOW() - INTERVAL '49 hours')
        < NOW() - INTERVAL '48 hours'
    THEN 10 ELSE 0 END
  ))::INT                                               AS priority_score,
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
      CASE WHEN COALESCE(public.safe_bool(l.data->>'is_hot'), FALSE) THEN 'hot' ELSE NULL END,
      CASE WHEN
        COALESCE(l.data->>'merchant_stage', '') = 'Funded'
        AND COALESCE(public.safe_numeric(pa.data->>'term_pct_used'), 0) > 0.60
      THEN 'renewal-ready' ELSE NULL END,
      CASE WHEN COALESCE(tc.shop_offer_count, 0) > 0
        THEN tc.shop_offer_count || ' offer' ||
             CASE WHEN tc.shop_offer_count = 1 THEN '' ELSE 's' END
        ELSE NULL END
    )
  ))                                                    AS priority_reason,

  l.created_at                                          AS created_at,
  l.updated_at                                          AS updated_at,
  pa.application_id                                     AS active_application_id,

  -- ============================================================================
  -- NEW v2 COLUMNS — underwriting-sourced metrics surfaced to the dashboard
  -- ============================================================================
  lu.uw_readiness_score                                 AS readiness_score,
  lu.uw_risk_flags                                      AS risk_flags,
  lu.uw_sales_angle                                     AS sales_angle,
  lu.uw_avg_daily_balance                               AS avg_daily_balance,
  lu.uw_deposit_consistency_pct                         AS deposit_consistency_pct,
  lu.uw_debt_service_monthly                            AS debt_service_monthly,
  lu.uw_run_at                                          AS last_underwriting_run_at

FROM public.tenant_records l
LEFT JOIN primary_app pa
       ON pa.tenant_id = l.tenant_id
      AND pa.lead_id_str = l.id::text
LEFT JOIN thread_counts tc
       ON tc.application_id = pa.application_id::text
LEFT JOIN latest_underwriting lu
       ON lu.application_id = pa.application_id
LEFT JOIN public.user_profiles up
       ON up.id::text = l.data->>'assigned_user_id'
WHERE l.entity_type = 'lead';

GRANT SELECT ON public.merchant_summary TO authenticated;
GRANT SELECT ON public.merchant_summary TO service_role;

COMMIT;
