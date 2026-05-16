/**
 * All Supabase queries the OASIS AI Agent Command Center makes.
 *
 * Tenant-aware: every query resolves the active operator profile from the
 * authenticated session (or falls back to the OPERATOR_EMAIL env for
 * legacy / non-auth contexts), then scopes reads to that tenant_id.
 *
 * Service-role for now (server-side reads); RLS policies live in the DB
 * for when client-side reads are added.
 */

import {
  getServiceSupabase,
  getSessionUser,
} from "./supabase-server";
import type {
  LeadInteraction,
  AgentDecision,
  Lead,
  AgentEvent,
  AgentStateSnapshot,
  UserProfile,
  DailyPlan,
  IntegrationHealth,
  Tenant,
  PlanTemplate,
} from "./supabase";
import { KNOWN_INTEGRATIONS } from "./integrations-registry";
import { operatorDateKey, operatorDayStartIso } from "./dates";
import { getDbBackend } from "./db";
import { isMissingTableError } from "./api-helpers";
import { getTenantEnabledAgents } from "./manifest/tenant-scope";
import {
  getTodayPlanTurso,
  recentLeadsTurso,
  pipelineBreakdownTurso,
} from "./turso-queries";

// ============================================================================
// Profile + Tenant
// ============================================================================

export async function getActiveProfile(): Promise<UserProfile | null> {
  const db = getServiceSupabase();
  const user = await getSessionUser();

  // Prefer authed user; fall back to OPERATOR_EMAIL (CC's legacy single-tenant default)
  if (user?.id) {
    const r = await db.from("user_profiles").select("*").eq("auth_user_id", user.id).maybeSingle();
    if (r.data) return r.data as UserProfile;
    // Auth user exists but no profile yet — try by email (post-migration link case)
    if (user.email) {
      const e = await db.from("user_profiles").select("*").eq("email", user.email).maybeSingle();
      if (e.data) return e.data as UserProfile;
    }
  }

  const fallbackEmail = process.env.OPERATOR_EMAIL || "conaugh@oasisai.work";
  const r = await db.from("user_profiles").select("*").eq("email", fallbackEmail).maybeSingle();
  if (r.error || !r.data) return null;
  return r.data as UserProfile;
}

export async function getTenant(tenantId: string): Promise<Tenant | null> {
  const db = getServiceSupabase();
  const r = await db.from("tenants").select("*").eq("id", tenantId).maybeSingle();
  if (r.error || !r.data) return null;
  return r.data as Tenant;
}

/**
 * True when the tenant has a non-revoked bridge pairing that pinged in the
 * last 5 minutes — same freshness rule the layout's header dot uses. Single
 * source of truth so Settings page + ChatWidget + AgentConfigEditor + any
 * future caller agree on what "bridge online" means.
 *
 * Returns false on missing tenant, missing pair, stale pair, or any DB error.
 * Never throws — best-effort signal that callers gate optional features on.
 */
