/**
 * Compose a "DASHBOARD STATE" block injected into the chat agent's system
 * prompt at the start of every turn.
 *
 * Why context injection vs full tool-calling: covers ~80% of the value
 * (operator asks "what's on my plate" / "how's MRR" / "any inbound" — agent
 * has the answer) at ~10% of the implementation surface (no provider-by-
 * provider tool_use handling, no multi-turn orchestration). When this hits
 * its limits — long-tail data, write actions — we can promote to real tool
 * calls using the same agent-tools.ts handlers.
 */

import { runTool, type ToolContext } from "./agent-tools";
import { listUnreadDb } from "./agent-inbox-db";
import { listRecords } from "./manifest/data";
import { getManifest } from "./manifest/loader";
import { resolveClientProfileSlug } from "./client-profiles";
import { getTenant } from "./queries";
import type { ManifestEntityDef } from "./manifest/schema";

function fmtUSD(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

/**
 * Detailed context-build result. The chat route uses `injectedInboxIds`
 * to mark those inbox messages read AFTER the assistant's response is
 * persisted — so a successful chat closes the inbox loop, but a failed
 * stream / disconnect leaves messages unread for the next attempt.
 *
 * Sole entry point. The earlier `composeDashboardContext` returning a
 * plain string was a transitional wrapper kept for one commit cycle;
 * removed once every caller switched to the IDs-aware shape.
 */
export type DashboardContextResult = {
  text: string;
  injectedInboxIds: string[];
};

export async function composeDashboardContextV2(ctx: ToolContext): Promise<DashboardContextResult> {
  const [mrrR, pipeR, inboundR, planR, integR] = await Promise.all([
    runTool("mrr_today", {}, ctx),
    runTool("pipeline_summary", {}, ctx),
    runTool("recent_inbound", { limit: 5 }, ctx),
    runTool("today_plan", {}, ctx),
    runTool("integrations_status", {}, ctx),
  ]);

  const lines: string[] = [];
  lines.push("---");
  lines.push("DASHBOARD STATE (auto-attached on every turn — use it; don't ask the operator for things you can already see):");
  lines.push("");

  // MRR
  if (mrrR.ok) {
    const m = mrrR.result as {
      current_usd: number;
      target_usd: number;
      pct_to_target: number;
      gap_usd: number;
      days_to_target: number | null;
    };
    const daysPart =
      typeof m.days_to_target === "number" ? `, ${m.days_to_target}d to deadline` : "";
    lines.push(
      `- MRR: ${fmtUSD(m.current_usd)} of ${fmtUSD(m.target_usd)} (${fmtPct(m.pct_to_target)}, gap ${fmtUSD(m.gap_usd)}${daysPart})`
    );
  }

  // Pipeline
  if (pipeR.ok) {
    const p = pipeR.result as {
      total: number;
      active: number;
      archived: number;
      stages: Record<string, number>;
    };
    const stageStr = Object.entries(p.stages || {})
      .map(([k, v]) => `${k}:${v}`)
      .join(" ");
    lines.push(`- Pipeline: ${p.active} active / ${p.archived} archived${stageStr ? ` (${stageStr})` : ""}`);
  }

  // Recent inbound
  if (inboundR.ok) {
    const inb = inboundR.result as {
      count: number;
      rows: Array<{ when: string; subject: string; from: unknown; intent: unknown }>;
    };
    if (inb.count > 0) {
      lines.push(`- Recent inbound (${inb.count}):`);
      for (const r of inb.rows.slice(0, 3)) {
        const subj = (r.subject || "(no subject)").slice(0, 80);
        const from = r.from ? ` from ${r.from}` : "";
        lines.push(`    · [${r.intent || "unclassified"}] ${subj}${from}`);
      }
    } else {
      lines.push("- Recent inbound: none in the last batch (n8n bridge may be stale — check /integrations).");
    }
  }

  // Today's plan
  if (planR.ok) {
    const pl = planR.result as {
      mission?: string | null;
      schedule?: Array<{ time_label?: string; title?: string; completed?: boolean }>;
    };
    if (pl.mission) lines.push(`- Today's mission: ${pl.mission}`);
    const sched = Array.isArray(pl.schedule) ? pl.schedule : [];
    if (sched.length > 0) {
      const open = sched.filter((s) => !s.completed).slice(0, 3);
      if (open.length > 0) {
        lines.push(`- Next blocks:`);
        for (const s of open) {
          const t = s.time_label ? `${s.time_label} ` : "";
          lines.push(`    · ${t}${s.title || "(unnamed)"}`);
        }
      }
    }
  }

  // Integrations — only mention if something is wrong
  if (integR.ok) {
    const i = integR.result as {
      healthy: string[];
      degraded: string[];
      down: string[];
      unconfigured: string[];
    };
    const broken = [...(i.down || []), ...(i.degraded || [])];
    if (broken.length > 0) {
      lines.push(`- Integrations needing attention: ${broken.join(", ")}`);
    }
    if (i.healthy && i.healthy.length > 0) {
      lines.push(`- Healthy integrations: ${i.healthy.length} (${i.healthy.slice(0, 6).join(", ")}${i.healthy.length > 6 ? ", ..." : ""})`);
    }
  }

  // Manifest pipeline snapshot — the row-level state of every entity in
  // the tenant's manifest data_model. Without this block, an agent like
  // Solara who's been asked "what's expiring in the next 60 days?" has
  // no way to answer — composeDashboardContextV2's MRR/pipeline tools
  // are OASIS-shaped (lead_score / pipeline_stage), they don't know
  // about funded_deal, renewal, application. Inject row counts + a
  // small sample per entity so the model can answer from real data
  // instead of hallucinating or asking the operator to paste.
  //
  // Best-effort. If the tenant has no manifest or the data layer hiccups,
  // skip the block; the rest of the context still renders.
  try {
    const manifestBlock = await composeManifestPipelineBlock(ctx.tenantId);
    if (manifestBlock) {
      lines.push("");
      lines.push(manifestBlock);
    }
  } catch {
    // swallowed — context build must never throw
  }

  // Inbox messages addressed to THIS agent — closes the inbox loop. When
  // the operator (or a sibling agent) posts to the inbox, the receiving
  // agent surfaces those messages at the top of its next chat session
  // and handles them before answering anything else. This is the
  // mechanism the /inbox page documents under "The closed loop."
  //
  // Mark-read happens in the chat route AFTER the assistant's response
  // is persisted — see app/api/chat/route.ts. We collect the message
  // IDs here and return them; the route stamps read_at on success.
  // Stream-failed / disconnected sessions leave messages unread so the
  // next attempt re-surfaces them.
  const injectedInboxIds: string[] = [];
  try {
    const inboxAll = await listUnreadDb(ctx.tenantId, ctx.agentKey);
    const inbox = inboxAll.slice(0, 5);
    if (inbox.length > 0) {
      lines.push("");
      lines.push(
        `INBOX FOR YOU (${inbox.length} unread message${inbox.length === 1 ? "" : "s"} — read and act on these BEFORE answering the operator's current question if relevant):`
      );
      for (const m of inbox) {
        const from = m.from_agent || "operator";
        const subj = (m.subject || "(no subject)").slice(0, 80);
        const body = (m.body || "").slice(0, 240).replace(/\s+/g, " ").trim();
        const pri = m.priority && m.priority !== "normal" ? `[${m.priority.toUpperCase()}] ` : "";
        lines.push(`- ${pri}from ${from}: ${subj}`);
        if (body) lines.push(`    ${body}${(m.body || "").length > 240 ? "…" : ""}`);
        injectedInboxIds.push(m.id);
      }
      lines.push(
        `(These messages are auto-marked read once you respond. They came from the operator or a sibling agent.)`
      );
    }
  } catch {
    // Inbox is best-effort; don't break the chat if Supabase hiccups.
  }

  lines.push("---");
  return { text: lines.join("\n"), injectedInboxIds };
}

/**
 * Manifest-aware pipeline snapshot. Returns null for tenants without a
 * resolvable manifest slug or whose manifest has no data_model — they
 * fall back to the OASIS-shaped tools alone.
 *
 * For each entity: total row count + the 3 most-recently-updated rows
 * (truncated to keep token spend predictable). Solara/Helios on a SunBiz
 * tenant get "5 leads (3 new, 2 qualified), 2 applications submitted, 1
 * offer expiring this week, 3 renewals in the 60-day window" without
 * needing a per-tenant pipeline tool.
 *
 * The block is labelled by entity so the model can spot "renewals" vs
 * "leads" vs "applications" by name. No domain-specific filters here —
 * the entity name is the contract.
 */
async function composeManifestPipelineBlock(tenantId: string): Promise<string | null> {
  // Resolve the manifest slug for this tenant. Same path the records
  // dashboard-action uses — keeps the answer "what data am I scoped
  // to?" consistent across the chat read path and the write path.
  const tenant = await getTenant(tenantId).catch(() => null);
  if (!tenant) return null;
  const slug = resolveClientProfileSlug(tenant);
  if (!slug) return null;
  let manifest;
  try {
    manifest = await getManifest(slug);
  } catch {
    return null;
  }
  const entities = manifest.data_model || [];
  if (entities.length === 0) return null;

  const blocks = await Promise.all(
    entities.map(async (entity) => formatEntityBlock(tenantId, entity))
  );
  const populated = blocks.filter((b): b is string => Boolean(b));
  if (populated.length === 0) return null;

  return [
    `PIPELINE STATE (${manifest.brand.name} — auto-attached every turn; quote from these rows, don't ask the operator to paste them):`,
    ...populated,
  ].join("\n");
}

async function formatEntityBlock(tenantId: string, entity: ManifestEntityDef): Promise<string | null> {
  try {
    const result = await listRecords({
      tenant_id: tenantId,
      entity: entity.name,
      limit: 3,
      // Default sort is updated_at DESC — most-recent rows first.
    });
    if (result.total === 0) {
      return `- ${entity.label} (${entity.name}): 0 rows`;
    }
    const sample = result.rows
      .map((r) => `    · ${summariseRow(entity, r.data, r.id)}`)
      .join("\n");
    return [`- ${entity.label} (${entity.name}): ${result.total} total — most recent:`, sample].join("\n");
  } catch {
    return null;
  }
}

function summariseRow(entity: ManifestEntityDef, data: Record<string, unknown>, id: string): string {
  // Pick a label field (business_name / name / title / contact_name / id),
  // then surface 2-3 highest-signal fields. Stage/status/amount fields
  // are the ones the model needs to reason about pipeline movement.
  const label =
    data.business_name || data.name || data.title || data.contact_name || id.slice(0, 8);
  const signal: string[] = [];
  for (const field of entity.fields) {
    if (signal.length >= 3) break;
    if (field.name === "business_name" || field.name === "name" || field.name === "title" || field.name === "contact_name") continue;
    const v = data[field.name];
    if (v === undefined || v === null || v === "") continue;
    // Truncate strings; numbers and enums render as-is.
    const valStr = typeof v === "string" ? (v.length > 40 ? v.slice(0, 37) + "..." : v) : String(v);
    signal.push(`${field.name}=${valStr}`);
  }
  return `${label}${signal.length ? ` [${signal.join(", ")}]` : ""}`;
}
