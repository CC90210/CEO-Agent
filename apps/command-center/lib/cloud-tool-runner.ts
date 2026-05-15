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
  /**
   * When true, the streaming loop does NOT execute this tool server-side.
   * Instead it yields { type: "tool_use_pending", resume_state } and exits
   * — the caller (the /api/chat route) emits a tool_use_pending SSE event,
   * the browser POSTs the call to its local bridge (Phase 2 of giggly-reef),
   * and the dashboard hits /api/chat/resume with the bridge-produced
   * tool_result to continue the Anthropic iteration.
   *
   * Mark this on tools that need the operator's local machine (file I/O,
   * shell, emails sent from their .env.agents credentials). Leave it off
   * for tools that the cloud runner can execute itself (records, http).
   */
  defer?: boolean;
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

  // ──────────────────────────────────────────────────────────────────
  // Bridge-proxied tools (defer: true) — these execute on the operator's
  // local machine via bravo_cli/bridge_tools.py. The runner pauses on
  // tool_use, the browser POSTs to localhost:9100/exec-tool, the result
  // gets POSTed back to /api/chat/resume. See bridge_tools.py for the
  // server-side implementations.
  //
  // If the bridge is offline when one of these fires, the browser-side
  // proxy returns is_error=true with "bridge_unreachable:..." in the
  // tool_result — the model sees the failure and can adapt (suggest the
  // operator start the bridge, or fall back to a cloud-only approach).
  // ──────────────────────────────────────────────────────────────────
  {
    name: "read_file",
    description:
      "Read a file from the operator's local machine. Relative paths resolve against the Bravo repo root; absolute paths work too. Returns up to 200KB of content; larger files get a head + truncation note. Use when the operator references a file, asks 'what's in X', or needs SKILL.md / brain/* context.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path OR path relative to the Bravo repo root." },
        max_bytes: { type: "number", description: "Optional cap on returned bytes (default 200000)." },
      },
      required: ["path"],
    },
  },
  {
    name: "write_file",
    description:
      "Create or overwrite a file on the operator's local machine. Use sparingly — confirm with the operator before writing. Parent directories are auto-created.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Destination path (absolute or repo-relative)." },
        content: { type: "string", description: "Full file content to write." },
        create_dirs: { type: "boolean", description: "Create missing parent dirs (default true)." },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "bash",
    description:
      "Run a shell command on the operator's local machine. 60-second timeout. Use for grep / find / git / npm / python invocations. Returns combined stdout+stderr with the exit code. For destructive commands (rm, drop, force-push), confirm with the operator first.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        command: { type: "string", description: "Shell command to execute." },
        cwd: { type: "string", description: "Optional working directory (default Bravo repo root)." },
        timeout_s: { type: "number", description: "Override default 60s timeout (max 300)." },
      },
      required: ["command"],
    },
  },
  {
    name: "send_email",
    description:
      "Send an email via the operator's Gmail account (uses scripts/google_tool.py with the operator's stored OAuth). Use when the operator says 'send an email to X' or 'reply to that lead'. Always include a professional subject and body. The 'from' field defaults to the operator's primary Gmail.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        to: { type: "string", description: "Recipient email address." },
        subject: { type: "string", description: "Email subject line." },
        body: { type: "string", description: "Email body (plain text or markdown — Gmail renders both)." },
        from: { type: "string", description: "Optional sender — defaults to operator's primary." },
      },
      required: ["to", "subject", "body"],
    },
  },
  {
    name: "send_sms",
    description:
      "Send an SMS via the operator's Twilio account. Honors the local opt-out list. Always include opt-out language ('Reply STOP to opt out') in the first touch — TCPA requires it. For cold outreach, confirm consent posture with the operator first.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        to: { type: "string", description: "Recipient phone number (E.164 format preferred, e.g. +12025551234)." },
        body: { type: "string", description: "SMS body. Keep under 160 chars to avoid multi-part billing." },
      },
      required: ["to", "body"],
    },
  },
  {
    name: "list_scripts",
    description:
      "List every Python script in the operator's scripts/ directory with a one-line synopsis. The catalog is ~50–150 entries depending on the tenant. Use this FIRST when you need to do something that isn't covered by the typed tools (read_file, write_file, bash, send_email, send_sms) — there's almost certainly a script already written for it. Scripts ending in '_tool.py' (e.g. stripe_tool.py, supabase_tool.py) are the documented CLI layer and support --json + --help. The 'filter' arg matches against script names (case-insensitive) — useful for narrowing down to 'stripe', 'send', 'snapshot', etc.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        filter: { type: "string", description: "Optional substring filter on script names (case-insensitive)." },
      },
    },
  },
  {
    name: "run_script",
    description:
      "Run a Python script from the operator's scripts/ directory by name. Returns exit_code, stdout, stderr, and (if stdout parses as JSON) a 'parsed' field with the structured data. 90-second timeout (override up to 300 via timeout_s). Most documented tools support `--help` to discover args and `--json` for machine-readable output — pass those in args. Use list_scripts first to discover what's available. For commands outside scripts/, use the bash tool instead.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        script: {
          type: "string",
          description: "Script filename, e.g. 'stripe_tool.py'. Resolved against scripts/ — no paths, no traversal. The .py suffix is optional.",
        },
        args: {
          type: "array",
          items: { type: "string" },
          description: "Argv list passed to the script. Example for stripe_tool.py: ['list-customers', '--limit', '10', '--json'].",
        },
        timeout_s: {
          type: "number",
          description: "Override the default 90s timeout (max 300).",
        },
        parse_json: {
          type: "boolean",
          description: "Try to parse stdout as JSON into a 'parsed' field. Default true. Set false for scripts that emit prose.",
        },
      },
      required: ["script"],
    },
  },
  {
    name: "list_skills",
    description:
      "List the operator's SKILL.md playbooks under skills/. Each entry has a name, description, and trigger phrases. Use this FIRST when the operator asks for something procedural (a briefing, a workflow, a recurring task) — there's almost certainly an existing playbook you should follow rather than improvising. The 'filter' arg matches case-insensitively across name, description, and trigger phrases.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        filter: {
          type: "string",
          description: "Optional substring filter. Matches against skill name, description, and triggers (case-insensitive). Try keywords from the operator's request: 'briefing', 'closing', 'debug', 'outreach'.",
        },
      },
    },
  },
  {
    name: "load_skill",
    description:
      "Load the full SKILL.md body for a named skill. Use after list_skills points at the right one. The file contains the SOP — step-by-step instructions you should follow verbatim instead of guessing. Skills often reference Python scripts in scripts/ — chain into run_script after reading.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Skill name as returned by list_skills (e.g. 'ceo-briefing', 'sales-closing'). Same as the directory name under skills/.",
        },
      },
      required: ["name"],
    },
  },

  // ──────────────────────────────────────────────────────────────────
  // Typed wrappers for the documented *_tool.py CLI layer — Phase C.
  // Each takes {action, args?} and shells out to the operator's local
  // scripts/<tool>.py with --json auto-appended. Same execution path
  // as run_script under the hood, just typed + advertised.
  // ──────────────────────────────────────────────────────────────────
  {
    name: "stripe",
    description:
      "Stripe SDK — universal payment access across all the operator's connected Stripe accounts. Actions: list-accounts, balance, customers, products, prices, invoices, subscriptions, charges, payment-links, create-payment-link, create-price, quick-link, create-customer, create-invoice, refund, events. Call action='--help' to see args for each. The wrapper auto-appends --json so you get structured output.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          description: "Subcommand name. Examples: 'customers', 'balance', 'create-payment-link', 'refund'. Pass '--help' to discover args for a specific action.",
        },
        args: {
          type: "array",
          items: { type: "string" },
          description: "Argv for the action. Example: ['--limit', '10', '--account', 'oasis_ai'].",
        },
      },
      required: ["action"],
    },
  },
  {
    name: "supabase",
    description:
      "Supabase — query the operator's database, list/get/insert/update/delete records, run raw SQL. Use this for ad-hoc data work that doesn't fit a manifest entity. The list_records / get_record / update_record cloud tools are usually a better choice for tenant_records data — supabase is for non-manifest tables (auth.users, integrations_health, etc.).",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        action: { type: "string", description: "Subcommand. Examples: 'query', 'list', 'get', 'insert', '--help'." },
        args: { type: "array", items: { type: "string" }, description: "Argv for the action." },
      },
      required: ["action"],
    },
  },
  {
    name: "n8n",
    description:
      "n8n workflow automation — list workflows, execute by name/ID, get execution status, manage webhooks. Use to kick off the operator's automated processes (lead enrichment, email sequences, etc.).",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        action: { type: "string", description: "Subcommand. Pass '--help' to discover." },
        args: { type: "array", items: { type: "string" }, description: "Argv for the action." },
      },
      required: ["action"],
    },
  },
  {
    name: "firecrawl",
    description:
      "Firecrawl — scrape a URL or crawl a site, return clean markdown. Use for competitor research, page content extraction, drafting from a real source. Falls back to http_get if Firecrawl credentials aren't configured.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        action: { type: "string", description: "Subcommand: 'scrape', 'crawl', 'map', '--help'." },
        args: { type: "array", items: { type: "string" }, description: "Argv for the action. Example for scrape: ['https://example.com', '--format', 'markdown']." },
      },
      required: ["action"],
    },
  },
  {
    name: "notebooklm",
    description:
      "NotebookLM — query the operator's curated knowledge base with citations. Use for grounded answers from their documented sources (vs. open-web speculation). Requires NotebookLM credentials in .env.agents; if missing, the action will return an is_error with the credential hint.",
    defer: true,
    input_schema: {
      type: "object",
      properties: {
        action: { type: "string", description: "Subcommand: 'query', 'list-notebooks', '--help'." },
        args: { type: "array", items: { type: "string" }, description: "Argv for the action." },
      },
      required: ["action"],
    },
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
  /**
   * Deferred tool — the model called a tool marked defer:true. The runner
   * captured the assistant turn (including the tool_use block) into the
   * resume_state below, then exits. The /api/chat route forwards this as an
   * SSE event so the browser can execute the tool locally and POST the
   * result to /api/chat/resume.
   */
  | {
      type: "tool_use_pending";
      tool_use_id: string;
      name: string;
      input: Record<string, unknown>;
      resume_state: ResumeState;
    }
  | { type: "done"; inputTokens: number; outputTokens: number }
  | { type: "error"; message: string };

type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error: boolean };