export async function getBridgeOnline(tenantId: string | null): Promise<boolean> {
  if (!tenantId) return false;
  try {
    const db = getServiceSupabase();
    const r = await db
      .from("bridge_pairings")
      .select("last_seen_at")
      .eq("tenant_id", tenantId)
      .is("revoked_at", null)
      .order("last_seen_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    const last = (r.data as { last_seen_at?: string | null } | null)?.last_seen_at;
    if (!last) return false;
    return Date.now() - new Date(last).getTime() < 5 * 60 * 1000;
  } catch {
    return false;
  }
}

/**
 * Phase F of giggly-reef — return the tool registry the operator's currently
 * live bridge has advertised, or null when no bridge is online or the
 * advertised list is empty (no filter, fall back to TOOL_DEFINITIONS defaults).
 *
 * Used by /api/chat to filter the bridge tools sent to Anthropic: dashboard
 * shouldn't advertise read_file if the operator's bridge version doesn't ship
 * that tool yet. Single round-trip — same row getBridgeOnline reads, plus
 * the tool_capabilities column.
 */
export async function getBridgeToolCapabilities(
  tenantId: string | null,
): Promise<{ online: boolean; tools: string[] | null }> {
  if (!tenantId) return { online: false, tools: null };
  try {
    const db = getServiceSupabase();
    const r = await db
      .from("bridge_pairings")
      .select("last_seen_at, tool_capabilities")
      .eq("tenant_id", tenantId)
      .is("revoked_at", null)
      .order("last_seen_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    const row = r.data as
      | { last_seen_at?: string | null; tool_capabilities?: string[] | null }
      | null;
    if (!row?.last_seen_at) return { online: false, tools: null };
    const online = Date.now() - new Date(row.last_seen_at).getTime() < 5 * 60 * 1000;
    if (!online) return { online: false, tools: null };
    const tools = Array.isArray(row.tool_capabilities)
      ? row.tool_capabilities.filter((t): t is string => typeof t === "string")
      : [];
    // Empty array → bridge online but never ran the new daemon (pre-Phase-F).
    // Fall back to null so /api/chat treats as "no filter" and uses the
    // hardcoded defaults. Preserves backwards-compat with existing pairings.
    return { online, tools: tools.length > 0 ? tools : null };
  } catch {
    return { online: false, tools: null };
  }
}

export async function getTodayPlan(profileId: string): Promise<DailyPlan | null> {
  // Tenant data sovereignty: when EMPIRE_DATA_BACKEND=turso_local + TURSO_DB_PATH
  // is set, read from the client's local libSQL file instead of Supabase. Falls
  // back to Supabase on any Turso failure so the dashboard never blank-screens.
  if (getDbBackend() === "turso") {
    const tursoRow = await getTodayPlanTurso(profileId);
    if (tursoRow) return tursoRow;
    // Fall through to Supabase on null (Turso miss OR Turso error already logged)
  }
  const db = getServiceSupabase();
  const today = operatorDateKey();
  const r = await db
    .from("daily_plans")
    .select("*")
    .eq("profile_id", profileId)
    .eq("plan_date", today)
    .maybeSingle();
  if (r.error || !r.data) return null;
  return r.data as DailyPlan;
}

export async function getPlanTemplates(profileId: string): Promise<PlanTemplate[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("plan_templates")
    .select("*")
    .eq("profile_id", profileId)
    .order("kind");
  return (r.data as PlanTemplate[]) || [];
}

export async function getLeadById(leadId: string): Promise<Lead | null> {
  const db = getServiceSupabase();
  const r = await db.from("leads").select("*").eq("id", leadId).maybeSingle();
  if (r.error || !r.data) return null;
  return r.data as Lead;
}

// ============================================================================
// Today's high-level counters (tenant-scoped)
// ============================================================================

export async function todayCounts(tenantId: string) {
  const db = getServiceSupabase();
  // Operator-TZ midnight (not server-local) — without this, Toronto users
  // hitting Vercel UTC after 8pm see TOMORROW's counts instead of today's.
  const dayStart = operatorDayStartIso();

  // Decisions + hot-alerts come from agent_decisions + agent_events,
  // both of which are PRE-multi-tenant tables (no tenant_id column —
  // tracked schema debt; see migration 017's docstring). Until the
  // tenant_id columns + RLS land, scope by the tenant's enabled-agent
  // set so a SunBiz operator never sees OASIS HQ Bravo's decision /
  // alert counts on their stat cards.
  //
  // Empty agentNames → return 0 (safer than leaking — same posture
  // recentDecisions / recentEvents already take).
  const enabledAgents = await getTenantEnabledAgents(tenantId);

  const [outbound, inbound, decisions, hot] = await Promise.all([
    db
      .from("lead_interactions")
      .select("id", { count: "exact", head: true })
      .eq("tenant_id", tenantId)
      .in("type", ["email_sent", "dm_sent", "linkedin_sent", "call_made"])
      .gte("created_at", dayStart),
    db
      .from("lead_interactions")
      .select("id", { count: "exact", head: true })
      .eq("tenant_id", tenantId)
      .in("type", ["email_received", "email_reply", "dm_received"])
      .gte("created_at", dayStart),
    enabledAgents.length === 0
      ? Promise.resolve({ count: 0 })
      : db
          .from("agent_decisions")
          .select("id", { count: "exact", head: true })
          .in("agent_name", enabledAgents)
          .gte("created_at", dayStart),
    enabledAgents.length === 0
      ? Promise.resolve({ count: 0 })
      : db
          .from("agent_events")
          .select("id", { count: "exact", head: true })
          .in("publisher_agent", enabledAgents)
          .eq("event_type", "inbound.classified")
          .eq("severity", "warn")
          .gte("published_at", dayStart),
  ]);

  return {
    outbound: outbound.count ?? 0,
    inbound: inbound.count ?? 0,
    decisions: decisions.count ?? 0,
    hot: hot.count ?? 0,
  };
}

// ============================================================================
// Pipeline (tenant-scoped)
// ============================================================================

export async function pipelineBreakdown(tenantId: string, includeArchived = false) {
  // Tenant data sovereignty: route to Turso for the SunBiz pipeline stat band
  // when the client opted into local libSQL. Falls back on null.
  if (getDbBackend() === "turso") {
    const tursoBreakdown = await pipelineBreakdownTurso(tenantId, includeArchived);
    if (tursoBreakdown !== null) return tursoBreakdown;
  }
  const db = getServiceSupabase();
  let q = db.from("leads").select("status,score,source").eq("tenant_id", tenantId);
  if (!includeArchived) q = q.neq("status", "archived");
  const r = await q;
  if (r.error || !r.data) return { stages: {}, total: 0, sources: {} };
  const stages: Record<string, number> = {
    new: 0, contacted: 0, qualified: 0, proposal: 0, won: 0, lost: 0,
  };
  const sources: Record<string, number> = {};
  for (const row of r.data as Array<{ status: string | null; source: string | null }>) {
    const s = (row.status as string) || "new";
    stages[s] = (stages[s] || 0) + 1;
    const src = row.source || "unknown";
    sources[src] = (sources[src] || 0) + 1;
  }
  return { stages, total: r.data.length, sources };
}

/**
 * Recent autonomous-loop decisions for the Reasoning page's "Agent decisions"
 * tape.
 *
 * SCOPING (cross-tenant data-leak fix, 2026-05-14):
 *   The agent_decisions table predates the tenant_manifests system and does
 *   NOT carry a tenant_id column today — every row was written by the
 *   autonomous_agent.py loop running for CC's OASIS Bravo. Until the column
 *   + RLS land (Phase 5 schema migration), the read path filters by
 *   agent_name ∈ agentNames so a SunBiz tenant (agents_enabled = [solara,
 *   helios]) sees ZERO Bravo rows.
 *
 *   When agentNames is empty (legacy callers, new tenants pre-wizard) the
 *   query returns [] — safer to show nothing than to leak.
 *
 *   When the schema gains tenant_id, prefer .eq("tenant_id", tenantId) and
 *   keep agentNames as a secondary filter for "show only decisions from
 *   agents I currently have enabled."
 *
 *   The tenantId param is plumbed through now so callers stop changing
 *   shape when the migration lands.
 */
export async function recentDecisions(
  tenantId: string | null,
  agentNames: string[],
  limit = 20
): Promise<AgentDecision[]> {
  if (!tenantId) return [];
  if (agentNames.length === 0) return [];
  const db = getServiceSupabase();
  const r = await db
    .from("agent_decisions")
    .select("*")
    .in("agent_name", agentNames)
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as AgentDecision[]) || [];
}

export async function recentInbound(tenantId: string, limit = 20): Promise<LeadInteraction[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("lead_interactions")
    .select("*")
    .eq("tenant_id", tenantId)
    .in("type", ["email_received", "email_reply", "dm_received"])
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as LeadInteraction[]) || [];
}

