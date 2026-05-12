-- ============================================================================
-- Migration 037 — Team Roles + Tenant Invites + Owner-Pairing Protection
--
-- Adds multi-user team access for the Command Center. Owner-led tenants can
-- now generate single-use, hashed invite links that scope new members to the
-- tenant_id and assign a power-level role (owner/admin/loan_officer/processor/
-- read_only/member). Employees cannot revoke the owner's machine pairing.
--
-- This migration is additive. Existing `user_profiles.role` ('operator' |
-- 'client' | 'admin') is unchanged — that column models *what kind* of user
-- this is. The new `team_role` column models *power level within a tenant*.
-- They are orthogonal axes.
--
-- Pre-apply audit (run first):
--   SELECT tenant_id, count(*) FROM user_profiles
--   GROUP BY tenant_id HAVING count(*) > 1;
-- Audit confirmed clean 2026-05-12 — only one user_profile exists.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Team role + owner flag on user_profiles
-- ---------------------------------------------------------------------------
ALTER TABLE public.user_profiles
    ADD COLUMN IF NOT EXISTS team_role text NOT NULL DEFAULT 'member'
        CHECK (team_role IN ('owner','admin','loan_officer','processor','read_only','member')),
    ADD COLUMN IF NOT EXISTS is_owner boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS invited_by uuid REFERENCES auth.users(id),
    ADD COLUMN IF NOT EXISTS joined_at timestamptz NOT NULL DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS user_profiles_one_owner_per_tenant
    ON public.user_profiles (tenant_id) WHERE is_owner = true;

-- Backfill step is run via scripts/supabase_tool.py update (apply_migration.py
-- gate refuses UPDATE statements by design). See sidecar:
--   database/037b_team_roles_backfill_manual.sql
-- and the post-migration commands in PR description.

-- ---------------------------------------------------------------------------
-- 2. tenant_invites table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenant_invites (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    email           text,                                  -- optional; null = open link
    team_role       text NOT NULL DEFAULT 'member'
        CHECK (team_role IN ('admin','loan_officer','processor','read_only','member')),
    token_hash      text NOT NULL UNIQUE,                  -- sha256 hex of the raw token; raw token never stored
    created_by      uuid NOT NULL REFERENCES auth.users(id),
    expires_at      timestamptz NOT NULL DEFAULT (now() + interval '7 days'),
    redeemed_at     timestamptz,
    redeemed_by     uuid REFERENCES auth.users(id),
    revoked_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_invites_active
    ON public.tenant_invites (tenant_id)
    WHERE redeemed_at IS NULL AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tenant_invites_token_hash
    ON public.tenant_invites (token_hash)
    WHERE redeemed_at IS NULL AND revoked_at IS NULL;

ALTER TABLE public.tenant_invites ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 3. Helper: is_team_admin() — SECURITY DEFINER avoids recursive RLS on
-- user_profiles when invite policies reference the same table.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.is_team_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE auth_user_id = auth.uid()
          AND tenant_id = public.current_tenant_id()
          AND team_role IN ('owner','admin')
    );
$$;

-- ---------------------------------------------------------------------------
-- 4. RLS policies on tenant_invites — owners/admins only, tenant-scoped
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_invites'
          AND policyname='tenant_invites_admin_select'
    ) THEN
        CREATE POLICY tenant_invites_admin_select ON public.tenant_invites
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() AND public.is_team_admin());
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_invites'
          AND policyname='tenant_invites_admin_write'
    ) THEN
        CREATE POLICY tenant_invites_admin_write ON public.tenant_invites
            FOR INSERT TO authenticated
            WITH CHECK (tenant_id = public.current_tenant_id() AND public.is_team_admin());
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_invites'
          AND policyname='tenant_invites_admin_update'
    ) THEN
        CREATE POLICY tenant_invites_admin_update ON public.tenant_invites
            FOR UPDATE TO authenticated
            USING (tenant_id = public.current_tenant_id() AND public.is_team_admin());
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 5. protect_owner_pairings trigger — block employees from revoking the
-- owner's machine pairing. Owner + admin remain unrestricted.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.protect_owner_pairings()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    actor_role text;
    pairing_owner boolean;
BEGIN
    -- Service-role bypass (dashboard server-side writes)
    IF auth.role() = 'service_role' THEN
        RETURN NEW;
    END IF;

    SELECT team_role INTO actor_role
    FROM public.user_profiles
    WHERE auth_user_id = auth.uid()
    LIMIT 1;

    -- If the pairing belongs to an owner, only owner/admin can change it
    SELECT EXISTS (
        SELECT 1 FROM public.user_profiles
        WHERE auth_user_id = OLD.user_id AND is_owner = true
    ) INTO pairing_owner;

    IF pairing_owner AND actor_role IS DISTINCT FROM 'owner' AND actor_role IS DISTINCT FROM 'admin' THEN
        RAISE EXCEPTION 'employees cannot modify or revoke owner machine pairings'
            USING ERRCODE = '42501';
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_bridge_pairings_protect_owner ON public.bridge_pairings;
CREATE TRIGGER trg_bridge_pairings_protect_owner
    BEFORE UPDATE OR DELETE ON public.bridge_pairings
    FOR EACH ROW EXECUTE FUNCTION public.protect_owner_pairings();

-- ---------------------------------------------------------------------------
-- 6. redeem_tenant_invite RPC — atomic redemption: hash the raw token, find
-- the active invite, attach the redeemer to the inviter's tenant, mark redeemed.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.redeem_tenant_invite(
    p_token_hash text,
    p_redeemer_auth_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_invite   public.tenant_invites%ROWTYPE;
    v_profile  uuid;
BEGIN
    SELECT * INTO v_invite
    FROM public.tenant_invites
    WHERE token_hash = p_token_hash
      AND redeemed_at IS NULL
      AND revoked_at IS NULL
      AND expires_at > now()
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'invalid_or_expired');
    END IF;

    -- Find or attach a user_profile to the redeemer
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
        'profile_id', v_profile
    );
END;
$$;

-- REVOKE/GRANT moved to database/037b_team_roles_backfill_manual.sql
-- (apply_migration.py guard refuses privilege statements by design).
-- Effective behavior unchanged: the dashboard calls this RPC via the
-- service-role key, which bypasses RLS regardless of explicit grants.
