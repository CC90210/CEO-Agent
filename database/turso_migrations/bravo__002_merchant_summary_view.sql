-- ============================================================================
-- bravo__002 — merchant_summary, manually ported to SQLite/libSQL
--
-- The transpiler could not port this one and said so. bravo__transpile_report.json
-- records it verbatim:
--
--     "VIEWS_LOST": ["merchant_summary: needs manual port — WITH ranked_apps AS ..."]
--
-- That report was never actioned, so the view shipped missing. The consequence
-- was not an error page. lib/queries/merchant-summary.ts swallows exactly this
-- failure:
--
--     if (error.code === "42P01" || /merchant_summary/i.test(error.message))
--       return [];
--
-- so the SunBiz Pipeline rendered an EMPTY board with no warning while 2,373
-- tenant_records sat in the database. Silent, not loud.
--
-- Source of truth: SunBiz-Agent/database/075_merchant_summary_v2.sql. Confirmed
-- to be the applied version by column count — PostgREST reports 73 columns live
-- and 075 emits exactly 73, in this order.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES (what could not be carried over literally)
--
--   security_invoker / RLS   SQLite has no RLS. Tenant isolation for this view
--                            comes from db_turso's scoping guard plus the
--                            explicit .eq("tenant_id", …) the callers already
--                            pass. `tenant_id` is exposed so that filter works.
--   safe_numeric/int/bool    Postgres helpers; inlined here. The guard matters:
--   safe_timestamptz         SQLite's CAST('N/A' AS REAL) is 0.0, not NULL, and
--                            a silent 0 would cross the paper-grade and
--                            priority thresholds and mislabel real deals.
--   DISTINCT ON              rewritten as ROW_NUMBER() … = 1.
--   data->>'k'               json_extract(data,'$.k').
--   jsonb ? 'k'              json_extract(...) IS NOT NULL. `?` is a bind
--                            parameter in SQLite and must never appear here.
--   GREATEST/LEAST           max()/min(), but those return NULL if ANY argument
--                            is NULL where Postgres skips NULLs — every call is
--                            COALESCEd first.
--   EXTRACT(DAY FROM …)      julianday() difference, cast to INTEGER.
--   CONCAT_WS                built by hand. Not relied upon across libSQL
--                            versions for a load-bearing column.
--   booleans                 0/1. The adapter documents this (turso-postgrest.ts
--                            line 24) and nothing compares with === true.
--
--   agent_color              DELIBERATE DIVERGENCE. Postgres used HASHTEXT(),
--                            an internal hash with no SQLite equivalent, so the
--                            palette assignment is recomputed from the same key
--                            with a different hash. Colours stay stable and
--                            evenly distributed per user, but a given user may
--                            get a different chip colour than before. Cosmetic
--                            only — no other column depends on it.
-- ============================================================================

DROP VIEW IF EXISTS "merchant_summary";

