-- ============================================================================
-- Migration 071 — known_funding_companies tier metadata + 22 additional funders
--
-- Migration 069 seeded the registry with 18 well-known MCA/loan companies but
-- left the tier/term/factor-rate columns null. The underwriting agent's
-- sales_angle.py and the dashboard's lender-match UI both need this metadata
-- to pre-rank lenders against a deal's profile (Adon's spec §10).
--
-- Two changes ship together:
--   1. Backfill tier + term + factor-rate range on existing 18 rows.
--   2. INSERT 22 additional funders Adon's spec §10 + §7 lists (CFG, Fora,
--      Mulligan, DLP, Olympus, Cloudfund, Cherokee, Enod, Giggle, Instafund,
--      Mint, Family, Loanme, Funding Metrics, Channel, Idea, Mr. Advance,
--      GMD, Trellis, Reliant, Lendr, Spartan). Each with tier + factor +
--      term metadata so the dashboard ranks them correctly out of the box.
--
-- Schema additions: NONE. Migration 069 already provides tier_name implicitly
-- via the metadata columns (typical_term_days, typical_buy_rate_min/max,
-- category). We add an explicit `tier` column here so the dashboard can
-- group funders by their submission priority — operators submit Tier 1
-- first, fall through to Tier 4 on declines. Per Adon §10.
--
-- All inserts/updates are idempotent (ON CONFLICT (name)).
--
-- Apply: python scripts/apply_migration.py database/071_known_funding_companies_enrichment.sql
-- ============================================================================

BEGIN;

-- Add `tier` column (1-4) per Adon's §10 priority map.
-- Idempotent via IF NOT EXISTS.
ALTER TABLE public.known_funding_companies
    ADD COLUMN IF NOT EXISTS tier int CHECK (tier BETWEEN 1 AND 4);

ALTER TABLE public.known_funding_companies
    ADD COLUMN IF NOT EXISTS paper_grades_accepted text[] DEFAULT ARRAY[]::text[];

ALTER TABLE public.known_funding_companies
    ADD COLUMN IF NOT EXISTS contact_email text;

ALTER TABLE public.known_funding_companies
    ADD COLUMN IF NOT EXISTS submission_notes text;

CREATE INDEX IF NOT EXISTS idx_known_funding_tier
    ON public.known_funding_companies(tier, active)
    WHERE active = true AND tier IS NOT NULL;

COMMENT ON COLUMN public.known_funding_companies.tier IS
    'Adon §10 submission-priority tier: 1=Premium (clean A only), 2=Mid (1-2 positions), 3=Sub-prime (B-D consolidation), 4=Micro/High-risk (small-dollar D). Lower tier = submit first.';

COMMENT ON COLUMN public.known_funding_companies.paper_grades_accepted IS
    'Which Adon §8 paper grades this funder will look at. {A}, {A,B}, {B,C,D}, etc.';

-- ============================================================================
-- BACKFILL existing 18 entries with tier metadata
-- ============================================================================

UPDATE public.known_funding_companies SET
    tier = 1, typical_term_days = 270, typical_buy_rate_min = 1.20, typical_buy_rate_max = 1.35,
    paper_grades_accepted = ARRAY['A']
WHERE name IN ('OnDeck', 'Forward Financing', 'Kapitus', 'Credibly', 'BlueVine');

UPDATE public.known_funding_companies SET
    tier = 1, typical_term_days = 365, typical_buy_rate_min = 1.18, typical_buy_rate_max = 1.32,
    paper_grades_accepted = ARRAY['A']
WHERE name IN ('Square Capital', 'Stripe Capital', 'PayPal Working Capital');

UPDATE public.known_funding_companies SET
    tier = 2, typical_term_days = 180, typical_buy_rate_min = 1.30, typical_buy_rate_max = 1.42,
    paper_grades_accepted = ARRAY['A','B']
WHERE name IN ('Velocity', 'CAN Capital', 'National Funding', 'Funding Circle', 'Kabbage');

UPDATE public.known_funding_companies SET
    tier = 3, typical_term_days = 120, typical_buy_rate_min = 1.40, typical_buy_rate_max = 1.55,
    paper_grades_accepted = ARRAY['B','C','D']
WHERE name IN ('Yellowstone Capital', 'Mantis Funding', 'Rapid Capital Funding', 'Reliant Funding', 'Fundbox');

-- ============================================================================
-- INSERT additional funders from Adon §10 tier tables
-- ============================================================================
--
-- Each row carries tier + term + factor-rate + paper_grades_accepted so the
-- dashboard's lender-match logic ranks them without further configuration.
-- contact_email left null on purpose — operator confirms each on first
-- submission so we don't ship stale addresses Adon hasn't validated.

