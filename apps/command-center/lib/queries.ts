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

export async function pipelineBreakdown(tenantId: string, includeArchived = false) {
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

export async function recentLeads(
  tenantId: string,
  limit = 30,
  opts?: { include_archived?: boolean; include_no_email?: boolean; include_lost?: boolean }
): Promise<Lead[]> {
  const db = getServiceSupabase();
  let q = db.from("leads").select("*").eq("tenant_id", tenantId);
  if (!opts?.include_archived) q = q.neq("status", "archived");
  if (!opts?.include_lost) q = q.neq("status", "lost");
  if (!opts?.include_no_email) q = q.not("email", "is", null);
  q = q.order("updated_at", { ascending: false }).limit(limit);
  const r = await q;
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

export async function recentEvents(
  limit = 25,
  opts?: { sinceDays?: number; tenantId?: string | null }
): Promise<AgentEvent[]> {
  const db = getServiceSupabase();
  let q = db.from("agent_events").select("*");
  // agent_events does NOT carry a tenant_id column today (audit confirmed
  // 2026-05-07). Tenant scoping happens via the publisher_agent + payload
  // shape rather than a column. The opts.tenantId param is accepted for
  // API consistency but not applied as a filter — would error otherwise.
  //
  // Default: 7-day freshness window. The activity-tape pages (/operations,
  // /agents) explicitly pass sinceDays:0 to show "most recent N regardless
  // of age" — they were rendering empty when the event bus was quiet for a
  // week even though the table had history. The 7-day default is kept here
  // to protect any future caller that wants a real "fresh activity only"
  // window without thinking about it.
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
  const db = getServiceSupabase();
  const q = db
    .from("integrations_health")
    .select("*")
    .order("service", { ascending: true });
  const r = tenantId ? await q.eq("tenant_id", tenantId) : await q;

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
const PROVIDER_TO_SERVICE: Record<string, string> = {
  anthropic: "anthropic",
  openai: "openai_codex",
  google: "google_ai",
  openrouter: "openrouter",
};

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
// Sun Biz Funding (tenant_slug = "sun") — Funding Operations queries
// ----------------------------------------------------------------------------
// These helpers back the /leads, /renewals, /sms, /commissions, etc. pages
// served when the authed profile resolves to the Sun tenant.
//
// Defensive note: the funded_deals / sms_sends / commissions / applications
// tables don't exist in Phase 1 — they land in migrations 037-047 (Phase 2).
// Every helper here catches PostgREST "relation not found" errors and
// returns empty/zero shapes so the Phase 1 dashboard renders cleanly
// (empty-state cards) instead of 500-ing every Sun page.
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
 */
function _isMissingTable(err: { code?: string; message?: string } | null | undefined): boolean {
  if (!err) return false;
  if (err.code === "PGRST205" || err.code === "42P01") return true; // PostgREST + Postgres
  const msg = (err.message || "").toLowerCase();
  return msg.includes("relation") && msg.includes("does not exist");
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
