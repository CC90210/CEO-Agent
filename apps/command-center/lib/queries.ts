/**
 * All Supabase queries the command center makes, in one file.
 *
 * Each function returns plain JSON the pages can render directly. Errors
 * are caught and degraded to empty arrays / zero counts so a DB hiccup
 * never renders a blank page.
 */

import { getSupabase, type LeadInteraction, type AgentDecision, type Lead, type AgentEvent, type AgentStateSnapshot } from "./supabase";

// ---- Today's high-level counters -------------------------------------------

export async function todayCounts() {
  const db = getSupabase();
  const now = new Date();
  const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();

  // Outbound today
  const outbound = await db
    .from("lead_interactions")
    .select("id", { count: "exact", head: true })
    .eq("channel", "email")
    .eq("type", "email_sent")
    .gte("created_at", dayStart);

  // Inbound today
  const inbound = await db
    .from("lead_interactions")
    .select("id", { count: "exact", head: true })
    .eq("type", "email_received")
    .gte("created_at", dayStart);

  // Decisions today
  const decisions = await db
    .from("agent_decisions")
    .select("id", { count: "exact", head: true })
    .gte("created_at", dayStart);

  // Hot / escalated events
  const hot = await db
    .from("agent_events")
    .select("id", { count: "exact", head: true })
    .eq("event_type", "inbound.classified")
    .eq("severity", "warn")
    .gte("published_at", dayStart);

  return {
    outbound: outbound.count ?? 0,
    inbound: inbound.count ?? 0,
    decisions: decisions.count ?? 0,
    hot: hot.count ?? 0,
  };
}

// ---- Pipeline breakdown ----------------------------------------------------

export async function pipelineBreakdown() {
  const db = getSupabase();
  const r = await db.from("leads").select("status,score");
  if (r.error || !r.data) return { stages: {}, total: 0 };
  const stages: Record<string, number> = {
    new: 0, contacted: 0, qualified: 0, proposal: 0, won: 0, lost: 0,
  };
  for (const row of r.data) {
    const s = (row.status as string) || "new";
    stages[s] = (stages[s] || 0) + 1;
  }
  return { stages, total: r.data.length };
}

// ---- Recent decisions ------------------------------------------------------

export async function recentDecisions(limit = 20): Promise<AgentDecision[]> {
  const db = getSupabase();
  const r = await db
    .from("agent_decisions")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as AgentDecision[]) || [];
}

// ---- Recent inbound --------------------------------------------------------

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

// ---- Recent outbound -------------------------------------------------------

export async function recentOutbound(limit = 20): Promise<LeadInteraction[]> {
  const db = getSupabase();
  const r = await db
    .from("lead_interactions")
    .select("*")
    .in("type", ["email_sent", "dm_sent", "linkedin_sent"])
    .order("created_at", { ascending: false })
    .limit(limit);
  return (r.data as LeadInteraction[]) || [];
}

// ---- Recent leads ----------------------------------------------------------

export async function recentLeads(limit = 30): Promise<Lead[]> {
  const db = getSupabase();
  const r = await db
    .from("leads")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(limit);
  return (r.data as Lead[]) || [];
}

// ---- Agent state (the C-Suite pulse) ---------------------------------------

export async function agentStates(): Promise<AgentStateSnapshot[]> {
  const db = getSupabase();
  const r = await db
    .from("agent_state_snapshot")
    .select("*")
    .order("last_tick_at", { ascending: false });
  return (r.data as AgentStateSnapshot[]) || [];
}

// ---- Recent agent events (the event bus tape) ------------------------------

export async function recentEvents(limit = 25): Promise<AgentEvent[]> {
  const db = getSupabase();
  const r = await db
    .from("agent_events")
    .select("*")
    .order("published_at", { ascending: false })
    .limit(limit);
  return (r.data as AgentEvent[]) || [];
}

// ---- Gateway daily-cap utilization ----------------------------------------

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
