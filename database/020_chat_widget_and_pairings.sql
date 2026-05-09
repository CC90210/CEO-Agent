-- Migration 020 — Chat Widget + Local Bridge Pairings
--
-- Adds the data layer for the in-dashboard chat widget that replaces the
-- Telegram bridge / Codex companion CLI for client-facing use.
--
-- Tables:
--   agent_model_config  — per-tenant per-agent (provider, model, encrypted API key)
--   chat_sessions       — one row per conversation
--   chat_messages       — turn-by-turn log
--   bridge_pairings     — Phase-2 pairing tokens for local-machine daemon
--
-- Encryption: API keys are encrypted in Node (aes-256-gcm) using
-- BRAVO_FIELD_ENCRYPTION_KEY (env). Postgres only stores the opaque
-- ciphertext as text. No pgcrypto round-trip — that path is fragile via
-- supabase-js bytea serialization.
--
-- Apply via: python scripts/apply_migration.py database/020_chat_widget_and_pairings.sql

BEGIN;

-- ============================================================================
-- 1. agent_model_config — per-tenant per-agent provider + key
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.agent_model_config (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    agent_key       text NOT NULL,                                -- bravo | maven | atlas | aura | hermes | lumen
    provider        text NOT NULL,                                -- openrouter | anthropic | openai | google | ollama
    model           text NOT NULL,                                -- e.g. "claude-opus-4-7" / "gpt-5.4" / "gemini-2.5-pro" / "llama3.3:70b"
    encrypted_api_key text,                                       -- iv:tag:ciphertext (base64), encrypted Node-side. For provider="ollama" this stores the local endpoint URL instead of an API key (e.g. "http://localhost:11434/v1")
    system_prompt_override text,                                  -- optional per-tenant overlay; nullable
    enabled         boolean NOT NULL DEFAULT true,
    last_used_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, agent_key)
);

CREATE INDEX IF NOT EXISTS idx_agent_model_config_tenant
    ON public.agent_model_config (tenant_id);

CREATE TRIGGER trg_agent_model_config_updated_at
    BEFORE UPDATE ON public.agent_model_config
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

ALTER TABLE public.agent_model_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY amc_tenant_select ON public.agent_model_config
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY amc_tenant_write ON public.agent_model_config
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 2. chat_sessions — one per conversation thread
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    user_id         uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    agent_key       text NOT NULL,
    title           text,                                          -- auto-generated summary
    provider        text NOT NULL,
    model           text NOT NULL,
    total_input_tokens  integer NOT NULL DEFAULT 0,
    total_output_tokens integer NOT NULL DEFAULT 0,
    estimated_cost_usd  numeric(12,6) NOT NULL DEFAULT 0,
    archived        boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant
    ON public.chat_sessions (tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent
    ON public.chat_sessions (tenant_id, agent_key, updated_at DESC);

CREATE TRIGGER trg_chat_sessions_updated_at
    BEFORE UPDATE ON public.chat_sessions
    FOR EACH ROW EXECUTE FUNCTION public.touch_user_profiles_updated_at();

ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY cs_tenant_select ON public.chat_sessions
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY cs_tenant_write ON public.chat_sessions
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 3. chat_messages — turn log
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.chat_messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    role            text NOT NULL,                                 -- user | assistant | system | tool
    content         text NOT NULL,
    input_tokens    integer,
    output_tokens   integer,
    latency_ms      integer,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON public.chat_messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_tenant
    ON public.chat_messages (tenant_id, created_at DESC);

ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY cm_tenant_select ON public.chat_messages
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY cm_tenant_write ON public.chat_messages
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

-- ============================================================================
-- 4. bridge_pairings — Phase-2 local-daemon pairing tokens
-- ============================================================================
-- Each tenant can pair one or more local machines (laptop, work desktop) to
-- their dashboard. The setup wizard generates a one-time code, the local
-- daemon redeems it for a long-lived bearer token, and from then on the
-- daemon proves itself with that token over WebSocket / HTTPS.
CREATE TABLE IF NOT EXISTS public.bridge_pairings (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    user_id             uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    label               text NOT NULL,                             -- "CC's MacBook"
    pairing_code        text UNIQUE,                               -- 6-digit setup-wizard code, NULL after redemption
    pairing_code_expires_at timestamptz,
    bridge_token_hash   text,                                      -- sha256 hex of the long-lived bearer
    machine_fingerprint text,                                      -- OS + hostname + cpu fingerprint
    last_seen_at        timestamptz,
    last_seen_ip        inet,
    revoked_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bridge_pairings_tenant
    ON public.bridge_pairings (tenant_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bridge_pairings_pairing_code
    ON public.bridge_pairings (pairing_code) WHERE pairing_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bridge_pairings_token_hash
    ON public.bridge_pairings (bridge_token_hash) WHERE bridge_token_hash IS NOT NULL;

ALTER TABLE public.bridge_pairings ENABLE ROW LEVEL SECURITY;

CREATE POLICY bp_tenant_select ON public.bridge_pairings
    FOR SELECT USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY bp_tenant_write ON public.bridge_pairings
    FOR ALL USING (
        tenant_id IN (
            SELECT tenant_id FROM public.user_profiles
            WHERE auth_user_id = auth.uid()
        )
    );

COMMIT;
