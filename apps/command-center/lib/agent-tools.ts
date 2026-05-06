/**
 * Agent tools — what the chat widget exposes to the LLM as callable functions.
 *
 * Phase 2 design: each tool is a server-side reader scoped to the authed
 * tenant. The chat route resolves tool calls, runs the handler, and feeds
 * the result back into the model's context as a tool message. Read-only
 * for now; write tools (propose_repo_edit, send_outreach_draft) come
 * online once the local bridge has a write-approval flow.
 *
 * Each tool declaration follows OpenAI function-calling shape so it
 * round-trips cleanly through OpenAI / OpenRouter (which accept the same
 * shape) and Anthropic (which we adapt at the provider boundary).
 */

import { getServiceSupabase } from "./supabase-server";

export type ToolDeclaration = {
  name: string;
  description: string;
  parameters: {
    type: "object";
    properties: Record<string, { type: string; description: string; default?: unknown }>;
    required?: string[];
  };
};

export type ToolContext = {
  tenantId: string;
  agentKey: string;
};

export type ToolHandler = (
  args: Record<string, unknown>,
  ctx: ToolContext
) => Promise<unknown>;

export const TOOL_DECLARATIONS: ToolDeclaration[] = [
  {
    name: "recent_inbound",
    description:
      "Read the most recent inbound emails / DMs the operator has received, classified by intent. Use when the operator asks about their inbox or replies they need to handle.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "number",
          description: "How many rows to return (1-25)",
          default: 10,
        },
      },
    },
  },
  {
    name: "pipeline_summary",
    description:
      "Snapshot of the operator's sales pipeline: total leads per stage (new / qualified / proposal / won / lost), top sources, archived counts. Use when the operator asks about the pipeline.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "mrr_today",
    description:
      "Current net MRR (USD), target, % to goal, and gap to goal. Use when the operator asks how revenue is doing.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "today_plan",
    description:
      "The operator's schedule for today — block-by-block, with completion state. Use when asked what's on the plate or what's next.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "integrations_status",
    description:
      "Which integrations are connected vs offline (FFmpeg, Whisper, Gmail, Stripe, etc). Use when something needs to happen and the operator might lack a connected tool.",
    parameters: { type: "object", properties: {} },
  },
];

/* ============================================================================
 * Handlers — server-side, all reads scoped to the authed tenantId.
 * ============================================================================ */

const HANDLERS: Record<string, ToolHandler> = {
  async recent_inbound(args, ctx) {
    const limitRaw = Number(args.limit ?? 10);
    const limit = Math.max(1, Math.min(25, isFinite(limitRaw) ? limitRaw : 10));
    const db = getServiceSupabase();
    const { data } = await db
      .from("lead_interactions")
      .select("id, type, subject, content, metadata, created_at")
      .eq("tenant_id", ctx.tenantId)
      .in("type", ["email_received", "email_reply", "dm_received"])
      .order("created_at", { ascending: false })
      .limit(limit);
    return {
      count: data?.length ?? 0,
      rows: (data || []).map((r) => ({
        when: r.created_at,
        type: r.type,
        subject: r.subject,
        from: ((r.metadata || {}) as Record<string, unknown>).from_identity || null,
        intent:
          ((((r.metadata || {}) as Record<string, unknown>).classification ||
            {}) as Record<string, unknown>).intent || "unclassified",
        excerpt: typeof r.content === "string" ? r.content.slice(0, 220) : null,
      })),
    };
  },

  async pipeline_summary(_args, ctx) {
    const db = getServiceSupabase();
    const { data } = await db
      .from("leads")
      .select("status, source")
      .eq("tenant_id", ctx.tenantId);
    const stages: Record<string, number> = {};
    const sources: Record<string, number> = {};
    let total = 0;
    let archived = 0;
    for (const r of (data || []) as Array<{ status: string; source: string | null }>) {
      total += 1;
      if (r.status === "archived") {
        archived += 1;
        continue;
      }
      stages[r.status] = (stages[r.status] || 0) + 1;
      const src = r.source || "unknown";
      sources[src] = (sources[src] || 0) + 1;
    }
    return { total, archived, active: total - archived, stages, sources };
  },

  async mrr_today(_args, ctx) {
    const db = getServiceSupabase();
    const { data: profile } = await db
      .from("user_profiles")
      .select("mrr_current_usd, mrr_target_usd, mrr_target_date")
      .eq("tenant_id", ctx.tenantId)
      .order("updated_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    const current = Number(profile?.mrr_current_usd) || 0;
    const target = Number(profile?.mrr_target_usd) || 5000;
    const gap = Math.max(0, target - current);
    const pct = target > 0 ? Math.round((current / target) * 1000) / 10 : 0;
    let days_to_target: number | null = null;
    if (profile?.mrr_target_date) {
      const dt = new Date(profile.mrr_target_date as string);
      days_to_target = Math.max(
        0,
        Math.round((dt.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      );
    }
    return {
      current_usd: current,
      target_usd: target,
      pct_to_target: pct,
      gap_usd: gap,
      days_to_target,
    };
  },

  async today_plan(_args, ctx) {
    const db = getServiceSupabase();
    const today = new Date().toISOString().slice(0, 10);
    // daily_plan is profile-scoped; resolve a profile in the tenant
    const { data: profile } = await db
      .from("user_profiles")
      .select("id, mission")
      .eq("tenant_id", ctx.tenantId)
      .order("updated_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (!profile) return { schedule: [], note: "no profile in tenant" };
    const { data: plan } = await db
      .from("daily_plan")
      .select("mission, schedule, primary_lead_id, primary_lead_play")
      .eq("profile_id", profile.id)
      .eq("plan_date", today)
      .maybeSingle();
    if (!plan) return { schedule: [], mission: null, note: "no plan for today" };
    return {
      mission: plan.mission || null,
      primary_lead_play: plan.primary_lead_play || null,
      schedule: Array.isArray(plan.schedule) ? plan.schedule : [],
    };
  },

  async integrations_status(_args, ctx) {
    const db = getServiceSupabase();
    const { data } = await db
      .from("integrations_health")
      .select("service, status, last_ping_at, last_error")
      .eq("tenant_id", ctx.tenantId);
    const groups: Record<string, string[]> = {
      healthy: [],
      degraded: [],
      down: [],
      unconfigured: [],
    };
    for (const r of (data || []) as Array<{ service: string; status: string }>) {
      (groups[r.status] || groups.unconfigured).push(r.service);
    }
    return {
      healthy: groups.healthy,
      degraded: groups.degraded,
      down: groups.down,
      unconfigured: groups.unconfigured,
    };
  },
};

export async function runTool(
  name: string,
  args: Record<string, unknown>,
  ctx: ToolContext
): Promise<{ ok: true; result: unknown } | { ok: false; error: string }> {
  const handler = HANDLERS[name];
  if (!handler) return { ok: false, error: `unknown_tool:${name}` };
  try {
    const result = await handler(args, ctx);
    return { ok: true, result };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "tool_failed" };
  }
}