type AnthropicMessage =
  | { role: "user"; content: string | ContentBlock[] }
  | { role: "assistant"; content: ContentBlock[] };

/**
 * The payload that gets serialized to the browser, hops through the
 * /api/chat/resume route, and seeds the next iteration of the loop with
 * the pre-pause state intact. Contains everything resumeAnthropicTurn()
 * needs to continue the model's session without re-running prior iterations.
 *
 * Security note: this state passes through the browser. v1 trusts the
 * authed dashboard session (replay attacks only let an operator mess with
 * their OWN chat, no cross-tenant blast radius). If /api/chat/resume ever
 * becomes a multi-tenant or public surface, add HMAC signing here so a
 * malicious page can't synthesize states the server didn't issue.
 */
export type ResumeState = {
  /** Anthropic model ID — must match the model that was streaming the pause. */
  model: string;
  /** System prompt the iteration loop was running with. */
  system: string;
  /** Full conversation history, including the assistant turn with the
   *  deferred tool_use block. resumeAnthropicTurn appends the tool_result
   *  block on top before re-opening the stream. */
  history: AnthropicMessage[];
  /** Iteration index the pause happened on; used to enforce the iteration
   *  cap across the resume boundary. */
  iteration: number;
  /** Running totals so the resumed turn keeps incrementing usage instead
   *  of resetting to zero. */
  totalIn: number;
  totalOut: number;
  /** Echo of the original request's maxTokens / enableTools — applied to
   *  the resumed call so the second half of the conversation behaves
   *  identically to what would have happened without the pause. */
  maxTokens?: number;
  enableTools?: boolean;
  /** Per-agent tool allowlist from the manifest (Phase D). Same value
   *  the initial /api/chat call resolved. Carried in resume_state so the
   *  resumed turn sees an identical tool palette to the paused turn — if
   *  the operator changed it mid-pause, the change applies on the next
   *  fresh /api/chat call, not on this one. */
  toolPalette?: string[];
};

