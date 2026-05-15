/**
 * POST /api/bridge/ping — local bridge daemon heartbeat + integrations report.
 *
 * Called every 60s by `bravo bridge start` running on the operator's machine.
 * Authenticated with the bearer token issued at /api/auth/pair.
 *
 * Body:
 *   {
 *     services: {
 *       [service_slug: string]: {
 *         status: "healthy" | "degraded" | "down" | "unconfigured",
 *         metadata?: { version?: string, path?: string, ... },
 *         last_error?: string
 *       }
 *     },
 *     // Phase F of giggly-reef — bridge advertises which local tools its
 *     // installation has registered. Dashboard reads this when filtering
 *     // TOOL_DEFINITIONS so it doesn't tell the model about read_file when
 *     // the operator's bridge version doesn't ship that tool yet.
 *     tool_capabilities?: string[]
 *   }
 *
 * Effect:
 *   - Bumps bridge_pairings.last_seen_at + last_seen_ip for the active token.
 *   - Stamps bridge_pairings.tool_capabilities when present in the body.
 *   - Upserts each service into integrations_health for the resolved tenant.
 *
 * Returns: { ok, pairing_id, services_recorded, tool_capabilities_recorded }
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, sha256 } from "@/lib/api-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ServiceReport = {
  status?: "healthy" | "degraded" | "down" | "unconfigured";
  metadata?: Record<string, unknown>;
  last_error?: string;
};

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") || "";
  if (!auth.toLowerCase().startsWith("bearer ")) {
    return bad(401, "Bearer bridge token required");
  }
  const tokenPlain = auth.slice(7).trim();
  const tokenHash = sha256(tokenPlain);

  const db = getServiceSupabase();
  const pairing = await db
    .from("bridge_pairings")
    .select("id, tenant_id, user_id, revoked_at")
    .eq("bridge_token_hash", tokenHash)
    .maybeSingle();
  if (pairing.error || !pairing.data) return bad(401, "unknown bridge token");
  if (pairing.data.revoked_at) return bad(403, "bridge pairing revoked");

  // Resolve profile_id (integrations_health is keyed on profile_id, service)
  let profileId: string | null = null;
  if (pairing.data.user_id) {
    const pf = await db
      .from("user_profiles")
      .select("id")
      .eq("auth_user_id", pairing.data.user_id)
      .maybeSingle();
    profileId = pf.data?.id || null;
  }

  let body: {
    services?: Record<string, ServiceReport>;
    tool_capabilities?: string[];
  };
  try {
    body = await req.json();
  } catch {
    return bad(400, "body must be JSON");
  }

  // Touch the pairing's heartbeat. If the bridge included a tool_capabilities
  // list, stamp it on the pairing too — dashboard reads this when filtering
  // TOOL_DEFINITIONS for the /api/chat tool palette.
  const ipHeader = req.headers.get("x-forwarded-for") || req.headers.get("x-real-ip");
  const ip = ipHeader ? ipHeader.split(",")[0].trim() : null;
  const pairingUpdate: Record<string, unknown> = {
    last_seen_at: new Date().toISOString(),
    last_seen_ip: ip,
  };
  let toolCapsRecorded = false;
  if (Array.isArray(body.tool_capabilities)) {
    // Defensive — refuse anything that isn't a list of plain strings.
    const cleaned = body.tool_capabilities
      .filter((t): t is string => typeof t === "string" && t.length > 0)
      .map((t) => t.toLowerCase());
    pairingUpdate.tool_capabilities = cleaned;
    toolCapsRecorded = true;
  }
  await db
    .from("bridge_pairings")
    .update(pairingUpdate)
    .eq("id", pairing.data.id);

  // Upsert per-service health rows, tenant-scoped
  const tenantId = pairing.data.tenant_id;
  const services = body.services || {};
  let recorded = 0;
  for (const [service, report] of Object.entries(services)) {
    if (!service) continue;
    const status = (report.status || "unconfigured") as
      | "healthy" | "degraded" | "down" | "unconfigured";
    const payload: Record<string, unknown> = {
      tenant_id: tenantId,
      profile_id: profileId,
      service,
      status,
      last_ping_at: new Date().toISOString(),
      last_error: report.last_error || null,
      metadata: report.metadata || {},
    };
    const r = await db
      .from("integrations_health")
      .upsert(payload, { onConflict: "profile_id,service" });
    if (!r.error) recorded += 1;
  }

  return NextResponse.json({
    ok: true,
    pairing_id: pairing.data.id,
    services_recorded: recorded,
    tool_capabilities_recorded: toolCapsRecorded,
  });
}