export async function recentOutbound(tenantId: string, limit = 20): Promise<LeadInteraction[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("lead_interactions")
    .select("*")
    .eq("tenant_id", tenantId)
    .in("type", ["email_sent", "dm_sent", "linkedin_sent", "call_made"])
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as LeadInteraction[]) || [];
}

export async function recentLeads(
  tenantId: string,
  limit = 30,
  opts?: { include_archived?: boolean; include_no_email?: boolean; include_lost?: boolean }
): Promise<Lead[]> {
  // Tenant data sovereignty: route to Turso when the client opted into local
  // libSQL storage. Falls back to Supabase on null (Turso miss or error).
  if (getDbBackend() === "turso") {
    const tursoRows = await recentLeadsTurso(tenantId, limit, opts);
    if (tursoRows !== null) return tursoRows;
  }
  const db = getServiceSupabase();
  let q = db.from("leads").select("*").eq("tenant_id", tenantId);
  if (!opts?.include_archived) q = q.neq("status", "archived");
  if (!opts?.include_lost) q = q.neq("status", "lost");
  if (!opts?.include_no_email) q = q.not("email", "is", null);
  q = q.order("updated_at", { ascending: false }).limit(limit);
  const r = await q;
  return (r.data as Lead[]) || [];
}

/**
 * Live heartbeat snapshots from the autonomous loop. Same scoping caveat
 * as recentDecisions — agent_state_snapshot is per-agent_name, not per-
 * tenant. Filter by the tenant's enabled agent set so a client tenant
 * doesn't see CC's Bravo heartbeats and vice versa. Empty agentNames →
 * empty result (safer than leaking).
 */