export type ToolLoopRequest = {
  apiKey: string;
  model: string;
  system: string;
  /** Conversation history, user-shaped (just role + string content). */
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  maxTokens?: number;
  /** When false, runs a no-tools straight stream (provider-fallback path). */
  enableTools?: boolean;
  /** When true, the deferred (bridge-routed) tools are filtered out of the
   *  palette sent to the model. Use this when the operator's bridge is
   *  offline — without it, the model sees send_email / bash / read_file
   *  in TOOL_DEFINITIONS, calls one, the browser proxy errors
   *  bridge_unreachable, the model retries, etc. Cleaner to tell the
   *  model up front that those tools don't exist this turn. */
  excludeDeferredTools?: boolean;
  /**
   * Per-agent tool allowlist from the tenant's manifest (Phase D).
   * Undefined → no filter; agent gets the full palette (preserves
   * pre-Phase-D behavior for existing tenants).
   * Empty array → agent is chat-only, no tools.
   * Populated → only these tool names get advertised to the model.
   *
   * Applied AFTER excludeDeferredTools — bridge-routed tools still get
   * filtered out when bridge is offline, even if they're in the palette.
   */
  toolPalette?: string[];
  /**
   * Phase F — bridge-advertised tool registry. The operator's local
   * bridge daemon reports which tools its installation actually has
   * (bravo_cli/bridge_tools.py:list_available_tools) on each heartbeat.
   * /api/chat reads bridge_pairings.tool_capabilities and passes it
   * here. null → no advertisement on record yet (older bridge daemons
   * or never-pinged pairings); runner falls back to the full bridge
   * tool palette in TOOL_DEFINITIONS. Empty array semantics are NOT
   * used here — null is the "no filter" signal.
   *
   * Only narrows defer:true tools. Cloud tools (defer:false) are
   * unaffected — they execute server-side on Vercel, not the bridge.
   */
  bridgeAdvertisedTools?: string[] | null;
};

