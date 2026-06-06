-- 094_email_suppressions.sql — CASL-compliant per-tenant email suppression table.
--
-- Why this exists: 2026-06-05 audit found `data/email_suppressions.csv` is the
-- only suppression store (CSV-only, NOT tenant-scoped). That violates CASL
-- s. 6, which is a per-sender rule — an unsub from SunBiz must NOT silence
-- OASIS AI sends, and vice versa. This table mirrors the CSV but scopes by
-- tenant + brand so multi-brand sending is legally clean.
--
-- The companion /unsubscribe page at oasisai.work/unsubscribe writes here
-- (anonymous POST, server-side service-role insert). The send_gateway
-- consults BOTH this table and the legacy CSV before every send for the
-- transition window — once all existing emails in the wild have rolled past
-- their 30-day TTL, the CSV path can be retired (see ADR follow-up).
--
-- IDEMPOTENCY: re-suppressing the same (email, tenant, brand) tuple is a
-- no-op via the UNIQUE constraint + UPSERT semantics in the API layer.

CREATE TABLE IF NOT EXISTS email_suppressions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       TEXT NOT NULL,
  tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE,
  brand       TEXT,
  reason      TEXT NOT NULL DEFAULT 'unsubscribe',
  source      TEXT NOT NULL DEFAULT 'web_form',
  user_agent  TEXT,
  ip_address  INET,
  added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Per-tenant + per-brand uniqueness. NULLS NOT DISTINCT lets a
  -- "global" suppression (tenant_id=NULL) coexist with brand-specific ones.
  CONSTRAINT email_suppressions_unique UNIQUE NULLS NOT DISTINCT (email, tenant_id, brand)
);

-- Lookup-optimized: should_suppress() queries by email; tenant filter is secondary.
CREATE INDEX IF NOT EXISTS idx_email_suppressions_email_lower
  ON email_suppressions ((lower(email)));

CREATE INDEX IF NOT EXISTS idx_email_suppressions_tenant
  ON email_suppressions (tenant_id);

-- RLS: SELECT scoped to the requesting user's tenant; service role bypasses
-- (used by /api/unsubscribe POST and by every email_engine send path).
ALTER TABLE email_suppressions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS email_suppressions_service_all ON email_suppressions;
CREATE POLICY email_suppressions_service_all ON email_suppressions
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS email_suppressions_tenant_select ON email_suppressions;
CREATE POLICY email_suppressions_tenant_select ON email_suppressions
  FOR SELECT TO authenticated
  USING (
    tenant_id IS NULL
    OR tenant_id IN (
      SELECT tenant_id FROM user_profiles WHERE auth_user_id = auth.uid()
    )
  );

COMMENT ON TABLE email_suppressions IS
  'CASL per-tenant email unsubscribe ledger. Companion to data/email_suppressions.csv during transition window. Source-of-truth for tenant-scoped suppression checks (see scripts/casl_compliance.py).';