export async function agentStates(agentNames: string[] = []): Promise<AgentStateSnapshot[]> {
  if (agentNames.length === 0) return [];
  const db = getServiceSupabase();
  const r = await db
    .from("agent_state_snapshot")
    .select("*")
    .in("agent_name", agentNames)
    .order("last_tick_at", { ascending: false });
  return (r.data as AgentStateSnapshot[]) || [];
}

/**
 * Activity-tape rows for /agents and /operations.
 *
 * SCOPING (cross-tenant data-leak fix, 2026-05-14):
 *   agent_events does NOT carry a tenant_id column today (same schema debt
 *   as agent_decisions + agent_state_snapshot). Until the column lands,
 *   the read path filters by publisher_agent ∈ agentNames so a client
 *   tenant only sees events fired by agents they have enabled.
 *
 *   Operators (CC) get the full feed by passing isOperator: true — the
 *   activity tape is one of the operator's primary debugging surfaces and
 *   we want them to see everything including system events with no
 *   publisher_agent.
 *
 *   Empty agentNames + non-operator: return [] (safer than leaking).
 *
 *   Default sinceDays: 7. The /operations + /agents pages explicitly pass
 *   sinceDays:0 to show "most recent N regardless of age" — they were
 *   rendering empty when the event bus was quiet for a week even though
 *   the table had history.
 */
export async function recentEvents(
  limit = 25,
  opts?: {
    sinceDays?: number;
    tenantId?: string | null;
    agentNames?: string[];
    isOperator?: boolean;
  }
): Promise<AgentEvent[]> {
  const agentNames = opts?.agentNames ?? [];
  const isOperator = opts?.isOperator === true;

  // Non-operator with no enabled agents → no leakage. Operator with no
  // agentNames → full feed (this is the dashboard-debug expectation).
  if (!isOperator && agentNames.length === 0) return [];

  const db = getServiceSupabase();
  let q = db.from("agent_events").select("*");

  if (!isOperator) {
    q = q.in("publisher_agent", agentNames);
  }

  const sinceDays = opts?.sinceDays ?? 7;
  if (sinceDays > 0) {
    const since = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000).toISOString();
    q = q.gte("published_at", since);
  }
  q = q.order("published_at", { ascending: false }).limit(limit);
  const r = await q;
  return (r.data as AgentEvent[]) || [];
}

/**
 * A6: Recent dashboard-action mutations for the /runs page. Filters
 * agent_events to event_type='dashboard_action' published by this tenant
 * (correlation_id == tenant_id, see lib/action-log.ts).
 */
export async function recentActions(
  tenantId: string,
  limit = 100
): Promise<AgentEvent[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("agent_events")
    .select("*")
    .eq("event_type", "dashboard_action")
    .eq("correlation_id", tenantId)
    .order("published_at", { ascending: false })
    .limit(limit);
  return (r.data as AgentEvent[]) || [];
}

// ============================================================================
// Channel caps (tenant-scoped)
// ============================================================================

const DAILY_CAPS: Record<string, number> = {
  email: 50,
  instagram: 30,
  linkedin: 20,
  phone: 15,
};

export async function channelUtilization(tenantId: string) {
  const db = getServiceSupabase();
  // Operator-TZ midnight — see todayCounts() for the bug this fixes.
  const dayStart = operatorDayStartIso();
  const rows = await db
    .from("lead_interactions")
    .select("channel")
    .eq("tenant_id", tenantId)
    .gte("created_at", dayStart);
  const counts: Record<string, number> = {};
  for (const row of rows.data || []) {
    const c = (row as { channel: string }).channel;
    counts[c] = (counts[c] || 0) + 1;
  }
  return Object.entries(DAILY_CAPS).map(([channel, cap]) => ({
    channel,
    used: counts[channel] || 0,
    cap,
    pct: Math.round(((counts[channel] || 0) / cap) * 100),
  }));
}

// ============================================================================
// Integrations health (tenant-scoped)
// ============================================================================

