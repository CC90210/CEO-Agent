/**
 * /api/exec-override
 *
 *   GET   — list recent override requests (default 24h window).
 *           Auth: a valid Supabase Auth session (cookies). The dashboard
 *           reads this from a server component or page route handler.
 *
 *   POST  — record a dashboard approve/deny decision for a request_id.
 *           Auth: x-oasis-profile-id + x-oasis-secret headers, same
 *           HMAC handshake as /api/outbound/log. The secret is sha256'd
 *           server-side and matched against n8n_webhook_secrets.secret_hash
 *           inside the SECURITY DEFINER RPC — so a leaked anon key cannot
 *           write a decision, only the holder of the raw secret can.
 *
 * The local source of truth remains state/empire_state.db on CC's machine.
 * This route writes to the Supabase `exec_overrides` mirror; the local
 * `scripts/exec_override_consumer.py` daemon polls the mirror and applies
 * the operator's decision to SQLite via state_manager.approve_override_request
 * (or deny_override_request). That local call HMAC-signs the row using
 * EMPIRE_OVERRIDE_HMAC_KEY — so the final auth gate for at-runtime block /
 * allow stays in the SQLite + secret stack on CC's machine, never on Vercel.
 *
 * Body (POST):
 *   {
 *     request_id: "req-xxxxxxxx",      // matches exec_overrides.request_id
 *     decision:   "approve" | "deny",
 *     reason?:    string               // optional one-line operator note
 *   }
 *
 * Returns: { ok: true, request_id } on success; { ok: false, error } otherwise.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, sha256 } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REQUEST_ID_RE = /^req-[0-9a-f]{8}$/i;

type DecisionBody = {
  request_id?: string;
  decision?: string;
  reason?: string;
};

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const sinceHours = Math.min(
    Math.max(parseInt(url.searchParams.get("since_hours") || "24", 10) || 24, 1),
    168,
  );
  const limit = Math.min(
    Math.max(parseInt(url.searchParams.get("limit") || "50", 10) || 50, 1),
    200,
  );
  const status = url.searchParams.get("status"); // 'pending' etc, optional

  const db = getServiceSupabase();
  const cutoff = new Date(Date.now() - sinceHours * 3600 * 1000).toISOString();

  let q = db
    .from("exec_overrides")
    .select(
      "request_id, ts, expires_at, command, command_hash, layer, reason, " +
        "status, approved_at, approved_by, consumed_at, " +
        "dashboard_decision, dashboard_decided_at, dashboard_decided_by, " +
        "dashboard_reason, consumer_synced_at, updated_at",
    )
    .gte("ts", cutoff)
    .order("ts", { ascending: false })
    .limit(limit);

  if (status) {
    q = q.eq("status", status);
  }

  const { data, error } = await q;
  if (error) {
    return bad(500, error.message);
  }

  return NextResponse.json({ ok: true, rows: data || [] });
}

export async function POST(req: NextRequest) {
  const profileId = req.headers.get("x-oasis-profile-id");
  const rawSecret = req.headers.get("x-oasis-secret");
  if (!profileId || !rawSecret) {
    return bad(401, "missing x-oasis-profile-id or x-oasis-secret header");
  }
  if (!UUID_RE.test(profileId)) {
    return bad(400, "x-oasis-profile-id is not a valid UUID");
  }

  let body: DecisionBody;
  try {
    body = (await req.json()) as DecisionBody;
  } catch {
    return bad(400, "body must be JSON");
  }

  if (!body.request_id || !REQUEST_ID_RE.test(body.request_id)) {
    return bad(400, "request_id must match req-xxxxxxxx");
  }
  if (body.decision !== "approve" && body.decision !== "deny") {
    return bad(400, "decision must be 'approve' or 'deny'");
  }
  const reason =
    typeof body.reason === "string" ? body.reason.slice(0, 500) : null;

  const secretHash = sha256(rawSecret);
  const db = getServiceSupabase();

  const r = await db.rpc("record_exec_override_decision_v1", {
    p_profile_id: profileId,
    p_secret_hash: secretHash,
    p_request_id: body.request_id,
    p_decision: body.decision,
    p_reason: reason,
  });

  if (r.error) {
    const code = (r.error as { code?: string }).code;
    const msg = r.error.message || "rpc failed";
    if (code === "42501" || /invalid_oasis_secret/i.test(msg)) {
      return bad(401, "invalid secret");
    }
    if (code === "P0001" || /request_not_found/i.test(msg)) {
      return bad(404, msg);
    }
    if (code === "P0002") {
      return bad(409, msg);
    }
    if (code === "P0003") {
      return bad(400, msg);
    }
    return bad(500, msg);
  }

  return NextResponse.json({ ok: true, request_id: r.data });
}