export async function* streamAnthropicWithTools(
  req: ToolLoopRequest,
  ctx: ToolContext
): AsyncGenerator<StreamYield> {
  // Convert flat-string history → Anthropic content-block format. The
  // iteration helper handles the rest (initial call, tool dispatch,
  // deferred-tool pause/resume).
  const history: AnthropicMessage[] = req.messages
    .filter((m) => m.content && m.content.length > 0)
    .map((m) => ({ role: m.role, content: m.content }) as AnthropicMessage);

  yield* runIterationLoop({
    apiKey: req.apiKey,
    model: req.model,
    system: req.system,
    maxTokens: req.maxTokens,
    enableTools: req.enableTools,
    excludeDeferredTools: req.excludeDeferredTools,
    toolPalette: req.toolPalette,
    bridgeAdvertisedTools: req.bridgeAdvertisedTools,
    history,
    startIter: 0,
    startTotalIn: 0,
    startTotalOut: 0,
    ctx,
  });
}

/**
 * Resume a paused tool_use loop. Called by /api/chat/resume after the
 * browser has executed a deferred tool (e.g., via the bridge proxy at
 * localhost:9100/exec-tool) and POSTed back its result.
 *
 * Takes the ResumeState the runner emitted before pausing + the
 * tool_result the client produced. Appends the tool_result block onto
 * the message history and continues the iteration loop from where it
 * left off — same iteration cap, same running token totals.
 */
export async function* resumeAnthropicTurn(
  resume: ResumeState,
  toolUseId: string,
  toolResult: { content: string; is_error: boolean },
  ctx: ToolContext,
  apiKey: string,
): AsyncGenerator<StreamYield> {
  const history: AnthropicMessage[] = [...resume.history];
  // Append the user-side tool_result block that the browser produced.
  history.push({
    role: "user",
    content: [
      {
        type: "tool_result",
        tool_use_id: toolUseId,
        content: toolResult.content,
        is_error: toolResult.is_error,
      },
    ],
  });
  yield* runIterationLoop({
    apiKey,
    model: resume.model,
    system: resume.system,
    maxTokens: resume.maxTokens,
    enableTools: resume.enableTools,
    toolPalette: resume.toolPalette,
    history,
    startIter: resume.iteration + 1,
    startTotalIn: resume.totalIn,
    startTotalOut: resume.totalOut,
    ctx,
  });
}

type IterationLoopArgs = {
  apiKey: string;
  model: string;
  system: string;
  maxTokens?: number;
  enableTools?: boolean;
  excludeDeferredTools?: boolean;
  toolPalette?: string[];
  bridgeAdvertisedTools?: string[] | null;
  /** Pre-built history. Mutates as the loop appends turns. */
  history: AnthropicMessage[];
  /** Iteration index to start at (0 for fresh, N+1 for resume). */
  startIter: number;
  startTotalIn: number;
  startTotalOut: number;
  ctx: ToolContext;
};