export async function integrationsHealth(
  tenantId: string | null
): Promise<IntegrationHealth[]> {
  // 2026-05-16 Round 3 R3-8: previously the function fell through when
  // tenantId was null and returned every tenant's integration rows
  // (cross-tenant leak on the "unconfigured" placeholder path). Now
  // null returns an unconfigured-everywhere shape — same UX a real
  // tenant with no rows would see, no leak.
  const db = getServiceSupabase();
  if (!tenantId) {
    // Synthesize placeholders for every known integration so the UI
    // still has something to render. Caller's behavior is preserved
    // (every service shows "unconfigured") without scanning all tenants.
    return KNOWN_INTEGRATIONS.map((integration) => ({
      id: `placeholder-${integration.service}`,
      profile_id: null,
      tenant_id: null,
      service: integration.service,
      status: "unconfigured" as const,
      last_ping_at: null,
      metadata: {},
      last_error: null,
    })) as IntegrationHealth[];
  }
  const r = await db
    .from("integrations_health")
    .select("*")
    .eq("tenant_id", tenantId)
    .order("service", { ascending: true });

  const expected = KNOWN_INTEGRATIONS.map((integration) => integration.service);
  const existing = new Map(
    (r.data as IntegrationHealth[] | null)?.map((row) => [row.service, row]) || []
  );
  return expected.map((service) => {
    const found = existing.get(service);
    if (found) return found;
    return {
      id: `placeholder-${service}`,
      profile_id: null,
      tenant_id: tenantId,
      service,
      status: "unconfigured" as const,
      last_ping_at: null,
      last_error: null,
      metadata: {},
      updated_at: new Date().toISOString(),
    };
  });
}

// ============================================================================
// Top-client concentration risk — % of MRR from a single client
// ============================================================================

/**
 * Returns the % of MRR concentrated in the operator's biggest client.
 * Reads `profile.custom_fields.top_client_name` + `top_client_mrr_usd`
 * (operators set these in Settings or via scripts/seed_profile.py); for
 * other tenants without those fields, falls back to the top-1 won client
 * by score from the leads table.
 *
 * Future-friendly: when revenue_events table lands, swap to that.
 */
