/**
 * Cloud tool-runner — native Anthropic tool_use loop for the API-key chat path.
 *
 * Why this exists: the older lib/cloud-tools.ts is a TEXT-MARKER protocol —
 * the model emits `<cloud-tool name="...">{...}</cloud-tool>`, the stream
 * completes, then we parse + execute and surface results. That works but
 * has three real problems:
 *
 *   1. The model has to "remember" the syntax via a long persona block.
 *   2. Tools can't influence the model's subsequent reasoning — results
 *      arrive AFTER the message is done.
 *   3. We can't chain tools (read → decide → write) because there's only
 *      one round of execution.
 *
 * The native Anthropic tool_use protocol (https://docs.anthropic.com/en/docs/
 * agents-and-tools/tool-use/overview) solves all three. The model emits
 * tool_use blocks mid-stream, we execute, we send tool_result back, and
 * the loop continues until stop_reason !== "tool_use".
 *
 * This file owns:
 *   - TOOL_DEFINITIONS: the JSONSchema-shaped tool specs we send to Anthropic
 *   - executeTool(): server-side dispatcher; calls into agent-actions /
 *     cloud-tools / new HTTP helpers
 *   - streamAnthropicWithTools(): the orchestrator — opens an /v1/messages
 *     stream, accumulates tool_use blocks, executes them, re-opens the
 *     stream with tool_results appended, repeats. Yields {type:"delta"} for
 *     text and {type:"tool_use"} / {type:"tool_result"} so the API route
 *     can surface tool activity to the operator in real time.
 *
 * Safety: only tenant-scoped + URL-safelisted operations. No shell exec, no
 * file-system access. Power comes from data breadth (records, http, memory),
 * not from arbitrary code execution. Phase v2 will add a sandboxed shell
 * via E2B or Vercel Sandbox.
 */

import { fetchWithRetry } from "./retry";
import { getServiceSupabase } from "./supabase-server";
import { getManifest } from "./manifest/loader";
import { resolveClientProfileSlug } from "./client-profiles";
import {
  getRecord as dataGet,
  listRecords as dataList,
} from "./manifest/data";
import { runAction } from "./agent-actions";
import { CLOUD_TOOLS } from "./cloud-tools";
import { parseSSE, safeText } from "./sse-parser";

const ANTHROPIC_VERSION = "2023-06-01";
const MAX_TOOL_ITERATIONS = 8; // safety cap — prevents runaway tool loops
const HTTP_BODY_CAP_BYTES = 5 * 1024 * 1024; // 5 MB max external response
const HTTP_TIMEOUT_MS = 15_000;

// ============================================================================
// Tool context — server-only state needed to execute tools on behalf of a user
// ============================================================================

export type ToolContext = {
  tenantId: string;
  userId: string;
  agentKey: string;
  /** Required to call runAction (it uses auth_user_id for profile-bound writes). */
  authUserId: string;
};

export type ToolUseBlock = {
  id: string;
  name: string;
  input: Record<string, unknown>;
};

export type ToolResultBlock = {
  /** Anthropic tool_result.content — JSON-stringified data the model reads. */
  content: string;
  is_error: boolean;
  /** Human-summary shown to the operator in the chat UI alongside the chip. */
  summary: string;
};

// ============================================================================
// Tool definitions — Anthropic JSONSchema format
// ============================================================================

type ToolDef = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
};

/**
 * The full tool palette the cloud agent gets when running on the API-key path.
 * Mirrors Claude Code's "Read / Write / Edit / Bash / Glob / Grep" tools, but
 * the scope is the tenant's dashboard data + the open web, not the operator's
 * local filesystem.
 *
 * Ordering matters for the model's attention budget — put the most-likely
 * useful tools first.
 */
