/**
 * /api/cron-jobs/poll — bearer-authed endpoint for the local bridge daemon.
 *
 * Phase I of giggly-reef harness completeness. The bridge polls this every
 * 60 seconds to pull its tenant's enabled cron jobs. Bridge resolves them
 * into local cron_engine.py SEED_JOBS and ticks them locally; this route
 * only delivers the spec, not the execution.
 *
 * Auth: same bridge_pairings bearer token /api/bridge/ping uses. No
 * session cookie — the bridge is a long-running daemon not a user agent.
 *
 * GET  → list jobs for the bridge's bound tenant.
 * POST → bridge reports back the outcome of a tick:
 *          { job_id, status: "success"|"error", output?, error? }
 *        Server stamps last_run_at / last_run_status / last_run_output /
 *        last_run_error / run_count++.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, sha256 } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function resolveBridge(req: NextRequest): Promise<{ tenantId: string } | null> {
  const auth = req.headers.get("authorization") || "";
  if (!auth.toLowerCase().startsWith("bearer ")) return null;
  const tokenPlain = auth.slice(7).trim();
  const tokenHash = sha256(tokenPlain);

  const db = getServiceSupabase();
  const pairing = await db
    .from("bridge_pairings")
    .select("tenant_id, revoked_at")
    .eq("bridge_token_hash", tokenHash)
    .maybeSingle();
  if (pairing.error || !pairing.data) return null;
  if (pairing.data.revoked_at) return null;
  return { tenantId: pairing.data.tenant_id };
}

export async function GET(req: NextRequest) {
  const bridge = await resolveBridge(req);
  if (!bridge) return bad(401, "invalid_or_revoked_bridge_token");

  const db = getServiceSupabase();
  // Only enabled jobs go to the bridge — disabled rows still live in the
  // table for the operator to re-enable later, but they don't tick.
  const { data, error } = await db
    .from("tenant_cron_jobs")
    .select(
      "id, agent_key, name, schedule, action_type, action_payload, enabled, last_run_at, run_count",
    )
    .eq("tenant_id", bridge.tenantId)
    .eq("enabled", true)
    .order("created_at", { ascending: true });
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, jobs: data || [], polled_at: new Date().toISOString() });
}

export async function POST(req: NextRequest) {
  const bridge = await resolveBridge(req);
  if (!bridge) return bad(401, "invalid_or_revoked_bridge_token");

  let body: any;
  try {
    body = await req.json();
  } catch {
    return bad(400, "invalid_json");
  }

  const jobId = String(body?.job_id || "").trim();
  if (!jobId) return bad(400, "missing_job_id");
  const status = String(body?.status || "").trim();
  if (status !== "success" && status !== "error") {
    return bad(400, "status_must_be_success_or_error");
  }
  const output = typeof body?.output === "string" ? body.output.slice(0, 8000) : null;
  const errorText = typeof body?.error === "string" ? body.error.slice(0, 2000) : null;

  const db = getServiceSupabase();
  // Pull current run_count so the increment is atomic-ish (Supabase doesn't
  // support raw SQL increments through the JS client without an RPC).
  // Race condition tolerated — two ticks within the same second on the
  // same job are pathological and operators noticing a count-of-1 short
  // is fine.
  const cur = await db
    .from("tenant_cron_jobs")
    .select("run_count")
    .eq("id", jobId)
    .eq("tenant_id", bridge.tenantId)
    .maybeSingle();
  if (cur.error || !cur.data) return bad(404, "job_not_found_or_other_tenant");
  const runCount = ((cur.data as { run_count?: number }).run_count || 0) + 1;

  const { error } = await db
    .from("tenant_cron_jobs")
    .update({
      last_run_at: new Date().toISOString(),
      last_run_status: status,
      last_run_output: output,
      last_run_error: errorText,
      run_count: runCount,
    })
    .eq("id", jobId)
    .eq("tenant_id", bridge.tenantId);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, job_id: jobId, run_count: runCount });
}
