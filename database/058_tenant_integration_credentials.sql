-- ============================================================
-- 058_tenant_integration_credentials.sql
-- ============================================================
-- Per-tenant, AES-256-GCM-encrypted credential store for integrations
-- not covered by agent_model_config (which is AI-provider-specific).
--
-- Covers: Twilio (account_sid + auth_token + from_number), TextTorrent
-- (api_key), n8n outbound webhook (url + secret), SMTP (host + user +
-- password + from), Stripe (publishable + secret), Late/Zernio
-- (api_key), any future paste-an-API-key integration.
--
-- Why a new table instead of extending agent_model_config:
--   - agent_model_config keys on `agent_key` (bravo/maven/atlas) — semantic
--     mismatch with non-AI integrations like Twilio.
--   - Some integrations require multiple fields (Twilio = SID + token +
--     from-number). A row-per-field shape (service, field_key) lets one
--     integration store many fields without schema churn.
--
-- Encryption: ciphertext stored in `encrypted_value`. The Node helper at
-- lib/field-encryption.ts is the canonical encrypter; same AES-256-GCM
-- format as agent_model_config.encrypted_api_key. Decryption only
-- happens server-side in API routes / send-path helpers — never
-- returned to the client.
--
-- Apply via: python scripts/apply_migration.py database/058_tenant_integration_credentials.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS public.tenant_integration_credentials (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    -- service matches lib/integrations-registry.ts `service` field
    -- (twilio, texttorrent, n8n, smtp, stripe, etc.).
    service         text NOT NULL,
    -- field_key is the sub-field for multi-field integrations:
    --   twilio       → account_sid | auth_token | from_number
    --   smtp         → host | port | user | password | from_address
    --   n8n          → outbound_url | outbound_secret
    --   texttorrent  → api_key | from_number
    --   single-field integrations use field_key='api_key'.
    field_key       text NOT NULL,
    encrypted_value text NOT NULL,
    -- last_tested_* track the most recent integration test result so
    -- the settings panel can show "Verified 5m ago" / "Failed: invalid
    -- token". Populated by /api/integrations/credentials/test.
    last_tested_at  timestamptz,
    last_test_ok    boolean,
    last_test_error text,
    created_by      uuid REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, service, field_key)
);

-- Per-tenant lookup: "give me every credential field for tenant X" is
-- the most common shape (the settings page renders all at once).
CREATE INDEX IF NOT EXISTS idx_tenant_integration_credentials_tenant
    ON public.tenant_integration_credentials (tenant_id, service);

-- Service-scoped lookup for the send-path helpers
-- (getTenantCredential(tenantId, 'twilio', 'auth_token')).
CREATE INDEX IF NOT EXISTS idx_tenant_integration_credentials_service
    ON public.tenant_integration_credentials (tenant_id, service, field_key);

-- Updated-at trigger reuses the canonical helper.
CREATE TRIGGER trg_tenant_integration_credentials_updated_at
    BEFORE UPDATE ON public.tenant_integration_credentials
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

ALTER TABLE public.tenant_integration_credentials ENABLE ROW LEVEL SECURITY;

-- RLS policy: tenant members can read presence (has-a-row) but
-- decryption is not exposed via PostgREST — only the service-role
-- Node API can read encrypted_value. The settings page calls a Node
-- route that uses service-role + the field-encryption helper.
CREATE POLICY tenant_integration_credentials_select
    ON public.tenant_integration_credentials FOR SELECT
    USING (tenant_id = public.current_tenant_id());

CREATE POLICY tenant_integration_credentials_insert
    ON public.tenant_integration_credentials FOR INSERT
    WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY tenant_integration_credentials_update
    ON public.tenant_integration_credentials FOR UPDATE
    USING (tenant_id = public.current_tenant_id())
    WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY tenant_integration_credentials_delete
    ON public.tenant_integration_credentials FOR DELETE
    USING (tenant_id = public.current_tenant_id());

COMMENT ON TABLE public.tenant_integration_credentials IS
    'Per-tenant encrypted credentials for integrations not covered by '
    'agent_model_config. One row per (service, field_key). Ciphertext '
    'is opaque to PostgREST — decryption only happens in Node API '
    'routes using lib/field-encryption.ts.';