export const TOOL_DEFINITIONS: ToolDef[] = [
  {
    name: "list_records",
    description:
      "List rows from one of the tenant's manifest-defined entities (e.g., 'lead', 'application', 'funded_deal', 'renewal'). Use this when the operator asks 'what leads are in the pipeline?', 'show me recent applications', or 'what's expiring soon'. Returns up to 100 rows ordered by created_at desc unless you pass sort.",
    input_schema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "The entity name as defined in the tenant's manifest (e.g. 'lead', 'application', 'funded_deal')." },
        filter: { type: "object", description: "Optional field→value equality filters. Example: {\"status\": \"qualified\"}." },
        sort: { type: "string", description: "Optional 'field' (asc) or '-field' (desc). Example: '-created_at'." },
        limit: { type: "number", description: "Max rows to return. Default 25, max 100." },
      },
      required: ["entity"],
    },
  },
  {
    name: "get_record",
    description:
      "Fetch a single record by ID. Use this when you have a record's ID from list_records and need its full data, or when the operator gives you a specific ID.",
    input_schema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "Entity name (e.g. 'lead')." },
        id: { type: "string", description: "The record's UUID." },
      },
      required: ["entity", "id"],
    },
  },
  {
    name: "search_records",
    description:
      "Text-search across an entity's data fields. Use when the operator describes a record by name or a substring instead of giving an ID ('find the lead named Jonathan', 'which application mentions ABC Corp').",
    input_schema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "Entity name to search within." },
        query: { type: "string", description: "Substring to match (case-insensitive)." },
        limit: { type: "number", description: "Max rows to return. Default 10, max 25." },
      },
      required: ["entity", "query"],
    },
  },
  {
    name: "create_record",
    description:
      "Create a new row in one of the tenant's entities. Use when the operator says 'log a new funded deal', 'add this lead', 'note this renewal'. The 'data' object must include every field the entity marks as required.",
    input_schema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "Entity name." },
        data: { type: "object", description: "Field→value map matching the entity's schema." },
      },
      required: ["entity", "data"],
    },
  },
  {
    name: "update_record",
    description:
      "Patch one or more fields on an existing record. Use for status changes, stage advances, edits.",
    input_schema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "Entity name." },
        id: { type: "string", description: "Record UUID." },
        patch: { type: "object", description: "Field→newValue map. Only supplied fields are changed." },
      },
      required: ["entity", "id", "patch"],
    },
  },
  {
    name: "delete_record",
    description:
      "Hard-delete a record by ID. Confirm with the operator before calling — there is no undo.",
    input_schema: {
      type: "object",
      properties: {
        entity: { type: "string", description: "Entity name." },
        id: { type: "string", description: "Record UUID." },
      },
      required: ["entity", "id"],
    },
  },
  {
    name: "http_get",
    description:
      "Fetch a public URL via HTTP GET. Use for reading public web pages, public JSON APIs, or any URL the operator pastes. Returns the response body (truncated to 5MB) plus status code and content-type. Do NOT use for authenticated requests that require operator-scoped credentials — those need an integration connector instead.",
    input_schema: {
      type: "object",
      properties: {
        url: { type: "string", description: "Absolute URL (https:// preferred)." },
        headers: { type: "object", description: "Optional request headers as a string→string map." },
      },
      required: ["url"],
    },
  },
  {
    name: "http_post",
    description:
      "POST a JSON body to a public URL. Use for calling public APIs that don't require operator credentials. Same response shape as http_get.",
    input_schema: {
      type: "object",
      properties: {
        url: { type: "string", description: "Absolute URL." },
        body: { description: "JSON body (object or array) to send." },
        headers: { type: "object", description: "Optional request headers." },
      },
      required: ["url", "body"],
    },
  },
  {
    name: "lookup_lead_by_name",
    description:
      "Convenience shortcut over search_records for the 'lead' entity. Returns top 5 matches by score with status + last update.",
    input_schema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Partial name to search (e.g. 'Jonathan')." },
      },
      required: ["name"],
    },
  },
  {
    name: "list_open_leads",
    description:
      "Convenience shortcut: top N leads whose status is not won/lost/archived, highest score first.",
    input_schema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Default 10, max 25." },
      },
    },
  },
  {
    name: "integration_status",
    description:
      "List the operator's connected integrations (Stripe, Gmail, Late, etc.) with health. Use before recommending an action that needs an integration.",
    input_schema: { type: "object", properties: {} },
  },
];

// ============================================================================
// Server-side tool execution
// ============================================================================