export async function topClientConcentration(tenantId: string): Promise<{
  client_name: string;
  pct_of_mrr: number;
  is_at_risk: boolean;
}> {
  const profile = await getActiveProfile();
  const totalMrr = Number(profile?.mrr_current_usd) || 0;
  if (totalMrr === 0) {
    return { client_name: "—", pct_of_mrr: 0, is_at_risk: false };
  }

  // For tenants without top_client_* in custom_fields, fall back to the
  // top-scoring won lead. Operator-configured fields take precedence.
  const db = getServiceSupabase();
  const r = await db
    .from("leads")
    .select("name,company,score")
    .eq("tenant_id", tenantId)
    .eq("status", "won")
    .order("score", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (!r.data) return { client_name: "—", pct_of_mrr: 0, is_at_risk: false };

  // Read from profile.custom_fields.top_client_mrr_usd. Operators set this
  // in Settings or via scripts/seed_profile.py. No magic numbers.
  const customFields = (profile?.custom_fields || {}) as Record<string, unknown>;
  const configuredName = (customFields.top_client_name as string) || null;
  const configuredMrr = Number(customFields.top_client_mrr_usd) || 0;

  const name = configuredName || r.data.name || r.data.company || "Top client";
  const pct = configuredMrr > 0 ? (configuredMrr / totalMrr) * 100 : 0;
  return {
    client_name: name,
    pct_of_mrr: Math.round(pct * 10) / 10,
    is_at_risk: pct >= 60,
  };
}

// ============================================================================
// Outreach reply rate — last 7 days
// ============================================================================

export async function outreachReplyRate(
  tenantId: string,
  days = 7
): Promise<{ replies: number; sends: number; rate_pct: number }> {
  const db = getServiceSupabase();
  const since = new Date();
  since.setDate(since.getDate() - days);
  const sinceIso = since.toISOString();

  const [sends, replies] = await Promise.all([
    db
      .from("lead_interactions")
      .select("id", { count: "exact", head: true })
      .eq("tenant_id", tenantId)
      .in("type", ["email_sent", "dm_sent", "linkedin_sent"])
      .gte("created_at", sinceIso),
    db
      .from("lead_interactions")
      .select("id", { count: "exact", head: true })
      .eq("tenant_id", tenantId)
      .in("type", ["email_received", "email_reply", "dm_received"])
      .gte("created_at", sinceIso),
  ]);

  const sendsCount = sends.count ?? 0;
  const repliesCount = replies.count ?? 0;
  const rate = sendsCount > 0 ? (repliesCount / sendsCount) * 100 : 0;
  return {
    replies: repliesCount,
    sends: sendsCount,
    rate_pct: Math.round(rate * 10) / 10,
  };
}

// ============================================================================
// Active pipeline value — leads at qualified or proposal stage
// ============================================================================

export async function activePipeline(tenantId: string): Promise<{
  qualified: number;
  proposal: number;
  total_active: number;
}> {
  const db = getServiceSupabase();
  const r = await db
    .from("leads")
    .select("status")
    .eq("tenant_id", tenantId)
    .in("status", ["qualified", "proposal"]);
  const data = (r.data || []) as Array<{ status: string }>;
  const qualified = data.filter((d) => d.status === "qualified").length;
  const proposal = data.filter((d) => d.status === "proposal").length;
  return { qualified, proposal, total_active: data.length };
}

// ============================================================================
// Top open lead — single highest-score non-won/lost/archived lead
// ============================================================================

export async function topOpenLead(tenantId: string): Promise<Lead | null> {
  const db = getServiceSupabase();
  const r = await db
    .from("leads")
    .select("*")
    .eq("tenant_id", tenantId)
    .not("status", "in", "(won,lost,archived)")
    .order("score", { ascending: false, nullsFirst: false })
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (r.data as Lead | null) || null;
}

// ============================================================================
// MRR
// ============================================================================

export async function mrrSnapshot(): Promise<{ current: number; target: number; pct: number }> {
  const profile = await getActiveProfile();
  if (!profile) return { current: 0, target: 5000, pct: 0 };
  const target = Number(profile.mrr_target_usd) || 5000;
  const current = Number(profile.mrr_current_usd) || 0;
  return {
    current,
    target,
    pct: target > 0 ? Math.round((current / target) * 1000) / 10 : 0,
  };
}

/**
 * MRR history is **NOT REAL DATA** yet — there is no `mrr_history` table.
 * Returns synthetic trajectory tagged synthetic: true.
 */

/**
 * Which AI provider services have credentials on file for this tenant?
 *
 * Returns a Set of integration-registry service slugs (anthropic, openai_codex,
 * google_ai, openrouter) for any agent_model_config row with an encrypted key
 * and enabled=true. The /integrations and /settings pages use this to mark
 * provider cards as "Connected" instead of "Not connected" when a key exists
 * but no successful API call has been pinged yet.
 */
// PROVIDER_TO_SERVICE moved to lib/providers.ts (client-safe pure-data
// home) so client components can import the mapping without dragging
// supabase-server's next/headers dep into the client bundle. See
// providers.ts for the table itself. Re-imported + re-exported here so
// (a) aiServicesWithKey below can use the local name, and (b) existing
// callers that still grab the symbol from this file's surface keep
// working.
import { PROVIDER_TO_SERVICE } from "./providers";
export { PROVIDER_TO_SERVICE };

export async function aiServicesWithKey(tenantId: string | null): Promise<Set<string>> {
  const out = new Set<string>();
  if (!tenantId) return out;
  const db = getServiceSupabase();
  const { data } = await db
    .from("agent_model_config")
    .select("provider, encrypted_api_key, enabled")
    .eq("tenant_id", tenantId);
  for (const row of (data || []) as Array<{ provider: string; encrypted_api_key: string | null; enabled: boolean }>) {
    if (!row.encrypted_api_key || !row.enabled) continue;
    const svc = PROVIDER_TO_SERVICE[row.provider];
    if (svc) out.add(svc);
  }
  return out;
}

export async function mrrHistory(days = 30): Promise<
  Array<{ date: string; mrr: number; synthetic: boolean }>
> {
  const profile = await getActiveProfile();
  const current = Number(profile?.mrr_current_usd) || 0;
  const tenantId = profile?.tenant_id || null;

  // Try real snapshots first (migration 021). If we have at least 2 days
  // of data, use it as-is — synthetic flag false. Anything missing in the
  // window gets back-filled with the most-recent known value (so the chart
  // doesn't drop to zero on days the cron hadn't run yet).
  let real: Array<{ snapshot_date: string; mrr_usd: number }> = [];
  if (tenantId) {
    try {
      const db = getServiceSupabase();
      const since = new Date();
      since.setDate(since.getDate() - days + 1);
      const { data } = await db
        .from("mrr_snapshots")
        .select("snapshot_date, mrr_usd")
        .eq("tenant_id", tenantId)
        .gte("snapshot_date", since.toISOString().slice(0, 10))
        .order("snapshot_date", { ascending: true });
      real = ((data as Array<{ snapshot_date: string; mrr_usd: string | number }>) || [])
        .map((r) => ({ snapshot_date: r.snapshot_date, mrr_usd: Number(r.mrr_usd) }));
    } catch {
      real = [];
    }
  }

  if (real.length >= 2) {
    const byDate = new Map(real.map((r) => [r.snapshot_date, r.mrr_usd] as const));
    const out: Array<{ date: string; mrr: number; synthetic: boolean }> = [];
    let lastKnown = real[0].mrr_usd;
    const today = new Date();
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const iso = d.toISOString().slice(0, 10);
      const v = byDate.get(iso);
      const hasReal = v != null;
      if (hasReal) lastKnown = v;
      // Tag back-filled days as synthetic so the chart can style them
      // distinctly. Without this every point reads as "real data" and
      // the operator thinks the cron has been running for 60 days when
      // only 3 days of snapshots actually exist.
      out.push({
        date: iso.slice(5, 10),
        mrr: Math.round(lastKnown),
        synthetic: !hasReal,
      });
    }
    return out;
  }

  // Fallback: synthetic decline curve, tagged so the UI can label it.
  const out: Array<{ date: string; mrr: number; synthetic: boolean }> = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    out.push({
      date: d.toISOString().slice(5, 10),
      mrr: Math.round(current - i * (current * 0.005)),
      synthetic: true,
    });
  }
  return out;
}