INSERT INTO public.known_funding_companies (
    name, aliases, industry_signal_keywords, category, tier,
    typical_term_days, typical_buy_rate_min, typical_buy_rate_max,
    paper_grades_accepted
) VALUES
    -- Tier 2 — Mid (1-2 positions, manageable leverage)
    ('CFG Merchant Solutions',  ARRAY['CFG'],              ARRAY['CFG MERCHANT','CFG MS'],                'mca', 2, 180, 1.30, 1.42, ARRAY['A','B']),
    ('Fora Financial',          ARRAY['Fora'],             ARRAY['FORA FINANCIAL','FORA'],                'mca', 2, 180, 1.30, 1.42, ARRAY['A','B']),
    ('Mulligan Funding',        ARRAY['Mulligan'],         ARRAY['MULLIGAN FUNDING','MULLIGAN'],          'mca', 2, 180, 1.32, 1.42, ARRAY['A','B']),

    -- Tier 3 — Sub-prime (B-D paper, consolidation territory — SunBiz's bread and butter)
    ('DLP Capital',             ARRAY['DLP'],              ARRAY['DLP CAPITAL','DLP CAP'],                'mca', 3, 150, 1.40, 1.55, ARRAY['B','C','D']),
    ('Olympus Funding',         ARRAY['Olympus'],          ARRAY['OLYMPUS FUNDING','OLYMPUS'],            'mca', 3, 120, 1.40, 1.52, ARRAY['B','C','D']),
    ('Cloudfund',               ARRAY['Cloud Fund'],       ARRAY['CLOUDFUND','CLOUD FUND'],               'mca', 3, 120, 1.42, 1.55, ARRAY['C','D']),
    ('Cherokee Funding',        ARRAY['Cherokee'],         ARRAY['CHEROKEE FUNDING','CHEROKEE'],          'mca', 3, 150, 1.40, 1.50, ARRAY['B','C','D']),
    ('Enod Capital',            ARRAY['Enod'],             ARRAY['ENOD CAPITAL','ENOD'],                  'mca', 3, 120, 1.42, 1.55, ARRAY['C','D']),
    ('Loanme',                  ARRAY['Loan Me'],          ARRAY['LOANME','LOAN ME'],                     'mca', 3, 150, 1.40, 1.52, ARRAY['C','D']),
    ('Funding Metrics',         ARRAY['FM Capital'],       ARRAY['FUNDING METRICS','FM CAP'],             'mca', 3, 120, 1.42, 1.55, ARRAY['C','D']),
    ('Channel Partners Capital',ARRAY['Channel Partners'], ARRAY['CHANNEL PARTNERS','CHANNEL CAP'],       'mca', 3, 180, 1.40, 1.50, ARRAY['B','C']),
    ('Idea Financial',          ARRAY['Idea'],             ARRAY['IDEA FINANCIAL','IDEA FIN'],            'mca', 3, 120, 1.42, 1.52, ARRAY['C','D']),
    ('Mr. Advance',             ARRAY['Mr Advance'],       ARRAY['MR ADVANCE','MRADVANCE'],               'mca', 3, 120, 1.45, 1.55, ARRAY['C','D']),
    ('GMD Capital',             ARRAY['GMD'],              ARRAY['GMD CAPITAL','GMD CAP'],                'mca', 3, 120, 1.45, 1.55, ARRAY['C','D']),
    ('Trellis Funding',         ARRAY['Trellis'],          ARRAY['TRELLIS FUNDING','TRELLIS'],            'mca', 3, 120, 1.42, 1.52, ARRAY['C','D']),
    ('Lendr',                   ARRAY['Lendr Inc'],        ARRAY['LENDR','LENDR INC'],                    'mca', 3, 150, 1.40, 1.50, ARRAY['B','C','D']),
    ('Spartan Capital',         ARRAY['Spartan'],          ARRAY['SPARTAN CAPITAL','SPARTAN CAP'],        'mca', 3, 120, 1.42, 1.55, ARRAY['C','D']),

    -- Tier 4 — Micro / high-risk (small-dollar high-frequency, D paper)
    ('Giggle Finance',          ARRAY['Giggle'],           ARRAY['GIGGLE FINANCE','GIGGLE'],              'mca', 4, 90,  1.45, 1.65, ARRAY['D']),
    ('Instafund',               ARRAY['Insta Fund'],       ARRAY['INSTAFUND','INSTA FUND'],               'mca', 4, 90,  1.50, 1.65, ARRAY['D']),
    ('Mint Capital',            ARRAY['Mint'],             ARRAY['MINT CAPITAL','MINT CAP'],              'mca', 4, 90,  1.50, 1.65, ARRAY['D']),
    ('Family Capital',          ARRAY['Family'],           ARRAY['FAMILY CAPITAL','FAMILY CAP'],          'mca', 4, 90,  1.50, 1.65, ARRAY['D']),
    ('Greenbox Capital',        ARRAY['Greenbox'],         ARRAY['GREENBOX CAPITAL','GREENBOX'],          'mca', 4, 90,  1.45, 1.60, ARRAY['C','D'])
ON CONFLICT (name) DO UPDATE SET
    tier = EXCLUDED.tier,
    typical_term_days = EXCLUDED.typical_term_days,
    typical_buy_rate_min = EXCLUDED.typical_buy_rate_min,
    typical_buy_rate_max = EXCLUDED.typical_buy_rate_max,
    paper_grades_accepted = EXCLUDED.paper_grades_accepted,
    aliases = EXCLUDED.aliases,
    industry_signal_keywords = EXCLUDED.industry_signal_keywords,
    updated_at = NOW();

-- Distribution report for the operator running the migration.
DO $$
DECLARE
  _r RECORD;
BEGIN
  RAISE NOTICE '--- known_funding_companies by tier after migration 071 ---';
  FOR _r IN
    SELECT COALESCE(tier::text, '(no tier)') AS t, COUNT(*) AS n
      FROM public.known_funding_companies
     WHERE active = true
     GROUP BY 1
     ORDER BY 1
  LOOP
    RAISE NOTICE '  tier % : % funder(s)', _r.t, _r.n;
  END LOOP;
END $$;

COMMIT;
