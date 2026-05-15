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
import { getManifest } from "./manifest/loader";
import {
  createRecord,
  deleteRecord,
  getRecord,
  listRecords,
  RecordsError,
  updateRecord,
} from "./manifest/data";
import { resolveClientProfileSlug } from "./client-profiles";
import type { ManifestEntityDef, TenantManifest } from "./manifest/schema";

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

  /**
   * create_record — agent writes a row into the tenant's manifest-defined
   * data model. Powers natural-language flows like "we just got a new funded
   * deal, $50k to ABC Corp, 12 months MCA" → row lands in /t/sun/funded-deals.
   *
   * Payload:
   *   { entity: "funded_deal", data: { lead_id, lender_id, amount_funded, ... } }
   *
   * Validation:
   *   - entity must exist in the tenant's manifest data_model
   *   - required fields must be present
   *   - enum fields must match an allowed value
   *   - the tenant_id from ctx is used as the writer; the agent can't write
   *     into another tenant's records
   */
  async create_record(payload, ctx): Promise<ActionResult> {
    const entityName = String(payload.entity || "").trim().toLowerCase();
    const data = payload.data;
    if (!entityName) {
      return { ok: false, type: "create_record", error: "entity required" };
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      return { ok: false, type: "create_record", error: "data must be an object" };
    }

    const ctxResolved = await resolveTenantManifest(ctx.tenantId);
    if (!ctxResolved.ok) return { ok: false, type: "create_record", error: ctxResolved.error };
    const entityDef = findEntity(ctxResolved.manifest, entityName);
    if (!entityDef) return { ok: false, type: "create_record", error: unknownEntityError(ctxResolved.manifest, entityName) };

    const validated = validateAgainstEntity(entityDef, data as Record<string, unknown>, { requireAll: true });
    if (!validated.ok) return { ok: false, type: "create_record", error: validated.error };

    try {
      const row = await createRecord({ tenant_id: ctx.tenantId, entity: entityName, data: validated.data });
      const label = recordLabel(validated.data, row.id);
      return { ok: true, type: "create_record", summary: `created ${entityDef.label.toLowerCase()}: ${label}` };
    } catch (err) {
      return { ok: false, type: "create_record", error: recordsErrorMessage(err, "create_failed") };
    }
  },

  /**
   * lookup_records — agent reads from the tenant's manifest data model.
   * Powers natural-language queries like "what's expiring in the next 60
   * days?" — Solara emits lookup_records with entity="renewal" and any
   * supported filters, the chat route returns the matching rows as part
   * of the action result so the model can quote real data.
   *
   * Payload:
   *   { entity, filter?: { field: value }, sort?: "field" | "-field",
   *     limit?: number (default 25, max 100) }
   *
   * Result.summary is JSON-encoded { count, rows: [{ id, ...data }] }.
   */
  async lookup_records(payload, ctx): Promise<ActionResult> {
    const entityName = String(payload.entity || "").trim().toLowerCase();
    if (!entityName) return { ok: false, type: "lookup_records", error: "entity required" };

    const ctxResolved = await resolveTenantManifest(ctx.tenantId);
    if (!ctxResolved.ok) return { ok: false, type: "lookup_records", error: ctxResolved.error };
    if (!findEntity(ctxResolved.manifest, entityName)) {
      return { ok: false, type: "lookup_records", error: unknownEntityError(ctxResolved.manifest, entityName) };
    }

    const rawFilter = payload.filter;
    const where: Record<string, string | number | boolean | null> = {};
    if (rawFilter && typeof rawFilter === "object" && !Array.isArray(rawFilter)) {
      for (const [k, v] of Object.entries(rawFilter as Record<string, unknown>)) {
        if (v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
          where[k] = v;
        }
      }
    }
    const sort = typeof payload.sort === "string" ? payload.sort : undefined;
    const limit = Math.max(1, Math.min(Number(payload.limit) || 25, 100));

    try {
      const result = await listRecords({
        tenant_id: ctx.tenantId,
        entity: entityName,
        where: Object.keys(where).length > 0 ? where : undefined,
        sort,
        limit,
      });
      const slim = result.rows.map((r) => ({ id: r.id, ...r.data }));
      return {
        ok: true,
        type: "lookup_records",
        summary: JSON.stringify({ count: result.total, rows: slim }),
      };
    } catch (err) {
      return { ok: false, type: "lookup_records", error: recordsErrorMessage(err, "lookup_failed") };
    }
  },

  /**
   * update_record — agent patches an existing row. Used for "mark this
   * funded deal as renewed", "set this lead to qualified", etc.
   *
   * Payload: { entity, id, patch: { field: newValue } }
   *
   * Validates patch fields against the entity schema like create_record,
   * but with requireAll=false (patches are partial). Required fields are
   * only re-validated if the patch supplies them.
   */
  async update_record(payload, ctx): Promise<ActionResult> {
    const entityName = String(payload.entity || "").trim().toLowerCase();
    const id = String(payload.id || "").trim();
    const patch = payload.patch;
    if (!entityName) return { ok: false, type: "update_record", error: "entity required" };
    if (!id) return { ok: false, type: "update_record", error: "id required" };
    if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
      return { ok: false, type: "update_record", error: "patch must be an object" };
    }

    const ctxResolved = await resolveTenantManifest(ctx.tenantId);
    if (!ctxResolved.ok) return { ok: false, type: "update_record", error: ctxResolved.error };
    const entityDef = findEntity(ctxResolved.manifest, entityName);
    if (!entityDef) return { ok: false, type: "update_record", error: unknownEntityError(ctxResolved.manifest, entityName) };

    const validated = validateAgainstEntity(entityDef, patch as Record<string, unknown>, { requireAll: false });
    if (!validated.ok) return { ok: false, type: "update_record", error: validated.error };

    try {
      const row = await updateRecord({
        tenant_id: ctx.tenantId,
        entity: entityName,
        id,
        patch: validated.data,
      });
      const label = recordLabel(row.data, row.id);
      const fieldsTouched = Object.keys(validated.data);
      return {
        ok: true,
        type: "update_record",
        summary: `updated ${entityDef.label.toLowerCase()} ${label}: ${fieldsTouched.join(", ")}`,
      };
    } catch (err) {
      return { ok: false, type: "update_record", error: recordsErrorMessage(err, "update_failed") };
    }
  },

  /**
   * delete_record — agent removes a row. Always confirms via summary text
   * so the operator-facing toast shows what was destroyed. The model's
   * persona spec instructs it to *never* emit delete_record without
   * explicit operator confirmation in the conversation.
   *
   * Payload: { entity, id }
   */
  async delete_record(payload, ctx): Promise<ActionResult> {
    const entityName = String(payload.entity || "").trim().toLowerCase();
    const id = String(payload.id || "").trim();
    if (!entityName) return { ok: false, type: "delete_record", error: "entity required" };
    if (!id) return { ok: false, type: "delete_record", error: "id required" };

    const ctxResolved = await resolveTenantManifest(ctx.tenantId);
    if (!ctxResolved.ok) return { ok: false, type: "delete_record", error: ctxResolved.error };
    const entityDef = findEntity(ctxResolved.manifest, entityName);
    if (!entityDef) return { ok: false, type: "delete_record", error: unknownEntityError(ctxResolved.manifest, entityName) };

    // Look up the row first so we can include a meaningful label in the
    // result summary; the toast tells the operator what got destroyed,
    // not just a UUID.
    const existing = await getRecord({ tenant_id: ctx.tenantId, entity: entityName, id }).catch(() => null);

    try {
      await deleteRecord({ tenant_id: ctx.tenantId, entity: entityName, id });
      const label = existing ? recordLabel(existing.data, id) : id;
      return { ok: true, type: "delete_record", summary: `deleted ${entityDef.label.toLowerCase()}: ${label}` };
    } catch (err) {
      return { ok: false, type: "delete_record", error: recordsErrorMessage(err, "delete_failed") };
    }
  },
};

