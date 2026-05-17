-- ============================================================================
-- Migration 053 — tenant_audit_log + log_tenant_event() RPC
--
-- Phase D of the master multi-tenant infra plan (2026-05-17). SOC2-style
-- trail of high-stakes mutations: invite create/revoke, member role
-- change, owner-pairing change, agent-config writes, override approvals.
--
-- Schema choices:
--   - Single fact table indexed on (tenant_id, created_at) for the
--     admin-facing /settings/audit-log view. Most queries are
--     "show me this tenant's recent events" — a covering tenant_id +
--     created_at index serves them cleanly.
--   - before/after as jsonb so any callsite can dump the relevant slice
--     of state without us pre-defining columns. Avoids the "schema
--     creep per audit event type" trap.
--   - ip_hash (not raw IP) for privacy. Match the same hashing scheme
--     used by /api/track/open/[id] (djb2 hex) so a single user's
--     activity is correlatable without exposing the raw IP.
--   - action_type is open text (not an enum) so adding new event types
--     doesn't require a migration. Conventions documented in code.
--
-- RLS posture:
--   - admins read their own tenant's rows
--   - writes only via the SECURITY DEFINER RPC log_tenant_event() so
--     application code can't forge actor_user_id or backdate created_at
--
-- Retention: handled by a separate prune cron (TODO Phase D.x — daily
-- delete WHERE created_at < now() - interval '1 year'). The table
-- itself doesn't enforce retention.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.tenant_audit_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    actor_user_id   uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_email     text,
    action_type     text NOT NULL,           -- e.g. 'invite.create' / 'member.role_change' / 'agent_config.update'
    target_table    text,                    -- 'tenant_invites' / 'user_profiles' / 'agent_model_config'
    target_id       text,                    -- text not uuid: some target ids are composite ("tenant_id:agent_key")
    before          jsonb,
    after           jsonb,
    ip_hash         text,
    user_agent      text,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_audit_log_tenant_time
    ON public.tenant_audit_log (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tenant_audit_log_actor
    ON public.tenant_audit_log (tenant_id, actor_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tenant_audit_log_action
    ON public.tenant_audit_log (tenant_id, action_type, created_at DESC);

ALTER TABLE public.tenant_audit_log ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname='public' AND tablename='tenant_audit_log'
          AND policyname='tenant_audit_admin_select'
    ) THEN
        CREATE POLICY tenant_audit_admin_select ON public.tenant_audit_log
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() AND public.is_team_admin());
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- log_tenant_event RPC — SECURITY DEFINER so we can stamp the actor's
-- user_id atomically from auth.uid() without the caller forging it.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.log_tenant_event(
    p_tenant_id     uuid,
    p_action_type   text,
    p_target_table  text DEFAULT NULL,
    p_target_id     text DEFAULT NULL,
    p_before        jsonb DEFAULT NULL,
    p_after         jsonb DEFAULT NULL,
    p_ip_hash       text DEFAULT NULL,
    p_user_agent    text DEFAULT NULL,
    p_metadata      jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_id uuid;
    v_actor_email text;
BEGIN
    SELECT email INTO v_actor_email
    FROM auth.users
    WHERE id = auth.uid()
    LIMIT 1;

    INSERT INTO public.tenant_audit_log (
        tenant_id, actor_user_id, actor_email,
        action_type, target_table, target_id,
        before, after, ip_hash, user_agent, metadata
    ) VALUES (
        p_tenant_id, auth.uid(), v_actor_email,
        p_action_type, p_target_table, p_target_id,
        p_before, p_after, p_ip_hash, p_user_agent, COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.log_tenant_event(uuid, text, text, text, jsonb, jsonb, text, text, jsonb) IS
  'SOC2-style audit logger. Stamps actor_user_id from auth.uid() so '
  'application code cannot forge it. Open action_type vocab — convention: '
  'dot-namespaced (e.g. invite.create, member.role_change, agent_config.update).';

COMMIT;