CREATE VIEW "merchant_summary" AS
WITH ranked_apps AS (
  SELECT
    a.id                                    AS application_id,
    a.tenant_id                             AS tenant_id,
    json_extract(a.data, '$.lead_id')       AS lead_id_str,
    a.data                                  AS data,
    a.created_at                            AS app_created_at,
    a.updated_at                            AS app_updated_at,
    ROW_NUMBER() OVER (
      PARTITION BY a.tenant_id, json_extract(a.data, '$.lead_id')
      ORDER BY
        CASE json_extract(a.data, '$.deal_stage')
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
  FROM tenant_records a
  WHERE a.entity_type = 'application'
    AND json_extract(a.data, '$.lead_id') IS NOT NULL
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
    MAX(last_response_at)                             AS last_lender_response_at
  FROM application_lender_threads
  GROUP BY application_id
),
-- Every Postgres `numeric` became TEXT in the transpile (deliberately -- these
-- are money and ratios, and float would round them). That makes the comparisons
-- below a trap: SQLite orders storage classes NULL < INTEGER/REAL < TEXT, so a
-- TEXT value is ALWAYS greater than any number. Unguarded,
--
--     debt_to_revenue_ratio > 0.70     is true for every non-null row
--     debt_to_revenue_ratio > 1.00     grades every underwritten deal 'JUNK'
--
-- Measured on live data: 133 of 145 complete underwriting rows flagged
-- high-leverage as written, 0 with the cast. Casting once here fixes both the
-- comparisons and the output types, which the dashboard expects as numbers.
-- The GLOB guard keeps a non-numeric string from silently casting to 0.0.
ranked_uw AS (
  SELECT
    au.application_id,
    au.run_at                    AS uw_run_at,
    CASE WHEN au.avg_monthly_revenue IS NULL
           OR trim(CAST(au.avg_monthly_revenue AS TEXT)) = ''
           OR trim(CAST(au.avg_monthly_revenue AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(au.avg_monthly_revenue AS REAL) END
                                 AS uw_avg_monthly_revenue,
    CASE WHEN au.avg_daily_balance IS NULL
           OR trim(CAST(au.avg_daily_balance AS TEXT)) = ''
           OR trim(CAST(au.avg_daily_balance AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(au.avg_daily_balance AS REAL) END
                                 AS uw_avg_daily_balance,
    au.nsf_count                 AS uw_nsf_count,
    CASE WHEN au.deposit_consistency_pct IS NULL
           OR trim(CAST(au.deposit_consistency_pct AS TEXT)) = ''
           OR trim(CAST(au.deposit_consistency_pct AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(au.deposit_consistency_pct AS REAL) END
                                 AS uw_deposit_consistency_pct,
    CASE WHEN au.debt_service_monthly IS NULL
           OR trim(CAST(au.debt_service_monthly AS TEXT)) = ''
           OR trim(CAST(au.debt_service_monthly AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(au.debt_service_monthly AS REAL) END
                                 AS uw_debt_service_monthly,
    CASE WHEN au.debt_to_revenue_ratio IS NULL
           OR trim(CAST(au.debt_to_revenue_ratio AS TEXT)) = ''
           OR trim(CAST(au.debt_to_revenue_ratio AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(au.debt_to_revenue_ratio AS REAL) END
                                 AS uw_debt_to_revenue_ratio,
    au.lender_count              AS uw_lender_count,
    au.risk_flags                AS uw_risk_flags,
    au.readiness_score           AS uw_readiness_score,
    au.sales_angle               AS uw_sales_angle,
    ROW_NUMBER() OVER (PARTITION BY au.application_id ORDER BY au.run_at DESC) AS rk
  FROM application_underwriting au
  WHERE au.status = 'complete'
),
latest_underwriting AS (
  SELECT * FROM ranked_uw WHERE rk = 1
)
SELECT
  l.id                                                            AS merchant_id,
  l.tenant_id                                                     AS tenant_id,

  COALESCE(
    NULLIF(json_extract(l.data, '$.dba'), ''),
    NULLIF(json_extract(l.data, '$.business_name'), ''),
    NULLIF(json_extract(l.data, '$.company'), ''),
    NULLIF(json_extract(l.data, '$.name'), '')
  )                                                               AS dba,
  COALESCE(
    NULLIF(json_extract(l.data, '$.legal_name'), ''),
    NULLIF(json_extract(l.data, '$.business_name'), ''),
    NULLIF(json_extract(l.data, '$.company'), '')
  )                                                               AS legal_name,
  NULLIF(json_extract(l.data, '$.state'), '')                     AS state,
  NULLIF(json_extract(l.data, '$.city'), '')                      AS city,
  COALESCE(
    NULLIF(json_extract(l.data, '$.phone'), ''),
    NULLIF(json_extract(l.data, '$.phones[0]'), '')
  )                                                               AS phone,
  NULLIF(json_extract(l.data, '$.email'), '')                     AS email,
  NULLIF(json_extract(l.data, '$.industry'), '')                  AS industry,
  NULLIF(json_extract(l.data, '$.ein'), '')                       AS ein,
  CASE WHEN json_extract(l.data, '$.time_in_business_years') IS NULL
         OR trim(CAST(json_extract(l.data, '$.time_in_business_years') AS TEXT)) = ''
         OR trim(CAST(json_extract(l.data, '$.time_in_business_years') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL
       ELSE CAST(json_extract(l.data, '$.time_in_business_years') AS REAL) END
                                                                  AS tib_years,

  COALESCE(
    NULLIF(json_extract(l.data, '$.owner.full_name'), ''),
    NULLIF(json_extract(l.data, '$.owner_name'), ''),
    NULLIF(json_extract(l.data, '$.first_name'), '') || ' ' || NULLIF(json_extract(l.data, '$.last_name'), '')
  )                                                               AS owner_name,
  NULLIF(json_extract(l.data, '$.owner.title'), '')               AS owner_title,
  CASE WHEN json_extract(l.data, '$.owner.ownership_pct') IS NULL
         OR trim(CAST(json_extract(l.data, '$.owner.ownership_pct') AS TEXT)) = ''
         OR trim(CAST(json_extract(l.data, '$.owner.ownership_pct') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL
       ELSE CAST(json_extract(l.data, '$.owner.ownership_pct') AS REAL) END
                                                                  AS ownership_pct,
  NULLIF(json_extract(l.data, '$.owner.date_of_birth'), '')       AS owner_dob,
  NULLIF(json_extract(l.data, '$.owner.citizenship'), '')         AS owner_citizenship,
  CASE
    WHEN json_extract(l.data, '$.owner.ssn_last4') IS NOT NULL
      THEN json_extract(l.data, '$.owner.ssn_last4')
    WHEN json_extract(l.data, '$.owner.ssn') IS NOT NULL
      THEN substr(CAST(json_extract(l.data, '$.owner.ssn') AS TEXT), -4)
    ELSE NULL
  END                                                             AS ssn_last4,
  CASE WHEN json_extract(l.data, '$.owner.credit_score') IS NULL
         OR trim(CAST(json_extract(l.data, '$.owner.credit_score') AS TEXT)) = ''
         OR trim(CAST(json_extract(l.data, '$.owner.credit_score') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL
       ELSE CAST(json_extract(l.data, '$.owner.credit_score') AS INTEGER) END
                                                                  AS credit_score,

  NULLIF(json_extract(l.data, '$.physical_address.line1'), '')    AS physical_line1,
  NULLIF(json_extract(l.data, '$.physical_address.line2'), '')    AS physical_line2,
  NULLIF(json_extract(l.data, '$.physical_address.city'), '')     AS physical_city,
  NULLIF(json_extract(l.data, '$.physical_address.state'), '')    AS physical_state,
  NULLIF(json_extract(l.data, '$.physical_address.zip'), '')      AS physical_zip,
  CASE WHEN json_extract(l.data, '$.physical_address.years_at') IS NULL
         OR trim(CAST(json_extract(l.data, '$.physical_address.years_at') AS TEXT)) = ''
         OR trim(CAST(json_extract(l.data, '$.physical_address.years_at') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL
       ELSE CAST(json_extract(l.data, '$.physical_address.years_at') AS REAL) END
                                                                  AS physical_years_at,
  NULLIF(json_extract(l.data, '$.home_address.line1'), '')        AS home_line1,
  NULLIF(json_extract(l.data, '$.home_address.city'), '')         AS home_city,
  NULLIF(json_extract(l.data, '$.home_address.state'), '')        AS home_state,
  NULLIF(json_extract(l.data, '$.home_address.zip'), '')          AS home_zip,
  CASE WHEN json_extract(l.data, '$.home_address.years_at') IS NULL
         OR trim(CAST(json_extract(l.data, '$.home_address.years_at') AS TEXT)) = ''
         OR trim(CAST(json_extract(l.data, '$.home_address.years_at') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL
       ELSE CAST(json_extract(l.data, '$.home_address.years_at') AS REAL) END
                                                                  AS home_years_at,

  COALESCE(
    up.display_name,
    up.full_name,
    NULLIF(json_extract(l.data, '$.agent'), ''),
    NULLIF(json_extract(l.data, '$.assigned_to'), '')
  )                                                               AS agent,
  -- First letter of the first word + first letter of the last word. The
  -- last-word extraction is the rtrim/replace idiom: replace(name,' ','') is
  -- the set of non-space characters, rtrim strips every trailing character in
  -- that set, leaving the prefix up to the final space, which is then removed.
  CASE
    WHEN up.display_name IS NULL OR trim(up.display_name) = '' THEN NULL
    WHEN instr(trim(up.display_name), ' ') = 0
      THEN upper(substr(trim(up.display_name), 1, 1))
    ELSE upper(
           substr(trim(up.display_name), 1, 1) ||
           substr(
             replace(trim(up.display_name),
                     rtrim(trim(up.display_name),
                           replace(trim(up.display_name), ' ', '')),
                     ''),
             1, 1)
         )
  END                                                             AS agent_initials,
  CASE ((
      COALESCE(unicode(substr(COALESCE(up.id, json_extract(l.data, '$.assigned_user_id'), 'unknown'), 1, 1)), 0)
    + COALESCE(unicode(substr(COALESCE(up.id, json_extract(l.data, '$.assigned_user_id'), 'unknown'), 2, 1)), 0)
    + COALESCE(unicode(substr(COALESCE(up.id, json_extract(l.data, '$.assigned_user_id'), 'unknown'), 3, 1)), 0)
    + COALESCE(unicode(substr(COALESCE(up.id, json_extract(l.data, '$.assigned_user_id'), 'unknown'), 4, 1)), 0)
    ) % 6)
    WHEN 0 THEN '#C0842F'
    WHEN 1 THEN '#2E8392'
    WHEN 2 THEN '#7057A7'
    WHEN 3 THEN '#32876B'
    WHEN 4 THEN '#3978BE'
    WHEN 5 THEN '#9B3D45'
  END                                                             AS agent_color,

  COALESCE(NULLIF(json_extract(l.data, '$.merchant_stage'), ''), 'Lead')
                                                                  AS merchant_stage,
  CASE
    WHEN COALESCE(tc.shop_offer_count, 0) > 0
         AND COALESCE(json_extract(pa.data, '$.deal_stage'), '') NOT IN ('Funded', 'Declined', 'Dead')
      THEN 'Approved'
    ELSE NULLIF(json_extract(pa.data, '$.deal_stage'), '')
  END                                                             AS deal_stage,
  max(0, CAST(COALESCE(
    julianday('now') - julianday(COALESCE(
      CASE WHEN julianday(CAST(json_extract(pa.data, '$.stage_entered_at') AS TEXT)) IS NULL
           THEN NULL ELSE CAST(json_extract(pa.data, '$.stage_entered_at') AS TEXT) END,
      pa.app_updated_at,
      l.updated_at)),
    0) AS INTEGER))                                               AS days_in_stage,
  max(0, CAST(COALESCE(julianday('now') - julianday(COALESCE(pa.app_updated_at, l.updated_at)), 0) AS INTEGER)
         - CASE json_extract(pa.data, '$.deal_stage')
             WHEN 'Application In' THEN 1
             WHEN 'Missing Info'   THEN 2
             WHEN 'Shopping'       THEN 3
             WHEN 'Funded'         THEN 999
             WHEN 'Declined'       THEN 999
             WHEN 'Dead'           THEN 999
             ELSE 7
           END)                                                   AS sla_overdue_days,

  COALESCE(CASE WHEN lower(CAST(json_extract(l.data, '$.is_hot') AS TEXT)) IN ('true','t','1','yes','y') THEN 1
                WHEN lower(CAST(json_extract(l.data, '$.is_hot') AS TEXT)) IN ('false','f','0','no','n') THEN 0
                ELSE NULL END, 0)                                 AS is_hot,
  COALESCE(CASE WHEN lower(CAST(json_extract(l.data, '$.is_shopped_stale') AS TEXT)) IN ('true','t','1','yes','y') THEN 1
                WHEN lower(CAST(json_extract(l.data, '$.is_shopped_stale') AS TEXT)) IN ('false','f','0','no','n') THEN 0
                ELSE NULL END, 0)                                 AS is_shopped_stale,
  COALESCE(
    CASE WHEN julianday(CAST(json_extract(l.data, '$.last_inbound_at') AS TEXT)) IS NULL THEN NULL
         WHEN julianday(CAST(json_extract(l.data, '$.last_inbound_at') AS TEXT))
              < julianday('now', '-48 hours') THEN 1
         ELSE 0 END,
    0)                                                            AS is_cold,
  CASE WHEN COALESCE(json_extract(l.data, '$.merchant_stage'), '') = 'Funded'
        AND COALESCE(
              CASE WHEN json_extract(pa.data, '$.term_pct_used') IS NULL
                     OR trim(CAST(json_extract(pa.data, '$.term_pct_used') AS TEXT)) = ''
                     OR trim(CAST(json_extract(pa.data, '$.term_pct_used') AS TEXT)) GLOB '*[^0-9.eE+-]*'
                   THEN NULL
                   ELSE CAST(json_extract(pa.data, '$.term_pct_used') AS REAL) END, 0) > 0.60
       THEN 1 ELSE 0 END                                          AS is_renewal_candidate,
  CASE WHEN COALESCE(lu.uw_debt_to_revenue_ratio, 0) > 0.70
        OR COALESCE(json_extract(pa.data, '$.paper_grade'), '') = 'D'
        OR COALESCE(
             CASE WHEN json_extract(pa.data, '$.leverage_ratio') IS NULL
                    OR trim(CAST(json_extract(pa.data, '$.leverage_ratio') AS TEXT)) = ''
                    OR trim(CAST(json_extract(pa.data, '$.leverage_ratio') AS TEXT)) GLOB '*[^0-9.eE+-]*'
                  THEN NULL
                  ELSE CAST(json_extract(pa.data, '$.leverage_ratio') AS REAL) END, 0) > 0.70
       THEN 1 ELSE 0 END                                          AS is_high_leverage,

  COALESCE(
    NULLIF(json_extract(pa.data, '$.paper_grade_override'), ''),
    CASE
      WHEN lu.uw_debt_to_revenue_ratio IS NULL THEN NULL
      WHEN COALESCE(CASE WHEN lower(CAST(json_extract(pa.data, '$.has_mca_in_collections') AS TEXT)) IN ('true','t','1','yes','y') THEN 1
                         WHEN lower(CAST(json_extract(pa.data, '$.has_mca_in_collections') AS TEXT)) IN ('false','f','0','no','n') THEN 0
                         ELSE NULL END, 0) = 1
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
    NULLIF(json_extract(pa.data, '$.paper_grade'), '')
  )                                                               AS paper_grade,

  COALESCE(lu.uw_debt_to_revenue_ratio,
    CASE WHEN json_extract(pa.data, '$.leverage_ratio') IS NULL
           OR trim(CAST(json_extract(pa.data, '$.leverage_ratio') AS TEXT)) = ''
           OR trim(CAST(json_extract(pa.data, '$.leverage_ratio') AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(json_extract(pa.data, '$.leverage_ratio') AS REAL) END)
                                                                  AS leverage_ratio,
  COALESCE(lu.uw_avg_monthly_revenue,
    CASE WHEN json_extract(pa.data, '$.avg_monthly_revenue') IS NULL
           OR trim(CAST(json_extract(pa.data, '$.avg_monthly_revenue') AS TEXT)) = ''
           OR trim(CAST(json_extract(pa.data, '$.avg_monthly_revenue') AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(json_extract(pa.data, '$.avg_monthly_revenue') AS REAL) END)
                                                                  AS avg_monthly_revenue,
  COALESCE(
    CASE WHEN json_extract(pa.data, '$.nsf_avg_per_month') IS NULL
           OR trim(CAST(json_extract(pa.data, '$.nsf_avg_per_month') AS TEXT)) = ''
           OR trim(CAST(json_extract(pa.data, '$.nsf_avg_per_month') AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(json_extract(pa.data, '$.nsf_avg_per_month') AS REAL) END,
    CASE WHEN lu.uw_nsf_count IS NOT NULL THEN CAST(lu.uw_nsf_count AS REAL) / 3 ELSE NULL END)
                                                                  AS nsf_avg_per_month,
  COALESCE(lu.uw_lender_count,
    CASE WHEN json_extract(pa.data, '$.position_count') IS NULL
           OR trim(CAST(json_extract(pa.data, '$.position_count') AS TEXT)) = ''
           OR trim(CAST(json_extract(pa.data, '$.position_count') AS TEXT)) GLOB '*[^0-9.eE+-]*'
         THEN NULL ELSE CAST(json_extract(pa.data, '$.position_count') AS INTEGER) END,
    0)                                                            AS position_count,
  CASE WHEN json_extract(pa.data, '$.requested_amount') IS NULL
         OR trim(CAST(json_extract(pa.data, '$.requested_amount') AS TEXT)) = ''
         OR trim(CAST(json_extract(pa.data, '$.requested_amount') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL ELSE CAST(json_extract(pa.data, '$.requested_amount') AS REAL) END
                                                                  AS funding_potential_usd,
  CASE WHEN json_extract(pa.data, '$.current_funded_amount') IS NULL
         OR trim(CAST(json_extract(pa.data, '$.current_funded_amount') AS TEXT)) = ''
         OR trim(CAST(json_extract(pa.data, '$.current_funded_amount') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL ELSE CAST(json_extract(pa.data, '$.current_funded_amount') AS REAL) END
                                                                  AS current_funded_amount,
  CASE WHEN julianday(CAST(json_extract(pa.data, '$.submitted_at') AS TEXT)) IS NULL
       THEN NULL ELSE CAST(json_extract(pa.data, '$.submitted_at') AS TEXT) END
                                                                  AS submitted_at,
  COALESCE(
    CASE WHEN julianday(CAST(json_extract(l.data, '$.last_touch_at') AS TEXT)) IS NULL
         THEN NULL ELSE CAST(json_extract(l.data, '$.last_touch_at') AS TEXT) END,
    l.updated_at)                                                 AS last_touch_at,
  CASE WHEN julianday(CAST(json_extract(l.data, '$.last_sms_at') AS TEXT)) IS NULL
       THEN NULL ELSE CAST(json_extract(l.data, '$.last_sms_at') AS TEXT) END
                                                                  AS last_sms_at,
  CASE WHEN julianday(CAST(json_extract(l.data, '$.last_email_at') AS TEXT)) IS NULL
       THEN NULL ELSE CAST(json_extract(l.data, '$.last_email_at') AS TEXT) END
                                                                  AS last_email_at,

  COALESCE(tc.shop_sent_count, 0)                                 AS shop_sent_count,
  COALESCE(tc.shop_replied_count, 0)                              AS shop_replied_count,
  COALESCE(tc.shop_offer_count, 0)                                AS shop_offer_count,
  COALESCE(tc.shop_declined_count, 0)                             AS shop_declined_count,
  COALESCE(tc.shop_pending_count, 0)                              AS shop_pending_count,
  COALESCE(tc.shop_info_requested_count, 0)                       AS shop_info_requested_count,
  COALESCE(tc.shop_no_response_count, 0)                          AS shop_no_response_count,
  tc.last_lender_response_at                                      AS last_lender_response_at,
  CASE WHEN json_extract(pa.data, '$.best_offer_amount') IS NULL
         OR trim(CAST(json_extract(pa.data, '$.best_offer_amount') AS TEXT)) = ''
         OR trim(CAST(json_extract(pa.data, '$.best_offer_amount') AS TEXT)) GLOB '*[^0-9.eE+-]*'
       THEN NULL ELSE CAST(json_extract(pa.data, '$.best_offer_amount') AS REAL) END
                                                                  AS best_offer_amount,

  CAST(min(100, max(0,
    min(50, max(0,
      (CAST(COALESCE(julianday('now') - julianday(COALESCE(pa.app_updated_at, l.updated_at)), 0) AS INTEGER)
        - CASE json_extract(pa.data, '$.deal_stage')
            WHEN 'Application In' THEN 1
            WHEN 'Missing Info'   THEN 2
            WHEN 'Shopping'       THEN 3
            ELSE 7
          END
      ) * 5
    )) +
    CASE WHEN COALESCE(CASE WHEN lower(CAST(json_extract(l.data, '$.is_hot') AS TEXT)) IN ('true','t','1','yes','y') THEN 1 ELSE 0 END, 0) = 1 THEN 30 ELSE 0 END +
    CASE WHEN COALESCE(json_extract(l.data, '$.merchant_stage'), '') = 'Funded'
          AND COALESCE(
                CASE WHEN json_extract(pa.data, '$.term_pct_used') IS NULL
                       OR trim(CAST(json_extract(pa.data, '$.term_pct_used') AS TEXT)) = ''
                       OR trim(CAST(json_extract(pa.data, '$.term_pct_used') AS TEXT)) GLOB '*[^0-9.eE+-]*'
                     THEN NULL ELSE CAST(json_extract(pa.data, '$.term_pct_used') AS REAL) END, 0) > 0.60
         THEN 25 ELSE 0 END +
    CASE WHEN COALESCE(json_extract(pa.data, '$.paper_grade'), '') = 'D' THEN 15 ELSE 0 END +
    min(16, COALESCE(tc.shop_offer_count, 0) * 8) +
    CASE WHEN COALESCE(CASE WHEN lower(CAST(json_extract(l.data, '$.is_shopped_stale') AS TEXT)) IN ('true','t','1','yes','y') THEN 1 ELSE 0 END, 0) = 1 THEN 12 ELSE 0 END -
    CASE WHEN COALESCE(
                julianday(CAST(json_extract(l.data, '$.last_inbound_at') AS TEXT)),
                julianday('now', '-49 hours'))
              < julianday('now', '-48 hours')
         THEN 10 ELSE 0 END
  )) AS INTEGER)                                                  AS priority_score,

  -- CONCAT_WS(', ', …) built by hand: each present part is suffixed with the
  -- separator, absent parts contribute nothing, and the trailing separator is
  -- trimmed. TRIM(BOTH ', ') maps to trim(x, ', ').
  NULLIF(trim(
    COALESCE(
      CASE WHEN CAST(COALESCE(julianday('now') - julianday(COALESCE(pa.app_updated_at, l.updated_at)), 0) AS INTEGER)
                - CASE json_extract(pa.data, '$.deal_stage')
                    WHEN 'Application In' THEN 1
                    WHEN 'Missing Info'   THEN 2
                    WHEN 'Shopping'       THEN 3
                    ELSE 7
                  END > 0
           THEN 'Overdue in ' || COALESCE(json_extract(pa.data, '$.deal_stage'), 'pipeline') || ', '
           ELSE NULL END, '')
    ||
    COALESCE(
      CASE WHEN lower(CAST(json_extract(l.data, '$.is_hot') AS TEXT)) IN ('true','t','1','yes','y')
           THEN 'hot, ' ELSE NULL END, '')
    ||
    COALESCE(
      CASE WHEN COALESCE(json_extract(l.data, '$.merchant_stage'), '') = 'Funded'
            AND COALESCE(
                  CASE WHEN json_extract(pa.data, '$.term_pct_used') IS NULL
                         OR trim(CAST(json_extract(pa.data, '$.term_pct_used') AS TEXT)) = ''
                         OR trim(CAST(json_extract(pa.data, '$.term_pct_used') AS TEXT)) GLOB '*[^0-9.eE+-]*'
                       THEN NULL ELSE CAST(json_extract(pa.data, '$.term_pct_used') AS REAL) END, 0) > 0.60
           THEN 'renewal-ready, ' ELSE NULL END, '')
    ||
    COALESCE(
      CASE WHEN COALESCE(tc.shop_offer_count, 0) > 0
           THEN CAST(tc.shop_offer_count AS TEXT) || ' offer' ||
                CASE WHEN tc.shop_offer_count = 1 THEN '' ELSE 's' END || ', '
           ELSE NULL END, '')
  , ', '), '')                                                    AS priority_reason,

  l.created_at                                                    AS created_at,
  l.updated_at                                                    AS updated_at,
  pa.application_id                                               AS active_application_id,

  lu.uw_readiness_score                                           AS readiness_score,
  lu.uw_risk_flags                                                AS risk_flags,
  lu.uw_sales_angle                                               AS sales_angle,
  lu.uw_avg_daily_balance                                         AS avg_daily_balance,
  lu.uw_deposit_consistency_pct                                   AS deposit_consistency_pct,
  lu.uw_debt_service_monthly                                      AS debt_service_monthly,
  lu.uw_run_at                                                    AS last_underwriting_run_at

FROM tenant_records l
LEFT JOIN primary_app pa
       ON pa.tenant_id = l.tenant_id
      AND pa.lead_id_str = l.id
LEFT JOIN thread_counts tc
       ON tc.application_id = pa.application_id
LEFT JOIN latest_underwriting lu
       ON lu.application_id = pa.application_id
LEFT JOIN user_profiles up
       ON up.id = json_extract(l.data, '$.assigned_user_id')
WHERE l.entity_type = 'lead';