export async function executeTool(
  name: string,
  input: Record<string, unknown>,
  ctx: ToolContext
): Promise<ToolResultBlock> {
  try {
    const data = await dispatch(name, input, ctx);
    return {
      content: JSON.stringify(data),
      is_error: false,
      summary: humanSummary(name, input, data),
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "tool_threw";
    return {
      content: JSON.stringify({ error: msg }),
      is_error: true,
      summary: `${name} failed: ${msg}`,
    };
  }
}

async function dispatch(
  name: string,
  input: Record<string, unknown>,
  ctx: ToolContext
): Promise<unknown> {
  switch (name) {
    case "list_records":
      return await toolListRecords(input, ctx);
    case "get_record":
      return await toolGetRecord(input, ctx);
    case "search_records":
      return await toolSearchRecords(input, ctx);
    case "create_record":
    case "update_record":
    case "delete_record": {
      // Delegate to the canonical agent-actions handler so cloud-tool writes
      // share the same validation, manifest-scoping, and audit log as the
      // text-marker path. Returns a summary string, not the row; that's fine
      // — the model can call get_record afterward if it needs the data.
      const r = await runAction({ type: name, payload: input }, {
        tenantId: ctx.tenantId,
        authUserId: ctx.authUserId,
      });
      if (!r.ok) throw new Error(r.error);
      return { ok: true, summary: r.summary };
    }
    case "http_get":
      return await toolHttpGet(input);
    case "http_post":
      return await toolHttpPost(input);
    case "lookup_lead_by_name":
    case "list_open_leads":
    case "integration_status": {
      const legacy = CLOUD_TOOLS[name];
      if (!legacy) throw new Error(`unknown_tool:${name}`);
      const r = await legacy.execute(input, ctx);
      if (!r.ok) throw new Error(r.error);
      return r.data;
    }
    default:
      throw new Error(`unknown_tool:${name}`);
  }
}

// ----------------------------------------------------------------------------
// Records tools — delegate to lib/manifest/data, validate against manifest
// ----------------------------------------------------------------------------

async function resolveEntity(tenantId: string, entityName: string) {
  const db = getServiceSupabase();
  const tenantRow = await db
    .from("tenants")
    .select("slug, custom_fields")
    .eq("id", tenantId)
    .maybeSingle();
  if (tenantRow.error || !tenantRow.data) throw new Error("tenant_not_found");
  const slug = resolveClientProfileSlug(tenantRow.data) || tenantRow.data.slug;
  if (!slug) throw new Error("manifest_slug_missing");
  const manifest = await getManifest(slug);
  if (!manifest) throw new Error("tenant_manifest_missing");
  const entityList = manifest.data_model || [];
  const entity = entityList.find(
    (e) => e.name.toLowerCase() === entityName.toLowerCase()
  );
  if (!entity) {
    const avail = entityList.map((e) => e.name).join(", ");
    throw new Error(`unknown_entity:${entityName} (available: ${avail || "none"})`);
  }
  return entity;
}

async function toolListRecords(input: Record<string, unknown>, ctx: ToolContext) {
  const entity = String(input.entity || "");
  await resolveEntity(ctx.tenantId, entity);
  const where: Record<string, string | number | boolean | null> = {};
  if (input.filter && typeof input.filter === "object" && !Array.isArray(input.filter)) {
    for (const [k, v] of Object.entries(input.filter as Record<string, unknown>)) {
      if (v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
        where[k] = v;
      }
    }
  }
  const sort = typeof input.sort === "string" ? input.sort : undefined;
  const limit = Math.max(1, Math.min(Number(input.limit) || 25, 100));
  const result = await dataList({
    tenant_id: ctx.tenantId,
    entity: entity.toLowerCase(),
    where: Object.keys(where).length > 0 ? where : undefined,
    sort,
    limit,
  });
  return {
    count: result.total,
    rows: result.rows.map((r) => ({ id: r.id, ...r.data })),
  };
}

async function toolGetRecord(input: Record<string, unknown>, ctx: ToolContext) {
  const entity = String(input.entity || "");
  const id = String(input.id || "");
  if (!id) throw new Error("id_required");
  await resolveEntity(ctx.tenantId, entity);
  const row = await dataGet({ tenant_id: ctx.tenantId, entity: entity.toLowerCase(), id });
  if (!row) throw new Error("record_not_found");
  return { id: row.id, ...row.data };
}

async function toolSearchRecords(input: Record<string, unknown>, ctx: ToolContext) {
  const entity = String(input.entity || "");
  const query = String(input.query || "").trim();
  if (!query || query.length < 2) throw new Error("query_too_short");
  const limit = Math.max(1, Math.min(Number(input.limit) || 10, 25));
  await resolveEntity(ctx.tenantId, entity);

  // No FTS on tenant_records.data (JSONB) — fetch a wide window then
  // substring-match in app code. Bounded at 200 rows so the memory cost
  // is fixed; if the operator has more, they should narrow via filter.
  const result = await dataList({
    tenant_id: ctx.tenantId,
    entity: entity.toLowerCase(),
    limit: 200,
  });
  const needle = query.toLowerCase();
  const matches = result.rows.filter((r) => {
    try {
      return JSON.stringify(r.data).toLowerCase().includes(needle);
    } catch {
      return false;
    }
  });
  return {
    count: matches.length,
    rows: matches.slice(0, limit).map((r) => ({ id: r.id, ...r.data })),
  };
}

// create_record / update_record / delete_record are dispatched directly to
// runAction in agent-actions.ts (see switch above) — no per-tool wrapper
// needed here. That keeps validation, manifest-scoping, and audit-logging
// in one place rather than duplicating them per call site.

// ----------------------------------------------------------------------------
// HTTP tools — open-web access with safety rails
// ----------------------------------------------------------------------------

function assertSafeUrl(url: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("invalid_url");
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new Error("unsupported_protocol");
  }
  // Block obvious SSRF targets — agents on the public dashboard should never
  // need to hit our own internal infra. Cloud-tool calls are explicitly
  // for public web reads.
  const host = parsed.hostname.toLowerCase();
  const blocked = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254", // AWS/Azure/GCP IMDS
    "metadata.google.internal",
  ];
  if (blocked.includes(host)) throw new Error("blocked_host");
  if (host.endsWith(".internal") || host.endsWith(".local")) {
    throw new Error("blocked_host");
  }
  // Private IP ranges — quick check, not exhaustive
  if (/^10\./.test(host) || /^192\.168\./.test(host) || /^172\.(1[6-9]|2[0-9]|3[01])\./.test(host)) {
    throw new Error("blocked_private_ip");
  }
  return parsed;
}

