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

export async function getTodayPlan(profileId: string): Promise<DailyPlan | null> {
  const db = getServiceSupabase();
  const today = new Date().toISOString().slice(0, 10);
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
  const dayStart = new Date(
    new Date().getFullYear(),
    new Date().getMonth(),
    new Date().getDate()
  ).toISOString();

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
    db
      .from("agent_decisions")
      .select("id", { count: "exact", head: true })
      .gte("created_at", dayStart),
    db
      .from("agent_events")
      .select("id", { count: "exact", head: true })
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

export async function pipelineBreakdown(tenantId: string) {
  const db = getServiceSupabase();
  const r = await db.from("leads").select("status,score,source").eq("tenant_id", tenantId);
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

export async function recentDecisions(limit = 20): Promise<AgentDecision[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("agent_decisions")
    .select("*")
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

export async function recentLeads(tenantId: string, limit = 30): Promise<Lead[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("leads")
    .select("*")
    .eq("tenant_id", tenantId)
    .order("updated_at", { ascending: false })
    .limit(limit);
  return (r.data as Lead[]) || [];
}

export async function agentStates(): Promise<AgentStateSnapshot[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("agent_state_snapshot")
    .select("*")
    .order("last_tick_at", { ascending: false });
  return (r.data as AgentStateSnapshot[]) || [];
}

export async function recentEvents(limit = 25): Promise<AgentEvent[]> {
  const db = getServiceSupabase();
  const r = await db
    .from("agent_events")
    .select("*")
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
  const dayStart = new Date();
  dayStart.setHours(0, 0, 0, 0);
  const rows = await db
    .from("lead_interactions")
    .select("channel")
    .eq("tenant_id", tenantId)
    .gte("created_at", dayStart.toISOString());
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
  const db = getServiceSupabase();
  const q = db
    .from("integrations_health")
    .select("*")
    .order("service", { ascending: true });
  const r = tenantId ? await q.eq("tenant_id", tenantId) : await q;

  const expected = [
    "supabase",
    "stripe",
    "gmail",
    "n8n_inbound",
    "telegram",
    "browser_harness",
  ];
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
export async function mrrHistory(days = 30): Promise<
  Array<{ date: string; mrr: number; synthetic: boolean }>
> {
  const profile = await getActiveProfile();
  const current = Number(profile?.mrr_current_usd) || 0;
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
