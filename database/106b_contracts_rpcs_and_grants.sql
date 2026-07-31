-- ============================================================
-- Migration 106b: contract signing RPCs + grants — RUN BY HAND
-- ============================================================
-- ⚠️ DO NOT run this through scripts/apply_migration.py. It will refuse, and
-- correctly so: this file contains GRANT, REVOKE and `UPDATE ... SET`, all of
-- which are on that tool's hard blocklist. Those statements are meant to have a
-- human read them before they touch production.
--
-- HOW TO RUN: Supabase Dashboard → project phctllmtsogkovoilwos → SQL Editor →
-- paste this whole file → Run. Idempotent (CREATE OR REPLACE + re-issued
-- grants), so re-running is safe.
--
-- PREREQUISITE: 106_contracts_and_signatures.sql must be applied first. Until
-- this file runs, the contract feature is INERT — RLS is on, no anon policy
-- exists, and no RPC exists. That is the correct failure mode: closed, not open.
--
-- WHY RPCs AND NOT POLICIES. A signer is anonymous; they authenticate with a
-- token in a URL, which no RLS policy can evaluate safely on its own. Worse,
-- RLS cannot restrict which COLUMNS an UPDATE writes, so an anon UPDATE policy
-- on `contracts` would let a signer rewrite `terms_body` after signing it.
-- These two SECURITY DEFINER functions are the entire public surface: they take
-- the token, authorise, and write only the columns they are allowed to.
-- search_path is pinned per migration 103.
-- ============================================================

-- ── RPC 1: fetch a contract for signing, by token ────────────────────────────
--
-- Returns ONLY what the signing page needs. Never returns sign_token, lead_id,
-- tenant_id or created_by — a public page has no business holding those.
-- Stamps first_viewed_at so 'viewed' is real telemetry, not a status nobody sets.

CREATE OR REPLACE FUNCTION public.get_contract_for_signing(p_token text)
RETURNS TABLE (
    contract_id   uuid,
    client_name   text,
    client_email  text,
    contract_type text,
    terms_body    text,
    status        text,
    expires_at    timestamptz,
    signed_at     timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE v_id uuid;
BEGIN
    -- Silent empty rather than an error: never confirm whether a token shape
    -- or a specific token exists. An enumerator learns nothing from either.
    IF p_token IS NULL OR length(p_token) < 32 THEN
        RETURN;
    END IF;

    SELECT c.id INTO v_id FROM public.contracts c WHERE c.sign_token = p_token;
    IF v_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE public.contracts c
       SET first_viewed_at = COALESCE(c.first_viewed_at, now()),
           status = CASE WHEN c.status = 'sent' THEN 'viewed' ELSE c.status END,
           updated_at = now()
     WHERE c.id = v_id;

    RETURN QUERY
    SELECT c.id, c.client_name, c.client_email, c.contract_type,
           c.terms_body, c.status, c.expires_at, c.signed_at
      FROM public.contracts c
     WHERE c.id = v_id;
END;
$fn$;

-- ── RPC 2: execute the signature ─────────────────────────────────────────────
--
-- The only write path a signer has. Cannot touch terms_body, cannot re-sign,
-- refuses expired or voided contracts.

CREATE OR REPLACE FUNCTION public.sign_contract(
    p_token           text,
    p_signer_name     text,
    p_signer_email    text,
    p_signature_png   text,
    p_signature_typed text,
    p_ip              text,
    p_user_agent      text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    c        public.contracts%ROWTYPE;
    v_sig_id uuid;
BEGIN
    IF p_token IS NULL OR length(p_token) < 32 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'invalid_token');
    END IF;

    -- FOR UPDATE: two tabs hitting "Complete Signing" simultaneously must not
    -- both pass the status check and insert two signature rows.
    SELECT * INTO c FROM public.contracts WHERE sign_token = p_token FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'invalid_token');
    END IF;

    IF c.status = 'signed' THEN
        -- Idempotent, not an error: a double-submit must not create a second
        -- signature row or fire the onboarding trigger twice.
        RETURN jsonb_build_object('ok', true, 'already_signed', true,
                                  'contract_id', c.id, 'signed_at', c.signed_at);
    END IF;
    IF c.status = 'void' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'contract_void');
    END IF;
    IF c.expires_at IS NOT NULL AND c.expires_at < now() THEN
        UPDATE public.contracts SET status = 'expired', updated_at = now() WHERE id = c.id;
        RETURN jsonb_build_object('ok', false, 'error', 'contract_expired');
    END IF;
    IF coalesce(trim(p_signer_name), '') = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'signer_name_required');
    END IF;
    IF coalesce(p_signature_png, '') = ''
       AND coalesce(trim(p_signature_typed), '') = '' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'signature_required');
    END IF;

    INSERT INTO public.client_signatures (
        contract_id, signer_name, signer_email, signature_png, signature_typed,
        signature_kind, ip_address, user_agent, terms_sha256
    ) VALUES (
        c.id,
        trim(p_signer_name),
        lower(trim(coalesce(nullif(p_signer_email, ''), c.client_email))),
        nullif(p_signature_png, ''),
        nullif(trim(coalesce(p_signature_typed, '')), ''),
        CASE WHEN coalesce(p_signature_png, '') <> '' THEN 'drawn' ELSE 'typed' END,
        -- A malformed IP must not abort a signing that is otherwise valid;
        -- log NULL and carry on. Losing one audit field beats losing the deal.
        (CASE WHEN p_ip ~ '^[0-9a-fA-F:.]+$' THEN p_ip::inet ELSE NULL END),
        left(coalesce(p_user_agent, ''), 500),
        encode(digest(c.terms_body, 'sha256'), 'hex')
    ) RETURNING id INTO v_sig_id;

    UPDATE public.contracts
       SET status = 'signed', signed_at = now(), updated_at = now()
     WHERE id = c.id;

    RETURN jsonb_build_object('ok', true, 'contract_id', c.id,
                              'signature_id', v_sig_id, 'lead_id', c.lead_id);
END;
$fn$;

-- ── Grants ───────────────────────────────────────────────────────────────────
--
-- EXECUTE on the two functions is all anon gets. That is safe precisely because
-- each function authorises by token and returns a fixed shape.

GRANT EXECUTE ON FUNCTION public.get_contract_for_signing(text) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.sign_contract(text, text, text, text, text, text, text)
    TO anon, authenticated;

-- Table privileges stay stripped. Migration 104 removed anon's dangerous grants
-- fleet-wide; this re-asserts it for the two new tables so a future
-- ALTER DEFAULT PRIVILEGES change cannot quietly hand them back.
REVOKE ALL ON public.contracts         FROM anon;
REVOKE ALL ON public.client_signatures FROM anon;

-- ── Verify (run these after, expect the stated results) ──────────────────────
-- SELECT proname, prosecdef, proconfig FROM pg_proc
--   WHERE proname IN ('get_contract_for_signing','sign_contract');
--   -- expect prosecdef=true and proconfig containing search_path=public,pg_temp
--
-- SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
--   WHERE relname IN ('contracts','client_signatures');
--   -- expect true / true for both
--
-- SELECT grantee, privilege_type FROM information_schema.role_table_grants
--   WHERE table_name IN ('contracts','client_signatures') AND grantee = 'anon';
--   -- expect ZERO rows