function sanitizeHeaders(input: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!input || typeof input !== "object") return out;
  for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
    if (typeof v !== "string") continue;
    const lower = k.toLowerCase();
    // Block setting hop-by-hop or auth-shaped headers — operator's API key
    // must NEVER be leaked into outbound headers the model controls.
    if (
      lower === "host" ||
      lower === "connection" ||
      lower === "content-length" ||
      lower === "cookie"
    ) {
      continue;
    }
    out[k] = v.slice(0, 2048);
  }
  return out;
}

async function fetchWithCap(url: URL, init: RequestInit): Promise<{ status: number; contentType: string; body: string; truncated: boolean }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);
  try {
    const res = await fetch(url.toString(), { ...init, signal: controller.signal });
    const contentType = res.headers.get("content-type") || "";
    const reader = res.body?.getReader();
    if (!reader) return { status: res.status, contentType, body: "", truncated: false };
    const decoder = new TextDecoder();
    let body = "";
    let bytes = 0;
    let truncated = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.length;
      if (bytes > HTTP_BODY_CAP_BYTES) {
        truncated = true;
        try { await reader.cancel(); } catch {}
        break;
      }
      body += decoder.decode(value, { stream: true });
    }
    return { status: res.status, contentType, body, truncated };
  } finally {
    clearTimeout(timer);
  }
}

async function toolHttpGet(input: Record<string, unknown>) {
  const url = assertSafeUrl(String(input.url || ""));
  const headers = sanitizeHeaders(input.headers);
  const r = await fetchWithCap(url, { method: "GET", headers });
  return {
    status: r.status,
    content_type: r.contentType,
    body: r.body.slice(0, 200_000), // cap returned-to-model size separately
    truncated: r.truncated,
    note: r.truncated
      ? "Response body was truncated at 5MB; only the first 200KB are shown to the model."
      : undefined,
  };
}

async function toolHttpPost(input: Record<string, unknown>) {
  const url = assertSafeUrl(String(input.url || ""));
  const headers = sanitizeHeaders(input.headers);
  if (!headers["content-type"] && !headers["Content-Type"]) {
    headers["content-type"] = "application/json";
  }
  const body = input.body === undefined ? "" : JSON.stringify(input.body);
  const r = await fetchWithCap(url, { method: "POST", headers, body });
  return {
    status: r.status,
    content_type: r.contentType,
    body: r.body.slice(0, 200_000),
    truncated: r.truncated,
    note: r.truncated
      ? "Response body was truncated at 5MB; only the first 200KB are shown to the model."
      : undefined,
  };
}