/**
 * The core Anthropic tool_use streaming loop. Owns the per-iteration
 * fetch → parseSSE → block accumulation → tool-dispatch cycle. Two
 * callers: streamAnthropicWithTools (initial turn) and
 * resumeAnthropicTurn (post-deferred-tool resume).
 *
 * Yields delta/tool_use/tool_result/done/error as documented on
 * StreamYield. NEW for Phase 2: when a tool is marked defer:true on
 * its TOOL_DEFINITIONS entry, the loop captures the in-progress
 * history, yields tool_use_pending with a ResumeState, and exits.
 * Caller resumes via resumeAnthropicTurn.
 */
async function* runIterationLoop(
  args: IterationLoopArgs,
): AsyncGenerator<StreamYield> {
  const { apiKey, model, system, maxTokens, ctx, history } = args;
  const enableTools = args.enableTools !== false;
  // Resolve which tools the model sees this turn. Four filters compose
  // in order — most-restrictive last so the operator's intent wins:
  //
  //   1. excludeDeferredTools (bridge offline)
  //      Drops every bridge-routed tool. Set by /api/chat when no
  //      live bridge_pairings row is present.
  //
  //   2. bridgeAdvertisedTools (Phase F)
  //      When the operator's bridge has reported a capability list,
  //      restrict bridge tools to the intersection of what the bridge
  //      advertises AND what TOOL_DEFINITIONS knows. Skipped on null
  //      (older bridge daemons / never-pinged pairings) — falls back
  //      to the hardcoded TOOL_DEFINITIONS bridge set.
  //
  //   3. toolPalette (Phase D — manifest per-agent allowlist)
  //      Operator's intent: "what's this agent allowed to call?"
  //      Undefined = no filter; empty array = chat-only.
  //
  //   4. Cloud tools (defer:false) are unaffected by 1+2 — they
  //      execute server-side on Vercel, not the bridge.
  let activeTools: ToolDef[] = TOOL_DEFINITIONS;
  if (args.excludeDeferredTools) {
    activeTools = activeTools.filter((t) => !t.defer);
  } else if (args.bridgeAdvertisedTools !== undefined && args.bridgeAdvertisedTools !== null) {
    const advertised = new Set(args.bridgeAdvertisedTools);
    activeTools = activeTools.filter((t) => !t.defer || advertised.has(t.name));
  }
  if (args.toolPalette !== undefined) {
    const allow = new Set(args.toolPalette);
    activeTools = activeTools.filter((t) => allow.has(t.name));
  }
  let totalIn = args.startTotalIn;
  let totalOut = args.startTotalOut;

  for (let iter = args.startIter; iter < MAX_TOOL_ITERATIONS; iter++) {
    // Output tokens for THIS iteration only. Anthropic's message_delta
    // events report a cumulative count within a single message — not
    // per-event deltas — so we OVERWRITE on each frame and add the
    // final value into totalOut after the inner loop ends. Adding on
    // every event would double-count by a factor of (frames per message).
    const body: Record<string, unknown> = {
      model,
      max_tokens: maxTokens ?? 4096,
      stream: true,
      system,
      messages: history,
    };
    if (enableTools) {
      body.tools = activeTools;
    }

    const res = await fetchWithRetry("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": apiKey,
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
    let iterOut = 0;

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
        // Cumulative for THIS message — overwrite, don't add. Final
        // message_delta has the total; we add to totalOut after the loop.
        if (typeof data.usage?.output_tokens === "number") {
          iterOut = data.usage.output_tokens;
        }
      } else if (ev.event === "message_stop") {
        break;
      }
    }
    totalOut += iterOut;

    // If the model didn't ask to call any tools, we're done. Filter
    // tool_use blocks defensively: a block with no id or name would
    // get rejected on the next API call (Anthropic requires both), so
    // dropping it here gives a cleaner error than a 400 we'd have to
    // translate. In practice the API always emits both — this guards
    // against transient stream truncation, not normal traffic.
    const toolUses = blocks.filter(
      (b): b is Extract<ContentBlock, { type: "tool_use" }> =>
        b?.type === "tool_use" && typeof b.id === "string" && b.id.length > 0 && typeof b.name === "string" && b.name.length > 0
    );
    if (toolUses.length === 0 || stopReason !== "tool_use") {
      yield { type: "done", inputTokens: totalIn, outputTokens: totalOut };
      return;
    }

    // Append the assistant turn (text + tool_use blocks) to history.
    history.push({
      role: "assistant",
      content: blocks.filter(Boolean) as ContentBlock[],
    });

    // Phase 2 deferred-tool short-circuit: if ANY of the tool_use blocks
    // points at a tool marked defer:true, we can't keep iterating
    // server-side — the operator's local bridge has to execute the tool
    // and POST the result back via /api/chat/resume. Capture the in-
    // flight state and exit. (If a single turn mixes deferred + non-
    // deferred tools, we pause on the first deferred one and defer ALL
    // remaining tool calls to the resume; the model will re-emit them.
    // In practice the model issues one tool_use per turn unless we ask
    // for parallel-tools, which we don't.)
    const deferred = toolUses.find((tu) => {
      const def = TOOL_DEFINITIONS.find((d) => d.name === tu.name);
      return def?.defer === true;
    });
    if (deferred) {
      yield {
        type: "tool_use_pending",
        tool_use_id: deferred.id,
        name: deferred.name,
        input: deferred.input,
        resume_state: {
          model,
          system,
          history,
          iteration: iter,
          totalIn,
          totalOut,
          maxTokens,
          enableTools,
          toolPalette: args.toolPalette,
        },
      };
      return;
    }

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

export function cloudToolsPromptBlockV2(opts: { bridgeOnline?: boolean } = {}): string {
  const cloudTools = TOOL_DEFINITIONS.filter((t) => !t.defer);
  // Hide bridge tools from the persona block when the bridge is offline.
  // The Anthropic tools[] array sent on the API call is already filtered
  // by excludeDeferredTools in runIterationLoop; the persona block
  // following the same rule keeps the model from being told it has tools
  // it can't actually call this turn.
  const bridgeTools = opts.bridgeOnline === false
    ? []
    : TOOL_DEFINITIONS.filter((t) => t.defer);
  const lines: string[] = [];
  lines.push("");
  lines.push("---");
  lines.push("CLOUD TOOLS — REAL TOOL_USE");
  lines.push("");
  lines.push(
    "You're running in cloud mode with a real tool_use loop. The runtime exposes two tiers of tools — call them like any native Claude tool. All are tenant-scoped to the current operator and audit-logged."
  );
  lines.push("");
  lines.push("Cloud tools (always available, execute server-side on Vercel):");
  for (const t of cloudTools) {
    lines.push(`- ${t.name} — ${t.description}`);
  }
  if (bridgeTools.length > 0) {
    lines.push("");
    lines.push("Bridge tools (the operator's local bridge IS online — these execute on their machine via the dashboard's browser proxy):");
    for (const t of bridgeTools) {
      lines.push(`- ${t.name} — ${t.description}`);
    }
  }
  lines.push("");
  lines.push("Rules:");
  lines.push("- Prefer get_record over list_records once you have an ID.");
  lines.push("- Confirm with the operator before delete_record (no undo).");
  lines.push("- Don't use http_get/http_post for the operator's own integrations — that needs a connector.");
  lines.push("- For bridge tools (read_file, write_file, bash, send_email, send_sms): if a tool returns is_error with 'bridge_unreachable' in the body, the operator's local bridge isn't running. Tell them to start it (pm2 restart claude-bridge) instead of retrying.");
  lines.push("- For send_email / send_sms: always confirm content with the operator before sending. Include opt-out language on first-touch SMS.");
  lines.push("- Tool results return JSON; quote relevant fields in your reply.");
  if (bridgeTools.length > 0) {
    lines.push("");
    lines.push("DISCOVERY POSTURE (CRITICAL):");
    lines.push("- The operator has a library of pre-built playbooks (`skills/`) and Python tools (`scripts/`). DO NOT improvise workflows when one already exists — your job is to execute their established SOPs, not reinvent them.");
    lines.push("- For procedural requests (briefings, recurring workflows, named tasks): call list_skills FIRST to find the playbook, then load_skill to read its steps, then follow them.");
    lines.push("- For 'do X with service Y' requests (Stripe, Supabase, n8n, Gmail, Twilio, Firecrawl): call list_scripts to see if there's a tool wrapper, then run_script with `--help` to see its commands, then run_script with the real args. Most documented tools support `--json` — use it so you get structured output.");
    lines.push("- Only fall back to raw bash when nothing in skills/ or scripts/ fits.");
  }
  return lines.join("\n");
}

// SSE parser + safeText are shared with lib/providers.ts — see lib/sse-parser.ts.
