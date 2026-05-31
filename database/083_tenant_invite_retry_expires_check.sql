-- 083_tenant_invite_retry_expires_check.sql
--
-- Tighten the "already redeemed" retry branch of redeem_tenant_invite
-- to honor expires_at. Migration 064 introduced the retry path so
-- that a user who refreshed the invite page after redeeming would
-- get a friendly "already redeemed" response instead of an error. The
-- branch checks token_hash + redeemed_by + revoked_at IS NULL but
-- NOT expires_at. Result: an expired invite that was previously
-- redeemed by user X can be replayed by user X forever.
--
-- Severity is LOW in practice — the retry path doesn't change any
-- state, it just returns the cached tenant_id assignment the user
-- already has. But the security review flagged it as a replay vector
-- and defense-in-depth says expired tokens should be inert no matter
-- which branch they hit.
--
-- This migration overwrites the function with the expires_at gate
-- added in the retry branch. The fresh-redemption logic is unchanged.

CREATE OR REPLACE FUNCTION public.redeem_tenant_invite(
    p_token_hash text,
    p_redeemer_auth_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_invite public.tenant_invites%ROWTYPE;
    v_profile uuid;
    v_email text;
BEGIN
    SELECT email INTO v_email FROM auth.users WHERE id = p_redeemer_auth_id;
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
        -- Retry branch: same user redeeming the same token again. Now
        -- gated on expires_at so an expired token is inert even on the
        -- "you already did this" friendly response. The previous code
        -- omitted this check.
        SELECT * INTO v_invite
        FROM public.tenant_invites
        WHERE token_hash = p_token_hash
          AND redeemed_by = p_redeemer_auth_id
          AND revoked_at IS NULL
          AND expires_at > now()
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