// ============================================================================
// Sun Biz Funding shared-shell fallback readers
// ----------------------------------------------------------------------------
// These helpers back the current /leads, /renewals, /sms, /commissions, etc.
// pages while the command-center shell is still rendering Sun inside the
// empire app.
//
// Operator correction (2026-05-11): Sun's long-term client data architecture
// is Turso/libSQL, not Supabase row-level tenancy. These Supabase readers are
// therefore transitional scaffolding only — they keep the shared shell
// rendering clean empty states until the dedicated Turso adapter lands.
//
// Defensive note: the funded_deals / sms_sends / commissions / applications
// tables don't exist in Phase 1 — they land in the future client schema.
// Every helper here catches "relation not found" errors and returns empty/zero
// shapes so the dashboard never 500s while the data layer is in flight.
// ============================================================================

/** Funded-deal row shape we render. Mirrors the migration 041 schema. */
export type FundedDealRow = {
  id: string;
  merchant_name: string | null;
  contact_name: string | null;
  lender_name: string | null; // null = "No lender assigned"
  funded_amount_usd: number | null;
  factor_rate: number | null;
  funded_at: string | null;
  next_renewal_date: string | null;
  est_commission_usd: number | null;
};

export type RenewalsSummary = {
  past_due_count: number;
  this_week_count: number;
  this_month_count: number;
  est_commission_total_usd: number;
  total_with_dates: number;
  total_no_date: number;
};

const EMPTY_RENEWALS_SUMMARY: RenewalsSummary = {
  past_due_count: 0,
  this_week_count: 0,
  this_month_count: 0,
  est_commission_total_usd: 0,
  total_with_dates: 0,
  total_no_date: 0,
};

/**
 * Returns true if a PostgREST error indicates the table simply doesn't
 * exist yet (Phase 1, before migrations 037-047 land). We swallow these
 * specifically and return empty shapes; any other error bubbles up so
 * we see real bugs in Vercel logs.
 *
 * Thin wrapper over the shared lib/api-helpers#isMissingTableError so
 * the queries-reader-side check stays in sync with the API-route-side
 * check. Kept as a local helper just so existing callers don't need
 * an import change; new callers should import from api-helpers directly.
 */
function _isMissingTable(err: { code?: string; message?: string } | null | undefined): boolean {
  return isMissingTableError(err);
}

/**
 * Aggregate counts + commission for the 4 Renewals stat cards.
 * Phase 1: returns zeros until migration 041 (funded_deals) ships.
 */
