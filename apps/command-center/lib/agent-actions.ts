/**
 * Dashboard mutation handlers — the write counterpart to lib/agent-tools.ts.
 *
 * The chat agent emits <dashboard-action type="..." > JSON </dashboard-action>
 * markers when the operator asks for a change. The chat route parses these
 * markers AFTER the model finishes streaming, validates each, and runs the
 * matching handler — tenant-scoped, audit-logged.
 *
 * Trust model: the operator is authed, the agent runs in their session,
 * and we trust the OPERATOR's intent (not the model). Handlers validate
 * inputs hard; an out-of-bounds value gets rejected, not coerced.
 */

import { getServiceSupabase } from "./supabase-server";
import { ALL_AGENT_KEYS } from "./agents";

export type ActionContext = {
  tenantId: string;
  authUserId: string;
};

export type ActionResult =
  | { ok: true; type: string; summary: string }
  | { ok: false; type: string; error: string };

type Handler = (
  payload: Record<string, unknown>,
  ctx: ActionContext
) => Promise<ActionResult>;

const VALID_AGENT_KEYS = new Set(ALL_AGENT_KEYS);

const ACTIONS: Record<string, Handler> = {
  async update_profile(payload, ctx): Promise<ActionResult> {
    const allowed = new Set([
      "full_name",
      "display_name",
      "brand",
      "primary_agent",
      "mrr_target_usd",
      "mrr_current_usd",
      "mrr_target_date",
      "manifesto",
      "agents_enabled",
    ]);
    const update: Record<string, unknown> = {};
    const summaryParts: string[] = [];

    for (const k of Object.keys(payload)) {
      if (!allowed.has(k)) continue;
      const v = payload[k];

      if (k === "primary_agent") {
        if (typeof v !== "string" || !VALID_AGENT_KEYS.has(v)) {
          return { ok: false, type: "update_profile", error: `invalid primary_agent: ${v}` };
        }
        update[k] = v;
        summaryParts.push(`primary agent → ${v}`);
        continue;
      }
      if (k === "agents_enabled") {
        if (!Array.isArray(v) || v.some((x) => typeof x !== "string" || !VALID_AGENT_KEYS.has(x))) {
          return { ok: false, type: "update_profile", error: "agents_enabled must be array of valid agent keys" };
        }
        update[k] = v;
        summaryParts.push(`agents enabled: ${(v as string[]).join(", ")}`);
        continue;
      }
      if (k === "mrr_target_usd" || k === "mrr_current_usd") {
        const n = Number(v);
        if (!isFinite(n) || n < 0 || n > 10_000_000) {
          return { ok: false, type: "update_profile", error: `${k} out of range` };
        }
        update[k] = n;
        summaryParts.push(`${k} → $${n.toLocaleString()}`);
        continue;
      }
      if (k === "mrr_target_date") {
        if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) {
          return { ok: false, type: "update_profile", error: "mrr_target_date must be YYYY-MM-DD" };
        }
        update[k] = v;
        summaryParts.push(`MRR target date → ${v}`);
        continue;
      }
      // text fields
      if (typeof v !== "string") {
        return { ok: false, type: "update_profile", error: `${k} must be string` };
      }
      if (v.length > 4000) {
        return { ok: false, type: "update_profile", error: `${k} too long` };
      }
      update[k] = v;
      summaryParts.push(`${k} updated`);
    }

    if (Object.keys(update).length === 0) {
      return { ok: false, type: "update_profile", error: "no editable fields supplied" };
    }

    const db = getServiceSupabase();
    const r = await db
      .from("user_profiles")
      .update(update)
      .eq("auth_user_id", ctx.authUserId)
      .eq("tenant_id", ctx.tenantId)
      .select("id")
      .maybeSingle();
    if (r.error) return { ok: false, type: "update_profile", error: r.error.message };
    return { ok: true, type: "update_profile", summary: summaryParts.join(", ") };
  },

  async toggle_agent_enabled(payload, ctx): Promise<ActionResult> {
    const agentKey = String(payload.agent_key || "");
    const enabled = payload.enabled === true;
    if (!VALID_AGENT_KEYS.has(agentKey)) {
      return { ok: false, type: "toggle_agent_enabled", error: `invalid agent_key: ${agentKey}` };
    }
    const db = getServiceSupabase();
    const cur = await db
      .from("user_profiles")
      .select("agents_enabled")
      .eq("auth_user_id", ctx.authUserId)
      .eq("tenant_id", ctx.tenantId)
      .maybeSingle();
    if (cur.error || !cur.data) {
      return { ok: false, type: "toggle_agent_enabled", error: cur.error?.message || "profile not found" };
    }
    const current = new Set<string>(((cur.data.agents_enabled as string[]) || []).filter(Boolean));
    if (enabled) current.add(agentKey);
    else current.delete(agentKey);
    const next = Array.from(current);
    const upd = await db
      .from("user_profiles")
      .update({ agents_enabled: next })
      .eq("auth_user_id", ctx.authUserId);
    if (upd.error) return { ok: false, type: "toggle_agent_enabled", error: upd.error.message };
    return {
      ok: true,
      type: "toggle_agent_enabled",
      summary: `${enabled ? "enabled" : "disabled"} ${agentKey}`,
    };
  },

  async set_primary_agent(payload, ctx): Promise<ActionResult> {
    return ACTIONS.update_profile({ primary_agent: payload.agent_key }, ctx);
  },

  async update_mrr(payload, ctx): Promise<ActionResult> {
    const slim: Record<string, unknown> = {};
    if ("current_usd" in payload) slim.mrr_current_usd = payload.current_usd;
    if ("target_usd" in payload) slim.mrr_target_usd = payload.target_usd;
    if ("target_date" in payload) slim.mrr_target_date = payload.target_date;
    if (Object.keys(slim).length === 0) {
      return { ok: false, type: "update_mrr", error: "no MRR fields supplied" };
    }
    const r = await ACTIONS.update_profile(slim, ctx);
    return r.ok
      ? { ok: true, type: "update_mrr", summary: r.summary }
      : { ok: false, type: "update_mrr", error: r.error };
  },
};