// ----------------------------------------------------------------------------
// Human-readable summaries for the chat UI tool-activity line
// ----------------------------------------------------------------------------

function humanSummary(name: string, input: Record<string, unknown>, data: unknown): string {
  switch (name) {
    case "list_records": {
      const d = data as { count: number };
      return `listed ${d.count} ${String(input.entity)} row${d.count === 1 ? "" : "s"}`;
    }
    case "get_record":
      return `read ${String(input.entity)} ${String(input.id).slice(0, 8)}…`;
    case "search_records": {
      const d = data as { count: number };
      return `searched ${String(input.entity)} for "${String(input.query)}" — ${d.count} match${d.count === 1 ? "" : "es"}`;
    }
    case "create_record":
    case "update_record":
    case "delete_record": {
      const d = data as { summary?: string };
      return d.summary || `${name.replace("_", " ")} ok`;
    }
    case "http_get": {
      const d = data as { status: number };
      return `GET ${String(input.url).slice(0, 60)} → ${d.status}`;
    }
    case "http_post": {
      const d = data as { status: number };
      return `POST ${String(input.url).slice(0, 60)} → ${d.status}`;
    }
    case "lookup_lead_by_name":
      return `lead lookup: "${String(input.name)}"`;
    case "list_open_leads":
      return `listed open leads`;
    case "integration_status":
      return `checked integrations`;
    default:
      return name;
  }
}

// ============================================================================
// Anthropic tool_use streaming loop
// ============================================================================

export type StreamYield =
  | { type: "delta"; text: string }
  | { type: "tool_use"; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; name: string; summary: string; ok: boolean }
  | { type: "done"; inputTokens: number; outputTokens: number }
  | { type: "error"; message: string };

type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error: boolean };

type AnthropicMessage =
  | { role: "user"; content: string | ContentBlock[] }
  | { role: "assistant"; content: ContentBlock[] };

export type ToolLoopRequest = {
  apiKey: string;
  model: string;
  system: string;
  /** Conversation history, user-shaped (just role + string content). */
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  maxTokens?: number;
  /** When false, runs a no-tools straight stream (provider-fallback path). */
  enableTools?: boolean;
};

