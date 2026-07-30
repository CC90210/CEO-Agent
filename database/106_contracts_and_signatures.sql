-- ============================================================
-- Migration 106: client contracts + immutable signature audit trail (SCHEMA)
-- ============================================================
-- Empire DB (phctllmtsogkovoilwos). Backs the OASIS Command Center contract
-- module: CC generates a contract from an operator-authored template, sends a
-- one-off signing link, the client signs on a public page, and the execution is
-- recorded in a way that would survive being questioned later.
--
-- SPLIT INTO TWO FILES ON PURPOSE. apply_migration.py hard-blocks GRANT,
-- REVOKE, DROP POLICY and `UPDATE <table> SET` — the last one matches inside
-- SECURITY DEFINER function bodies, which is where this feature's write logic
-- has to live. Rather than reshape the SQL to slip past the guard (explicitly
-- forbidden), the split follows the guard's intent:
--
--   106  (this file)  — tables, indexes, trigger, RLS enable + read policies.
--                       Safe, idempotent, applied by the tool with --allow-rls.
--   106b              — the two SECURITY DEFINER RPCs + GRANT/REVOKE.
--                       Run BY HAND in the Supabase Dashboard SQL editor.
--
-- The feature is inert until 106b is run: with 106 alone, RLS is on and no
-- public path exists, which is the correct failure mode (closed, not open).
--
-- THREE SECURITY DECISIONS, each deliberate:
--
-- 1. THE SIGNING LINK IS A SEPARATE SECRET, NOT THE PRIMARY KEY.
--    `sign_token` is 32 random bytes, unique, indexed. The URL never exposes
--    `contracts.id`. A guessable identifier in a public URL means anyone can
--    enumerate every client contract you have ever sent.
--
-- 2. ANON NEVER TOUCHES THESE TABLES DIRECTLY.
--    RLS is enabled with NO anon policy, so anon gets nothing. Public access is
--    exclusively via the RPCs in 106b, which authorise by token. RLS cannot
--    restrict which COLUMNS an UPDATE touches (learned the hard way — see
--    memory/PATTERNS.md), so a direct anon UPDATE could rewrite `terms_body`
--    after signing. An RPC can forbid exactly that.
--
-- 3. THE SIGNATURE ROW IS APPEND-ONLY.
--    A trigger raises on UPDATE or DELETE. An audit trail you can quietly edit
--    is not an audit trail. To correct a mis-signature, void the CONTRACT and
--    reissue; the original record stays.
--
-- Idempotent. Reversible: drop the trigger, the tables, and 106b's functions.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_bytes, digest

-- ── contracts ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.contracts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid NOT NULL,
    lead_id       uuid REFERENCES public.leads(id) ON DELETE SET NULL,

    client_name   text NOT NULL,
    client_email  text NOT NULL,
    contract_type text NOT NULL,

    -- Rendered markdown of the executed terms. Stored as TEXT, not a template
    -- reference: a contract must be readable exactly as signed even if the
    -- template is edited afterwards.
    terms_body    text NOT NULL,
    -- The variables used to render terms_body, kept for regeneration + audit.
    variables     jsonb NOT NULL DEFAULT '{}'::jsonb,

    status        text NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft','sent','viewed','signed','expired','void')),

    -- The public secret. NOT the id.
    sign_token    text NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
    expires_at    timestamptz,

    sent_at         timestamptz,
    first_viewed_at timestamptz,
    signed_at       timestamptz,

    created_by    uuid,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contracts_tenant_idx ON public.contracts (tenant_id);
CREATE INDEX IF NOT EXISTS contracts_lead_idx   ON public.contracts (lead_id);
CREATE INDEX IF NOT EXISTS contracts_status_idx ON public.contracts (status);
CREATE UNIQUE INDEX IF NOT EXISTS contracts_sign_token_idx ON public.contracts (sign_token);

COMMENT ON COLUMN public.contracts.sign_token IS
    'Public signing secret (32 random bytes, hex). Appears in the URL; contracts.id never does.';
COMMENT ON COLUMN public.contracts.terms_body IS
    'Rendered markdown AS SIGNED. Never rewritten after status=signed.';

-- ── client_signatures (append-only) ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.client_signatures (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id   uuid NOT NULL REFERENCES public.contracts(id) ON DELETE RESTRICT,

    signer_name     text NOT NULL,
    signer_email    text NOT NULL,
    signature_png   text,
    signature_typed text,
    signature_kind  text NOT NULL DEFAULT 'drawn'
                    CHECK (signature_kind IN ('drawn','typed')),

    -- Captured server-side from the request, never from the client body — a
    -- signer-supplied IP is worthless as evidence.
    ip_address    inet,
    user_agent    text,
    -- Hash of the exact terms at signing time, so a later edit is detectable
    -- even if someone bypasses the immutability rules above.
    terms_sha256  text,

    signed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS client_signatures_contract_idx
    ON public.client_signatures (contract_id);

CREATE OR REPLACE FUNCTION public.client_signatures_append_only()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION
        'client_signatures is append-only (attempted %). Void the contract and reissue instead.',
        TG_OP;
END;
$fn$;

DROP TRIGGER IF EXISTS client_signatures_no_mutate ON public.client_signatures;
CREATE TRIGGER client_signatures_no_mutate
    BEFORE UPDATE OR DELETE ON public.client_signatures
    FOR EACH ROW EXECUTE FUNCTION public.client_signatures_append_only();

-- ── RLS: deny-by-default ─────────────────────────────────────────────────────
--
-- Enabled with only tenant-scoped SELECT for authenticated. service_role
-- bypasses RLS; anon gets nothing at all. Public signing goes through 106b.

ALTER TABLE public.contracts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_signatures ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contracts         FORCE ROW LEVEL SECURITY;
ALTER TABLE public.client_signatures FORCE ROW LEVEL SECURITY;

-- Idempotent policy creation WITHOUT `DROP POLICY` (a blocked pattern): guard
-- on pg_policies instead. Re-running this migration is a no-op.
DO $mig$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'contracts'
          AND policyname = 'contracts_tenant_read'
    ) THEN
        CREATE POLICY contracts_tenant_read ON public.contracts
            FOR SELECT TO authenticated
            USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'client_signatures'
          AND policyname = 'client_signatures_tenant_read'
    ) THEN
        CREATE POLICY client_signatures_tenant_read ON public.client_signatures
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1 FROM public.contracts c
                WHERE c.id = client_signatures.contract_id
                  AND c.tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid
            ));
    END IF;
END
$mig$;