/**
 * Parse <dashboard-action type="X">{...}</dashboard-action> markers from
 * the assistant's full response text. Returns the raw action specs;
 * caller validates + runs.
 */
export function extractActionMarkers(
  text: string
): Array<{ type: string; payload: Record<string, unknown> }> {
  const out: Array<{ type: string; payload: Record<string, unknown> }> = [];
  // Tolerant regex — matches either single-line or multi-line JSON payloads.
  const re = /<dashboard-action\s+type=["']([a-z_]+)["']\s*>([\s\S]*?)<\/dashboard-action>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    const type = m[1].toLowerCase();
    const raw = m[2].trim();
    if (!raw) {
      out.push({ type, payload: {} });
      continue;
    }
    try {
      const payload = JSON.parse(raw);
      if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        out.push({ type, payload: payload as Record<string, unknown> });
      }
    } catch {
      // Skip malformed payloads silently — agent will see no "applied" event
      // for that marker and likely retry on next turn.
    }
  }
  return out;
}

export async function runAction(
  spec: { type: string; payload: Record<string, unknown> },
  ctx: ActionContext
): Promise<ActionResult> {
  const handler = ACTIONS[spec.type];
  if (!handler) {
    return { ok: false, type: spec.type, error: `unknown_action:${spec.type}` };
  }
  try {
    return await handler(spec.payload, ctx);
  } catch (e) {
    return {
      ok: false,
      type: spec.type,
      error: e instanceof Error ? e.message : "handler_threw",
    };
  }
}

export function knownActionTypes(): string[] {
  return Object.keys(ACTIONS);
}
