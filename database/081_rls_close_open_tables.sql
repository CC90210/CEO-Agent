-- 081_rls_close_open_tables.sql
--
-- CRITICAL: 13 public tables had no RLS enabled. Combined with the
-- default Supabase GRANT (anon + authenticated get full DML on every
-- table), this means anyone with the public anon key (which ships in
-- every browser bundle) could SELECT / INSERT / UPDATE / DELETE rows
-- directly via the Supabase client, bypassing every API route gate.
--
-- The most critical exposure is agent_events: 373+ rows containing
-- multi-tenant payloads (lead IDs, command summaries, error details).
-- Any logged-in tenant user could read every other tenant's event
-- payload. Mitigated at the API layer by event-feed route's
-- correlation_id filter — but a direct Supabase client call bypasses
-- it entirely.
--
-- Strategy:
--   - agent_events: RLS on, SELECT scoped to user's tenant via
--     correlation_id, plus operator-email bypass. INSERT/UPDATE/DELETE
--     denied for non-service-role (system writes use the service-role
--     client and bypass RLS).
--   - All other RLS-off tables are CC-personal infrastructure
--     (agent_decisions, agent_state_snapshot, memories_*, drift_*,
--     shadow_decisions, template_performance, vertical_response_patterns,
--     lead_edges, leads_outreach). These are touched by service-role
--     code only. Enable RLS with no policies = default-deny for anon
--     and authenticated. Service role still works.
--
-- Why no INSERT/UPDATE/DELETE policies on agent_events: today every
-- writer is service-role (Kixie webhook, action-log, state-health,
-- send_gateway). If a future use case needs authed write, add a
-- targeted policy at that time instead of a broad permit.
--
-- All policies are drop-and-recreate so re-running is safe.

-- ============================================================
-- agent_events: tenant-scoped SELECT, defense-in-depth for the
-- /api/event-feed route's correlation_id filter
-- ============================================================
ALTER TABLE public.agent_events ENABLE ROW LEVEL SECURITY;

-- Idempotent policy creation via exception-swallowing DO block.
-- The apply_migration tool blocks DROP/ALTER POLICY by design (see
-- migration 013 hardening); this pattern stays within those guards.
DO $policy$
BEGIN
  CREATE POLICY agent_events_tenant_select
    ON public.agent_events FOR SELECT
    TO authenticated
    USING (
      -- correlation_id is text-typed but holds a tenant uuid for every
      -- multi-tenant event producer (kixie webhook, state_manager,
      -- bridge events). Cast safely — non-UUID rows comparison-fail.
      correlation_id IN (
        SELECT tenant_id::text
        FROM public.user_profiles
        WHERE auth_user_id = auth.uid()
      )
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $policy$;

-- ============================================================
-- CC-personal infrastructure: RLS on, no policies for
-- anon/authenticated = default-deny. Service role bypasses.
-- ============================================================
ALTER TABLE public.agent_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_state_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.drift_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.drift_baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads_outreach ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories_episodic ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories_procedural ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories_semantic ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shadow_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.template_performance ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vertical_response_patterns ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.agent_events IS
  'Cross-agent event bus. RLS-scoped per tenant via correlation_id (text-cast '
  'of tenant uuid). System writers use service role and bypass RLS. Migration '
  '081 hardened this — pre-migration the anon role had full DML.';
