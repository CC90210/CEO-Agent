-- ============================================================================
-- Migration 076 — per-user integration credentials
--
-- Phase 4 of the SunBiz multi-employee personalization plan (2026-05-29).
--
-- Companion to tenant_integration_credentials (migration 058) but
-- scoped to the (tenant, user) pair instead of just the tenant. Built
-- for the case where the credential MUST be the employee's personally
-- (e.g. Gmail OAuth refresh tokens — emails sent from Alex's seat
-- should come from Alex's address, not Ezra's "submissions@").
--
-- Tenant-shared credentials (TextTorrent, Kixie, Stripe) stay in the
-- tenant_integration_credentials table — single billing surface,
-- single set of API keys. Per-user credentials live HERE.
--
-- Field shape mirrors tenant_integration_credentials exactly so the
-- AES-256-GCM helpers + read patterns transfer 1:1. The only
-- difference is the user_id column + the (tenant, user, service,
-- field_key) uniqueness.
--
-- RLS: users can SELECT/INSERT/UPDATE/DELETE their OWN rows. Admins
-- of the tenant get SELECT for support visibility but cannot decrypt
-- (encrypted_value is only readable by the service-role Node API).
--
-- Idempotent. Re-runnable.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.user_integration_credentials (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- service matches lib/integrations-registry.ts `service` field.
    -- Per-user services (gmail_oauth, slack_oauth, etc.) live here;
    -- shared-billing services (twilio, texttorrent, kixie, stripe)
    -- stay in tenant_integration_credentials.
    service         text NOT NULL,
    -- field_key sub-field for multi-field integrations. For gmail_oauth:
    --   refresh_token   (long-lived; AES-256-GCM encrypted)
    --   access_token    (short-lived; refreshed on demand)
    --   expires_at      (ISO timestamp of access_token expiry)
    --   scope           (OAuth scope granted — typically 'gmail.send')
    --   gmail_address   (the user's actual @gmail.com / @workspace email)
    field_key       text NOT NULL,
    encrypted_value text NOT NULL,
    -- last_tested_* mirror tenant_integration_credentials. Populated
    -- by the per-user integration test endpoint (sends a no-op
    -- gmail.send.draft equivalent or similar).
    last_tested_at  timestamptz,
    last_test_ok    boolean,
    last_test_error text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id, service, field_key)
);

-- Per-(tenant, user) lookup is the dominant access pattern: "give me
-- every credential field for THIS user". Used by the send pipeline's
-- acted_by_user_id resolution.
CREATE INDEX IF NOT EXISTS idx_user_integration_credentials_user
    ON public.user_integration_credentials (tenant_id, user_id, service);

-- Updated-at trigger reuses the canonical helper (same function used
-- by tenant_integration_credentials per migration 058).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_user_integration_credentials_updated_at'
  ) THEN
    CREATE TRIGGER trg_user_integration_credentials_updated_at
        BEFORE UPDATE ON public.user_integration_credentials
        FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();
  END IF;
END $$;

ALTER TABLE public.user_integration_credentials ENABLE ROW LEVEL SECURITY;

-- RLS policies. Drop-and-recreate pattern so re-runs land cleanly even
-- if the policy spec changes later.

DROP POLICY IF EXISTS user_integration_credentials_self_select ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_select
    ON public.user_integration_credentials FOR SELECT
    USING (
        -- The owning user can read their own rows.
        user_id = auth.uid()
        -- Tenant admins can see WHICH rows exist for visibility (support
        -- debugging) but encrypted_value stays out of reach unless the
        -- service-role Node API decrypts it.
        OR EXISTS (
          SELECT 1 FROM public.user_profiles up
           WHERE up.auth_user_id = auth.uid()
             AND up.tenant_id = user_integration_credentials.tenant_id
             AND up.is_owner = true
        )
    );

DROP POLICY IF EXISTS user_integration_credentials_self_insert ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_insert
    ON public.user_integration_credentials FOR INSERT
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS user_integration_credentials_self_update ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_update
    ON public.user_integration_credentials FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS user_integration_credentials_self_delete ON public.user_integration_credentials;
CREATE POLICY user_integration_credentials_self_delete
    ON public.user_integration_credentials FOR DELETE
    USING (user_id = auth.uid());

COMMENT ON TABLE public.user_integration_credentials IS
    'Per-(tenant, user) encrypted credential vault. Mirrors '
    'tenant_integration_credentials but scoped to a specific employee '
    'rather than the tenant. Use this for credentials that MUST be the '
    'employee personally (Gmail OAuth, future personal Slack tokens, '
    'etc.). Tenant-shared API keys stay in tenant_integration_credentials.';