export async function getRenewalsSummary(tenantId: string): Promise<RenewalsSummary> {
  const db = getServiceSupabase();
  try {
    const r = await db
      .from("funded_deals")
      .select("next_renewal_date, est_commission_usd")
      .eq("tenant_id", tenantId);

    if (r.error) {
      if (_isMissingTable(r.error)) return EMPTY_RENEWALS_SUMMARY;
      console.warn("[getRenewalsSummary]", r.error.message);
      return EMPTY_RENEWALS_SUMMARY;
    }

    const rows = (r.data as Array<{ next_renewal_date: string | null; est_commission_usd: number | null }>) || [];
    const now = new Date();
    const weekEnd = new Date(now);
    weekEnd.setDate(weekEnd.getDate() + 7);
    const monthEnd = new Date(now);
    monthEnd.setDate(monthEnd.getDate() + 30);

    let past_due = 0;
    let this_week = 0;
    let this_month = 0;
    let est_total = 0;
    let with_dates = 0;
    let no_date = 0;

    for (const row of rows) {
      if (!row.next_renewal_date) {
        no_date += 1;
        continue;
      }
      with_dates += 1;
      const d = new Date(row.next_renewal_date);
      if (d < now) past_due += 1;
      else if (d <= weekEnd) this_week += 1;
      else if (d <= monthEnd) this_month += 1;
      if (row.est_commission_usd && d >= now && d <= monthEnd) {
        est_total += Number(row.est_commission_usd);
      }
    }

    return {
      past_due_count: past_due,
      this_week_count: this_week,
      this_month_count: this_month,
      est_commission_total_usd: est_total,
      total_with_dates: with_dates,
      total_no_date: no_date,
    };
  } catch (e) {
    console.warn("[getRenewalsSummary] unexpected", e);
    return EMPTY_RENEWALS_SUMMARY;
  }
}

/**
 * Renewal rows for the table beneath the stat cards. Phase 1: returns
 * empty until funded_deals lands. Includes the lender join shape we'd
 * use once the lenders table exists.
 */
export async function getRenewalsRows(
  tenantId: string,
  limit = 50
): Promise<FundedDealRow[]> {
  const db = getServiceSupabase();
  try {
    const r = await db
      .from("funded_deals")
      .select(
        "id, merchant_name, contact_name, lender_name, funded_amount_usd, factor_rate, funded_at, next_renewal_date, est_commission_usd"
      )
      .eq("tenant_id", tenantId)
      .order("next_renewal_date", { ascending: true, nullsFirst: false })
      .limit(limit);
    if (r.error) {
      if (_isMissingTable(r.error)) return [];
      console.warn("[getRenewalsRows]", r.error.message);
      return [];
    }
    return (r.data as FundedDealRow[]) || [];
  } catch (e) {
    console.warn("[getRenewalsRows] unexpected", e);
    return [];
  }
}

/** SMS history row for the /sms page recent-sends table. */
export type SmsSendRow = {
  id: string;
  sent_at: string;
  provider: string | null;
  to_hash: string | null;
  body_preview: string | null;
  status: string | null;
  sid: string | null;
};

/**
 * Recent SMS sends — fed by migration 044 (sms_sends). Phase 1 fallback
 * reads the local sms_engine.py JSONL log via the API surface; the
 * Supabase path takes over Phase 2.
 */
export async function getSmsHistory(
  tenantId: string,
  limit = 50
): Promise<SmsSendRow[]> {
  const db = getServiceSupabase();
  try {
    const r = await db
      .from("sms_sends")
      .select("id, sent_at, provider, to_hash, body_preview, status, sid")
      .eq("tenant_id", tenantId)
      .order("sent_at", { ascending: false })
      .limit(limit);
    if (r.error) {
      if (_isMissingTable(r.error)) return [];
      console.warn("[getSmsHistory]", r.error.message);
      return [];
    }
    return (r.data as SmsSendRow[]) || [];
  } catch (e) {
    console.warn("[getSmsHistory] unexpected", e);
    return [];
  }
}

/** Applications count — drives the sidebar badge on /applications. */
export async function getApplicationsCount(tenantId: string): Promise<number> {
  const db = getServiceSupabase();
  try {
    const r = await db
      .from("applications")
      .select("id", { count: "exact", head: true })
      .eq("tenant_id", tenantId);
    if (r.error) {
      if (_isMissingTable(r.error)) return 0;
      return 0;
    }
    return r.count || 0;
  } catch {
    return 0;
  }
}

/**
 * Convenience helper for the /leads page. Just wraps recentLeads with
 * a tenant-required signature and sensible default filters for the
 * funding-ops workflow (no email filter — Sun uses phone-first SMS
 * outreach so leads without email are still actionable).
 */
export async function getLeadsForTenant(
  tenantId: string,
  limit = 100
): Promise<Lead[]> {
  return recentLeads(tenantId, limit, { include_no_email: true });
}
