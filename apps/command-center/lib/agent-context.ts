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

function fmtUSD(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

/**
 * Returns a short, plain-text block ready to append to the persona.
 * Empty string on any failure — the agent still works without it.
 */
export async function composeDashboardContext(ctx: ToolContext): Promise<string> {
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

  lines.push("---");
  return lines.join("\n");
}
