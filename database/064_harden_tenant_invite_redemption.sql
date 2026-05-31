-- ============================================================================
-- Migration 064 — Harden tenant invite redemption
--
-- Production hardening for SunBiz team portal invites:
--   1. Pinned-email invites can only be redeemed by an auth user whose email
--      matches tenant_invites.email.
--   2. A retry by the same already-redeemed user returns ok=true instead of
--      failing as invalid_or_expired. This makes browser/network retries safe
--      after password creation.
--
-- The raw token is still never stored; callers pass SHA-256(token).
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.redeem_tenant_invite(
    p_token_hash text,
    p_redeemer_auth_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_invite   public.tenant_invites%ROWTYPE;
    v_profile  uuid;
    v_email    text;
BEGIN
    SELECT email INTO v_email
    FROM auth.users
    WHERE id = p_redeemer_auth_id;

    IF v_email IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'auth_user_not_found');
    END IF;

    SELECT * INTO v_invite
    FROM public.tenant_invites
    WHERE token_hash = p_token_hash
      AND redeemed_at IS NULL
      AND revoked_at IS NULL
      AND expires_at > now()
    FOR UPDATE;

    IF NOT FOUND THEN
        SELECT * INTO v_invite
        FROM public.tenant_invites
        WHERE token_hash = p_token_hash
          AND redeemed_by = p_redeemer_auth_id
          AND revoked_at IS NULL
        LIMIT 1;

        IF FOUND THEN
            SELECT id INTO v_profile
            FROM public.user_profiles
            WHERE auth_user_id = p_redeemer_auth_id;

            RETURN jsonb_build_object(
                'ok', true,
                'tenant_id', v_invite.tenant_id,
                'team_role', v_invite.team_role,
                'profile_id', v_profile,
                'already_redeemed', true
            );
        END IF;

        RETURN jsonb_build_object('ok', false, 'error', 'invalid_or_expired');
    END IF;

    IF v_invite.email IS NOT NULL
       AND lower(trim(v_invite.email)) <> lower(trim(v_email)) THEN
        RETURN jsonb_build_object('ok', false, 'error', 'email_mismatch');
    END IF;

    -- Find or attach a user_profile to the redeemer.
    SELECT id INTO v_profile
    FROM public.user_profiles
    WHERE auth_user_id = p_redeemer_auth_id;

    IF NOT FOUND THEN
        INSERT INTO public.user_profiles (
            auth_user_id, email, full_name, tenant_id,
            team_role, invited_by, joined_at, is_owner
        )
        SELECT
            p_redeemer_auth_id,
            COALESCE(u.email, 'pending+'||p_redeemer_auth_id||'@oasis.invalid'),
            COALESCE(u.raw_user_meta_data->>'full_name', u.email, 'New member'),
            v_invite.tenant_id,
            v_invite.team_role,
            v_invite.created_by,
            now(),
            false
        FROM auth.users u
        WHERE u.id = p_redeemer_auth_id
        RETURNING id INTO v_profile;
    ELSE
        UPDATE public.user_profiles
        SET tenant_id = v_invite.tenant_id,
            team_role = v_invite.team_role,
            invited_by = v_invite.created_by,
            joined_at = COALESCE(joined_at, now()),
            is_owner = false
        WHERE id = v_profile;
    END IF;

    UPDATE public.tenant_invites
    SET redeemed_at = now(),
        redeemed_by = p_redeemer_auth_id
    WHERE id = v_invite.id;

    RETURN jsonb_build_object(
        'ok', true,
        'tenant_id', v_invite.tenant_id,
        'team_role', v_invite.team_role,
        'profile_id', v_profile,
        'already_redeemed', false
    );
END;
$$;

COMMENT ON FUNCTION public.redeem_tenant_invite(text, uuid) IS
  'Redeems a tenant invite atomically. Enforces pinned invite email against '
  'auth.users.email and returns ok=true for same-user retry after successful '
  'redemption.';

COMMIT;