// ---------------------------------------------------------------------------
// Shared helpers — manifest resolution + field validation for record actions.
// Extracted so create_record / update_record / lookup_records / delete_record
// share one source of truth for "which manifest scopes this tenant?" and
// "does this data fit the entity schema?".
// ---------------------------------------------------------------------------

async function resolveTenantManifest(
  tenantId: string
): Promise<{ ok: true; manifest: TenantManifest; slug: string } | { ok: false; error: string }> {
  const db = getServiceSupabase();
  const tenantRow = await db.from("tenants").select("slug, custom_fields").eq("id", tenantId).maybeSingle();
  if (tenantRow.error || !tenantRow.data) return { ok: false, error: "tenant not found" };
  const slug = resolveClientProfileSlug(tenantRow.data) || tenantRow.data.slug;
  if (!slug) return { ok: false, error: "no manifest slug resolvable for tenant" };
  try {
    const manifest = await getManifest(slug);
    return { ok: true, manifest, slug };
  } catch (err) {
    return { ok: false, error: `manifest load failed: ${err instanceof Error ? err.message : "unknown"}` };
  }
}

function findEntity(manifest: TenantManifest, entityName: string): ManifestEntityDef | undefined {
  return (manifest.data_model || []).find((e) => e.name === entityName);
}

