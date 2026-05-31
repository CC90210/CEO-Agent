-- 082_rls_lockdown_table_comments.sql
--
-- Follow-up to migration 081 which enabled RLS on 12 CC-personal
-- infrastructure tables with NO policies (default-deny for anon and
-- authenticated; service role bypasses). The intent is clear in the
-- migration header, but a future reader running `\d+ <table>` or
-- querying pg_description should see it without having to dig the
-- migration history. These comments are the durable signal.
--
-- If a future feature genuinely needs authed-client access to one of
-- these tables, the next migration should add a targeted policy AND
-- update the comment below to reflect the new access model.

COMMENT ON TABLE public.agent_decisions IS
  'Agent decision audit trail. RLS-locked: service-role writers only '
  '(scripts/autonomous_agent.py). No authenticated read path. Adding '
  'an authed read = add a tenant-scoped SELECT policy.';

COMMENT ON TABLE public.agent_state_snapshot IS
  'Agent tick state. RLS-locked: service-role writers only. Read by '
  'lib/queries.ts:agentStates via service role.';

COMMENT ON TABLE public.drift_alerts IS
  'Drift detection alerts. RLS-locked: service-role only.';

COMMENT ON TABLE public.drift_baselines IS
  'Drift detection baselines. RLS-locked: service-role only.';

COMMENT ON TABLE public.lead_edges IS
  'Lead relationship graph (referrals, duplicates, household). RLS-locked: '
  'service-role only. Tenant scoping enforced at application layer.';

COMMENT ON TABLE public.leads_outreach IS
  'Cold-outreach history. RLS-locked: service-role only. Single-tenant '
  'today (no tenant_id column); adding a second tenant requires both a '
  'tenant_id column and a SELECT policy.';

COMMENT ON TABLE public.memories_episodic IS
  'Agent episodic memory. RLS-locked: service-role only.';

COMMENT ON TABLE public.memories_procedural IS
  'Agent procedural memory. RLS-locked: service-role only.';

COMMENT ON TABLE public.memories_semantic IS
  'Agent semantic memory. RLS-locked: service-role only.';

COMMENT ON TABLE public.shadow_decisions IS
  'Shadow-mode decision ledger for ML training. RLS-locked: service-role only.';

COMMENT ON TABLE public.template_performance IS
  'Template-level outbound analytics. RLS-locked: service-role only.';

COMMENT ON TABLE public.vertical_response_patterns IS
  'Industry-vertical response analytics. RLS-locked: service-role only.';
