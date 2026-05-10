-- ============================================================================
-- Migration 035 — exec_overrides mirror for V6 Apex Phase 2 (Dashboard-Driven
-- Override Approvals).
--
-- Local source of truth is still `override_request` in state/empire_state.db
-- (SQLite, see state_manager.create_override_request / approve_override_request).
-- This table is the dashboard-visible mirror — pending requests land here so
-- the operator can approve/deny from the Vercel UI without opening a TTY.
--
-- Flow:
--   1. exec_guard blocks    → state_manager.create_override_request() inserts
--                              locally AND best-effort upserts here as pending.
--   2. operator clicks ✓    → /api/exec-override POST writes
--                              dashboard_decision='approve' via record_exec_override_decision_v1.
--   3. exec_override_consumer → polls rows WHERE dashboard_decision IS NOT NULL
--                              AND consumer_synced_at IS NULL, calls
--                              approve_override_request() / deny_override_request()
--                              locally, marks the row synced.
--   4. exec_guard at runtime → still consults SQLite via find_fresh_approval;
--                              Supabase is dashboard-visibility, NOT the auth path.
--
-- Note on RLS: every row is service-role-only. The Next.js routes use the
-- service-role client (via getServiceSupabase) gated by the existing
-- x-oasis-profile-id + x-oasis-secret HMAC handshake, which is itself
-- validated against n8n_webhook_secrets.secret_hash inside the SECURITY DEFINER
-- RPC below — so a leaked anon key cannot record a decision.
--
-- Note on GRANTs: service_role has EXECUTE on functions in the public schema
-- by default in Supabase. Explicit GRANTs were stripped to satisfy the
-- apply_migration.py guardrail; service_role can still call the RPCs because
-- they live in `public` and use SECURITY DEFINER with explicit search_path.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.exec_overrides (
    request_id          text PRIMARY KEY,
    ts                  timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,
    command             text NOT NULL,
    command_hash        text NOT NULL,
    layer               text NOT NULL,
    reason              text,
    caller_pid          int,

    status              text NOT NULL DEFAULT 'pending',
    approved_at         timestamptz,
    approved_by         text,
    consumed_at         timestamptz,
    hmac_sig            text,

    dashboard_decision    text,
    dashboard_decided_at  timestamptz,
    dashboard_decided_by  uuid REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    dashboard_reason      text,
    consumer_synced_at    timestamptz,

    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exec_overrides_status
    ON public.exec_overrides (status, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_exec_overrides_pending_intent
    ON public.exec_overrides (dashboard_decided_at)
    WHERE dashboard_decision IS NOT NULL AND consumer_synced_at IS NULL;

ALTER TABLE public.exec_overrides ENABLE ROW LEVEL SECURITY;

CREATE POLICY service_role_all_exec_overrides
    ON public.exec_overrides
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ----------------------------------------------------------------------------
-- record_exec_override_decision_v1 — atomic dashboard-side approve/deny.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.record_exec_override_decision_v1(
    p_profile_id   uuid,
    p_secret_hash  text,
    p_request_id   text,
    p_decision     text,
    p_reason       text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
DECLARE
    v_secret_valid boolean;
    v_existing     record;
BEGIN
    IF p_decision NOT IN ('approve', 'deny') THEN
        RAISE EXCEPTION 'invalid_decision: %', p_decision USING ERRCODE = 'P0003';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM public.n8n_webhook_secrets
        WHERE profile_id = p_profile_id
          AND secret_hash = p_secret_hash
          AND revoked_at IS NULL
    ) INTO v_secret_valid;

    IF NOT v_secret_valid THEN
        RAISE EXCEPTION 'invalid_oasis_secret' USING ERRCODE = '42501';
    END IF;

    SELECT request_id, status, dashboard_decision INTO v_existing
    FROM public.exec_overrides WHERE request_id = p_request_id;

    IF v_existing IS NULL THEN
        RAISE EXCEPTION 'request_not_found: %', p_request_id USING ERRCODE = 'P0001';
    END IF;

    IF v_existing.dashboard_decision IS NOT NULL THEN
        RAISE EXCEPTION 'already_decided: dashboard_decision=%', v_existing.dashboard_decision
            USING ERRCODE = 'P0002';
    END IF;

    IF v_existing.status IN ('consumed', 'denied', 'expired') THEN
        RAISE EXCEPTION 'request_not_pending: status=%', v_existing.status
            USING ERRCODE = 'P0002';
    END IF;

    UPDATE public.exec_overrides
    SET dashboard_decision   = p_decision,
        dashboard_decided_at = now(),
        dashboard_decided_by = p_profile_id,
        dashboard_reason     = p_reason,
        updated_at           = now()
    WHERE request_id = p_request_id;

    RETURN p_request_id;
END;
$func$;

-- ----------------------------------------------------------------------------
-- mark_exec_override_synced_v1 — called by exec_override_consumer after it
-- applies a dashboard decision to local SQLite.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.mark_exec_override_synced_v1(
    p_request_id    text,
    p_final_status  text,
    p_hmac_sig      text DEFAULT NULL,
    p_approved_at   timestamptz DEFAULT NULL,
    p_approved_by   text DEFAULT NULL,
    p_consumed_at   timestamptz DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
BEGIN
    IF p_final_status NOT IN ('approved', 'denied', 'consumed', 'expired') THEN
        RAISE EXCEPTION 'invalid_final_status: %', p_final_status USING ERRCODE = 'P0003';
    END IF;

    UPDATE public.exec_overrides
    SET status              = p_final_status,
        hmac_sig            = COALESCE(p_hmac_sig, hmac_sig),
        approved_at         = COALESCE(p_approved_at, approved_at),
        approved_by         = COALESCE(p_approved_by, approved_by),
        consumed_at         = COALESCE(p_consumed_at, consumed_at),
        consumer_synced_at  = now(),
        updated_at          = now()
    WHERE request_id = p_request_id;

    RETURN p_request_id;
END;
$func$;
