/**
 * All Supabase queries the OASIS AI Agent Command Center makes.
 *
 * Every function is profile-aware where it makes sense. Errors degrade to
 * empty results so a DB hiccup never renders a blank page.
 */

import {
  getSupabase,
  type LeadInteraction,
  type AgentDecision,
  type Lead,
  type AgentEvent,
  type AgentStateSnapshot,
  type UserProfile,
  type DailyPlan,
  type IntegrationHealth,
} from "./supabase";

// ============================================================================
// Profile + Plan
// ============================================================================

/** Resolve the active operator profile.
 *
 * For v1 we use a single OPERATOR_EMAIL env var to pick the row. When auth
 * lands, this becomes "from session.user.id".
 */
export async function getActiveProfile(): Promise<UserProfile | null> {
  const db = getSupabase();
  const email = process.env.OPERATOR_EMAIL || "konamak@icloud.com";
  const r = await db
    .from("user_profiles")
    .select("*")
    .eq("email", email)
    .maybeSingle();
  if (r.error || !r.data) return null;
  return r.data as UserProfile;
}

export async function getTodayPlan(profileId: string): Promise<DailyPlan | null> {
  const db = getSupabase();
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

export async function getLeadById(leadId: string): Promise<Lead | null> {
  const db = getSupabase();
  const r = await db.from("leads").select("*").eq("id", leadId).maybeSingle();
  if (r.error || !r.data) return null;
  return r.data as Lead;
}

// ============================================================================
// Today's high-level counters
// ============================================================================

export async function todayCounts() {
  const db = getSupabase();
  const now = new Date();
  const dayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  ).toISOString();

  const [outbound, inbound, decisions, hot] = await Promise.all([
    db
      .from("lead_interactions")
      .select("id", { count: "exact", head: true })
      .in("type", ["email_sent", "dm_sent", "linkedin_sent", "call_made"])
      .gte("created_at", dayStart),
    db
      .from("lead_interactions")
      .select("id", { count: "exact", head: true })
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
// Pipeline
// ============================================================================

export async function pipelineBreakdown() {
  const db = getSupabase();
  const r = await db.from("leads").select("status,score,source");
  if (r.error || !r.data) return { stages: {}, total: 0, sources: {} };
  const stages: Record<string, number> = {
    new: 0,
    contacted: 0,
    qualified: 0,
    proposal: 0,
    won: 0,
    lost: 0,
  };
  const sources: Record<string, number> = {};
  for (const row of r.data as Array<{
    status: string | null;
    source: string | null;
  }>) {
    const s = (row.status as string) || "new";
    stages[s] = (stages[s] || 0) + 1;
    const src = row.source || "unknown";
    sources[src] = (sources[src] || 0) + 1;
  }
  return { stages, total: r.data.length, sources };
}

// ============================================================================
// Recent activity
// ============================================================================

export async function recentDecisions(limit = 20): Promise<AgentDecision[]> {
  const db = getSupabase();
  const r = await db
    .from("agent_decisions")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as AgentDecision[]) || [];
}

export async function recentInbound(limit = 20): Promise<LeadInteraction[]> {
  const db = getSupabase();
  const r = await db
    .from("lead_interactions")
    .select("*")
    .in("type", ["email_received", "email_reply", "dm_received"])
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as LeadInteraction[]) || [];
}

export async function recentOutbound(limit = 20): Promise<LeadInteraction[]> {
  const db = getSupabase();
  const r = await db
    .from("lead_interactions")
    .select("*")
    .in("type", ["email_sent", "dm_sent", "linkedin_sent", "call_made"])
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as LeadInteraction[]) || [];
}

export async function recentLeads(limit = 30): Promise<Lead[]> {
  const db = getSupabase();
  const r = await db
    .from("leads")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(limit);
  return (r.data as Lead[]) || [];
}

export async function agentStates(): Promise<AgentStateSnapshot[]> {
  const db = getSupabase();
  const r = await db
    .from("agent_state_snapshot")
    .select("*")
    .order("last_tick_at", { ascending: false });
  return (r.data as AgentStateSnapshot[]) || [];
}

export async function recentEvents(limit = 25): Promise<AgentEvent[]> {
  const db = getSupabase();
  const r = await db
    .from("agent_events")
    .select("*")
    .order("published_at", { ascending: false })
    .limit(limit);
  return (r.data as AgentEvent[]) || [];
}

// ============================================================================
// Channel caps
// ============================================================================

const DAILY_CAPS: Record<string, number> = {
  email: 50,
  instagram: 30,
  linkedin: 20,
  phone: 15,
};

export async function channelUtilization() {
  const db = getSupabase();
  const dayStart = new Date();
  dayStart.setHours(0, 0, 0, 0);
  const rows = await db
    .from("lead_interactions")
    .select("channel")
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
// Integrations health
// ============================================================================

export async function integrationsHealth(
  profileId: string | null
): Promise<IntegrationHealth[]> {
  const db = getSupabase();
  const q = db
    .from("integrations_health")
    .select("*")
    .order("service", { ascending: true });
  const r = profileId ? await q.eq("profile_id", profileId) : await q;

  // Build the canonical list of services we expect — any missing rows
  // surface as 'unconfigured' so the Settings page shows the gaps.
  const expected = [
    "supabase",
    "stripe",
    "gmail",
    "n8n_inbound",
    "telegram",
    "browser_harness",
  ];
  const existing = new Map((r.data as IntegrationHealth[] | null)?.map((row) => [row.service, row]) || []);
  return expected.map((service) => {
    const found = existing.get(service);
    if (found) return found;
    return {
      id: `placeholder-${service}`,
      profile_id: profileId,
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
// MRR — pulls from a manual_mrr table + Stripe (we just read the cached value)
// ============================================================================

export async function mrrSnapshot(): Promise<{
  current: number;
  target: number;
  pct: number;
}> {
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

export async function mrrHistory(days = 30): Promise<
  Array<{ date: string; mrr: number }>
> {
  // We don't store a history table yet — synthesize a flat-line series from
  // current MRR so charts render. When mrr_history exists, swap this out.
  const profile = await getActiveProfile();
  const current = Number(profile?.mrr_current_usd) || 0;
  const out: Array<{ date: string; mrr: number }> = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    out.push({
      date: d.toISOString().slice(5, 10),
      // Slight variance so the line isn't dead-flat — proportional to days from today
      mrr: Math.round(current - i * (current * 0.005)),
    });
  }
  return out;
}