function unknownEntityError(manifest: TenantManifest, entityName: string): string {
  const known = (manifest.data_model || []).map((e) => e.name).join(", ") || "(none)";
  return `unknown entity "${entityName}" — manifest has: ${known}`;
}

function recordsErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof RecordsError) return `${err.code}: ${err.message}`;
  if (err instanceof Error) return err.message;
  return fallback;
}

function recordLabel(data: Record<string, unknown>, fallback: string): string {
  return String(
    data.business_name ||
      data.name ||
      data.title ||
      data.contact_name ||
      fallback
  );
}

/**
 * Validate an arbitrary data object against an entity's field definitions.
 * Returns { ok: true, data: sanitized } if all supplied fields are valid;
 * { ok: false, error } otherwise.
 *
 * `requireAll`: true for create_record (all required fields must be present);
 * false for update_record (a patch may touch only some fields).
 */
function validateAgainstEntity(
  entity: ManifestEntityDef,
  input: Record<string, unknown>,
  opts: { requireAll: boolean }
): { ok: true; data: Record<string, unknown> } | { ok: false; error: string } {
  const sanitized: Record<string, unknown> = {};
  for (const field of entity.fields) {
    const supplied = field.name in input;
    const v = input[field.name];
    if (!supplied || v === undefined || v === null || v === "") {
      if (opts.requireAll && field.required) {
        return { ok: false, error: `${entity.name}.${field.name} is required` };
      }
      continue;
    }
    if (field.type === "enum") {
      if (!field.enum_values?.includes(String(v))) {
        return { ok: false, error: `${entity.name}.${field.name} must be one of: ${field.enum_values?.join(", ")}` };
      }
      sanitized[field.name] = v;
      continue;
    }
    if (field.type === "number") {
      const n = Number(v);
      if (!Number.isFinite(n)) return { ok: false, error: `${entity.name}.${field.name} must be a number` };
      sanitized[field.name] = n;
      continue;
    }
    if (field.type === "boolean") {
      sanitized[field.name] = Boolean(v);
      continue;
    }
    if (field.type === "date") {
      const s = String(v).trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || Number.isNaN(Date.parse(s))) {
        return { ok: false, error: `${entity.name}.${field.name} must be a YYYY-MM-DD date (got "${s}")` };
      }
      sanitized[field.name] = s;
      continue;
    }
    if (field.type === "datetime") {
      const s = String(v).trim();
      if (Number.isNaN(Date.parse(s))) {
        return { ok: false, error: `${entity.name}.${field.name} must be an ISO 8601 datetime (got "${s}")` };
      }
      sanitized[field.name] = s;
      continue;
    }
    // string + json — pass through.
    sanitized[field.name] = v;
  }
  return { ok: true, data: sanitized };
}

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
