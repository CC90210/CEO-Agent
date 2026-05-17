-- ============================================================================
-- Migration 051 — preview_tenant_invite RPC
--
-- Public-readable preview of an invite. Used by /invite/[token] landing
-- page to render "Join <Tenant Name> as <Role>" before the recipient
-- actually authenticates.
--
-- Why a dedicated RPC: tenant_invites RLS is admin-only, so the
-- anonymous landing page can't SELECT directly. SECURITY DEFINER lets
-- this function look up by token_hash and return just the safe fields
-- (tenant display name + role + expiry) without exposing every row to
-- every anon caller.
--
-- Safety: only callable with the SHA-256 hash of the raw token (same
-- hash the redeem RPC checks). An attacker without the raw token can't
-- enumerate active invites — the lookup is keyed on the hash, not the
-- invite UUID. Plus the result excludes created_by, the actual hash,
-- and any other fields useful for impersonation. Expired / revoked /
-- already-redeemed invites return null so the landing page can render
-- a clean "this invite has expired" state.
--
-- Tied to migration 037 (tenant_invites table + redeem_tenant_invite
-- RPC). Independently re-runnable; CREATE OR REPLACE.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.preview_tenant_invite(p_token_hash text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_invite public.tenant_invites%ROWTYPE;
    v_tenant_name text;
BEGIN
    SELECT * INTO v_invite
    FROM public.tenant_invites
    WHERE token_hash = p_token_hash
      AND redeemed_at IS NULL
      AND revoked_at IS NULL
      AND expires_at > now()
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT name INTO v_tenant_name
    FROM public.tenants
    WHERE id = v_invite.tenant_id;

    RETURN jsonb_build_object(
        'tenant_id', v_invite.tenant_id,
        'tenant_name', COALESCE(v_tenant_name, 'a workspace'),
        'team_role', v_invite.team_role,
        'expires_at', v_invite.expires_at,
        'email_pinned', v_invite.email
    );
END;
$$;

COMMENT ON FUNCTION public.preview_tenant_invite(text) IS
  'Public preview for the /invite/<token> landing page (Phase A, '
  'master multi-tenant infra plan, 2026-05-17). Returns tenant name '
  '+ role + expiry for a still-valid invite, NULL otherwise. Safe to '
  'call anonymously because the lookup requires the SHA-256 hash of '
  'the raw token (an attacker without the link cannot enumerate).';

COMMIT;