export async function* streamAnthropicWithTools(
  req: ToolLoopRequest,
  ctx: ToolContext
): AsyncGenerator<StreamYield> {
  const enableTools = req.enableTools !== false;
  // Convert history to Anthropic content-block format. Initial round is all
  // strings; subsequent rounds we append { tool_use, tool_result } blocks.
  const history: AnthropicMessage[] = req.messages
    .filter((m) => m.content && m.content.length > 0)
    .map((m) => ({ role: m.role, content: m.content }) as AnthropicMessage);

  let totalIn = 0;
  let totalOut = 0;

  for (let iter = 0; iter < MAX_TOOL_ITERATIONS; iter++) {
    const body: Record<string, unknown> = {
      model: req.model,
      max_tokens: req.maxTokens ?? 4096,
      stream: true,
      system: req.system,
      messages: history,
    };
    if (enableTools) {
      body.tools = TOOL_DEFINITIONS;
    }

    const res = await fetchWithRetry("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": req.apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
      },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const detail = await safeText(res);
      yield {
        type: "error",
        message:
          res.status >= 500 || res.status === 429
            ? `provider_temporarily_unavailable:anthropic_${res.status}`
            : `anthropic_${res.status}:${detail}`,
      };
      return;
    }

    // Accumulate content blocks from this streaming turn. Text blocks emit
    // deltas to the caller as they arrive; tool_use blocks are buffered
    // until message_stop so we can dispatch them all at once.
    const blocks: ContentBlock[] = [];
    const blockBuffers = new Map<number, { kind: "text" | "tool_use"; partial: string }>();
    let stopReason: string | null = null;

    for await (const ev of parseSSE(res.body)) {
      const data: any = ev.data;
      if (!data) continue;
      if (ev.event === "message_start") {
        const usage = data.message?.usage;
        if (usage) totalIn += usage.input_tokens ?? 0;
      } else if (ev.event === "content_block_start") {
        const block = data.content_block;
        const idx = data.index as number;
        if (block?.type === "text") {
          blockBuffers.set(idx, { kind: "text", partial: "" });
          blocks[idx] = { type: "text", text: "" };
        } else if (block?.type === "tool_use") {
          blockBuffers.set(idx, { kind: "tool_use", partial: "" });
          blocks[idx] = {
            type: "tool_use",
            id: block.id,
            name: block.name,
            input: {},
          };
        }
      } else if (ev.event === "content_block_delta") {
        const idx = data.index as number;
        const buf = blockBuffers.get(idx);
        if (!buf) continue;
        const delta = data.delta;
        if (delta?.type === "text_delta" && typeof delta.text === "string") {
          buf.partial += delta.text;
          const b = blocks[idx];
          if (b?.type === "text") b.text += delta.text;
          yield { type: "delta", text: delta.text };
        } else if (delta?.type === "input_json_delta" && typeof delta.partial_json === "string") {
          buf.partial += delta.partial_json;
        }
      } else if (ev.event === "content_block_stop") {
        const idx = data.index as number;
        const buf = blockBuffers.get(idx);
        if (!buf) continue;
        if (buf.kind === "tool_use") {
          // Finalize the tool_use input — parse the accumulated JSON
          const b = blocks[idx];
          if (b?.type === "tool_use") {
            try {
              b.input = buf.partial ? JSON.parse(buf.partial) : {};
            } catch {
              b.input = {};
            }
          }
        }
        blockBuffers.delete(idx);
      } else if (ev.event === "message_delta") {
        if (data.delta?.stop_reason) stopReason = String(data.delta.stop_reason);
        if (data.usage?.output_tokens) totalOut += data.usage.output_tokens;
      } else if (ev.event === "message_stop") {
        break;
      }
    }

    // If the model didn't ask to call any tools, we're done.
    const toolUses = blocks.filter((b): b is Extract<ContentBlock, { type: "tool_use" }> => b?.type === "tool_use");
    if (toolUses.length === 0 || stopReason !== "tool_use") {
      yield { type: "done", inputTokens: totalIn, outputTokens: totalOut };
      return;
    }

    // Append the assistant turn (text + tool_use blocks) to history.
    history.push({
      role: "assistant",
      content: blocks.filter(Boolean) as ContentBlock[],
    });

    // Execute each tool call, surface to the operator, and queue the
    // tool_result blocks for the next turn.
    const resultBlocks: ContentBlock[] = [];
    for (const tu of toolUses) {
      yield { type: "tool_use", name: tu.name, input: tu.input };
      const result = await executeTool(tu.name, tu.input, ctx);
      yield {
        type: "tool_result",
        name: tu.name,
        summary: result.summary,
        ok: !result.is_error,
      };
      resultBlocks.push({
        type: "tool_result",
        tool_use_id: tu.id,
        content: result.content,
        is_error: result.is_error,
      });
    }
    history.push({ role: "user", content: resultBlocks });
    // Loop — the next iteration re-opens the stream with the new history.
  }

  // Hit the iteration cap — tell the operator instead of looping forever.
  yield {
    type: "error",
    message: `tool_loop_exhausted_after_${MAX_TOOL_ITERATIONS}_iterations`,
  };
}

// ============================================================================
// Prompt block — teaches non-Anthropic providers about the tool surface so
// they can still emit text markers. For Anthropic, the tools are passed via
// the API contract and this block is unused.
// ============================================================================

export function cloudToolsPromptBlockV2(): string {
  const lines: string[] = [];
  lines.push("");
  lines.push("---");
  lines.push("CLOUD TOOLS — REAL TOOL_USE");
  lines.push("");
  lines.push(
    "You're running in cloud mode with a real tool_use loop. The runtime exposes these tools — call them like any native Claude tool. Each tool is tenant-scoped to the current operator and audit-logged."
  );
  lines.push("");
  for (const t of TOOL_DEFINITIONS) {
    lines.push(`- ${t.name} — ${t.description}`);
  }
  lines.push("");
  lines.push("Rules:");
  lines.push("- Prefer get_record over list_records once you have an ID.");
  lines.push("- Confirm with the operator before delete_record (no undo).");
  lines.push("- Don't use http_get/http_post for the operator's own integrations — that needs a connector.");
  lines.push("- Tool results return JSON; quote relevant fields in your reply.");
  return lines.join("\n");
}

// SSE parser + safeText are shared with lib/providers.ts — see lib/sse-parser.ts.
