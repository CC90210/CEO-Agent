/**
 * /api/cron-jobs — operator-facing CRUD for tenant cron jobs (Phase I).
 *
 * GET  → list this tenant's jobs (RLS-scoped via the authed user).
 * POST → create a new job. Body: { agent_key, name, description?, schedule,
 *        action_type, action_payload, enabled? }
 *
 * Per-row update / delete lives at /api/cron-jobs/[id].
 *
 * Bridge daemon's poll endpoint lives at /api/cron-jobs/poll — a separate
 * bearer-token-authed route so the daemon doesn't need a session cookie.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Action types we accept on create. Discriminator + payload-shape validation
// done in code (vs JSON-schema) because the shapes are small and clear.
const VALID_ACTION_TYPES = ["script_run", "snapshot_run", "agent_prompt", "webhook_post"] as const;
type ActionType = (typeof VALID_ACTION_TYPES)[number];

// Minimal cron-expression validator. Five fields, each one of:
//   *, N, N-M, */N, N,M,K
// More exotic forms (L, W, #, named months/dow) intentionally rejected — the
// bridge's cron_engine uses standard Python schedule semantics, and refusing
// the weird forms keeps validation simple. Operators who need them can drop
// down to bash from the agent chat.
const CRON_FIELD = /^(\*|\*\/\d+|\d+(-\d+)?(\/\d+)?(,\d+(-\d+)?(\/\d+)?)*)$/;
function isValidCron(expr: string): boolean {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  return parts.every((p) => CRON_FIELD.test(p));
}

async function resolveTenantId(): Promise<string | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const { data } = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return (data as { tenant_id: string | null } | null)?.tenant_id ?? null;
}

async function resolveUserId(): Promise<string | null> {
  const user = await getSessionUser();
  return user?.id ?? null;
}

export async function GET() {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("tenant_cron_jobs")
    .select(
      "id, agent_key, name, description, schedule, action_type, action_payload, enabled, last_run_at, last_run_status, last_run_output, last_run_error, run_count, created_at, updated_at",
    )
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false });
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, jobs: data || [] });
}

export async function POST(req: NextRequest) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const userId = await resolveUserId();

  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const name = String(body?.name || "").trim().slice(0, 80);
  if (!name) return NextResponse.json({ ok: false, error: "name_required" }, { status: 400 });

  const schedule = String(body?.schedule || "").trim();
  if (!isValidCron(schedule)) {
    return NextResponse.json(
      { ok: false, error: "invalid_cron_expression", hint: "Use 5-field cron syntax (m h dom mon dow)." },
      { status: 400 },
    );
  }

  const actionType = String(body?.action_type || "") as ActionType;
  if (!VALID_ACTION_TYPES.includes(actionType)) {
    return NextResponse.json(
      { ok: false, error: `invalid_action_type:${actionType}`, valid: VALID_ACTION_TYPES },
      { status: 400 },
    );
  }
  const actionPayload = body?.action_payload && typeof body.action_payload === "object" ? body.action_payload : {};

  // Per-type payload validation. Keeps malformed payloads from reaching the
  // bridge where they'd just error silently in cron_engine.
  const payloadErr = validateActionPayload(actionType, actionPayload);
  if (payloadErr) {
    return NextResponse.json({ ok: false, error: payloadErr }, { status: 400 });
  }

  const agentKey = String(body?.agent_key || "bravo").toLowerCase();
  const description = body?.description ? String(body.description).slice(0, 500) : null;
  const enabled = body?.enabled !== false;

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("tenant_cron_jobs")
    .insert({
      tenant_id: tenantId,
      agent_key: agentKey,
      name,
      description,
      schedule,
      action_type: actionType,
      action_payload: actionPayload,
      enabled,
      created_by: userId,
    })
    .select()
    .single();
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, job: data });
}

/**
 * Per-action-type payload shape check. Returns an error string on failure,
 * null on success. Kept loose — the bridge is the real validator (it
 * resolves paths, runs subprocesses, etc.) and there's no point being
 * strict here at the API edge.
 */
function validateActionPayload(type: ActionType, payload: Record<string, unknown>): string | null {
  switch (type) {
    case "script_run":
      if (typeof payload.script !== "string" || !payload.script.trim()) {
        return "script_run requires action_payload.script (string)";
      }
      if (payload.args !== undefined && !Array.isArray(payload.args)) {
        return "script_run.args must be an array if provided";
      }
      return null;
    case "snapshot_run":
      if (typeof payload.snapshot !== "string" || !payload.snapshot.trim()) {
        return "snapshot_run requires action_payload.snapshot (string)";
      }
      return null;
    case "agent_prompt":
      if (typeof payload.prompt !== "string" || !payload.prompt.trim()) {
        return "agent_prompt requires action_payload.prompt (string)";
      }
      return null;
    case "webhook_post":
      if (typeof payload.url !== "string" || !/^https?:\/\//.test(payload.url)) {
        return "webhook_post requires action_payload.url (http/https URL)";
      }
      return null;
  }
}
