/**
 * POST /api/outbound/log
 *
 * The outbound counterpart to /api/inbound/n8n. send_gateway.py POSTs every
 * confirmed send here. We auth via shared-secret header (same n8n_webhook_secrets
 * table — one HMAC per profile gates both inbound + outbound), then call
 * record_outbound_from_gateway_v1 which:
 *   1. Validates the secret hash
 *   2. Resolves tenant_id from the profile (Pipeline + Activity Tape were
 *      missing recent sends because send_gateway wrote tenant_id=NULL).
 *   3. Finds-or-creates the lead under the tenant
 *   4. Inserts lead_interactions WITH tenant_id stamped
 *   5. Publishes agent_events("outbound.sent") so Operations Activity Tape sees it
 *   6. Bumps integrations_health for the gateway green dot
 *
 * Headers required:
 *   x-oasis-profile-id  — operator profile UUID
 *   x-oasis-secret      — raw secret (we sha256 server-side)
 *
 * Body schema:
 *   {
 *     to_email: string,
 *     subject: string,
 *     body_preview?: string,         // truncated to 1KB on Python side already
 *     lead_id?: string (uuid),       // skip the find-or-create when known
 *     status?: "sent" | "queued" | "blocked" | "failed",   // default "sent"
 *     channel?: "email" | "dm" | "linkedin" | "sms" | "call",  // default "email"
 *     agent_source?: string,         // default "send_gateway"
 *     sent_at?: ISO timestamp,       // default now()
 *     metadata?: object              // free-form extras (template_id, sequence_id, etc)
 *   }
 *
 * Returns: { ok: true, interaction_id } on success, { ok: false, error } otherwise.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase } from "@/lib/supabase-server";
import { bad, sha256 } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type IncomingPayload = {
  to_email?: string;
  subject?: string;
  body_preview?: string;
  lead_id?: string;
  status?: string;
  channel?: string;
  agent_source?: string;
  sent_at?: string;
  metadata?: Record<string, unknown>;
  /** When the caller (send_gateway) already inserted the row locally, pass
   *  its id so the RPC dedupes — stamps tenant, publishes agent_events,
   *  but does NOT insert a second lead_interactions row. Future SaaS
   *  clients without local Supabase access omit this. */
  existing_interaction_id?: string;
};

// sha256 + bad imported from @/lib/api-helpers (consolidated 2026-05-09).

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function POST(req: NextRequest) {
  const profileId = req.headers.get("x-oasis-profile-id");
  const rawSecret = req.headers.get("x-oasis-secret");
  if (!profileId || !rawSecret) {
    return bad(401, "missing x-oasis-profile-id or x-oasis-secret header");
  }
  if (!UUID_RE.test(profileId)) {
    return bad(400, "x-oasis-profile-id is not a valid UUID");
  }

  let body: IncomingPayload;
  try {
    body = (await req.json()) as IncomingPayload;
  } catch {
    return bad(400, "body must be JSON");
  }
  if (!body.to_email || !body.subject) {
    return bad(400, "to_email and subject are required");
  }
  if (body.lead_id && !UUID_RE.test(body.lead_id)) {
    return bad(400, "lead_id is not a valid UUID");
  }
  if (body.existing_interaction_id && !UUID_RE.test(body.existing_interaction_id)) {
    return bad(400, "existing_interaction_id is not a valid UUID");
  }

  const secretHash = sha256(rawSecret);
  const db = getServiceSupabase();
  const r = await db.rpc("record_outbound_from_gateway_v1", {
    p_profile_id: profileId,
    p_secret_hash: secretHash,
    p_to_email: body.to_email,
    p_subject: body.subject,
    p_body_preview: body.body_preview || "",
    p_lead_id: body.lead_id || null,
    p_status: body.status || "sent",
    p_channel: body.channel || "email",
    p_agent_source: body.agent_source || "send_gateway",
    p_sent_at: body.sent_at || new Date().toISOString(),
    p_metadata: body.metadata || {},
    p_existing_interaction_id: body.existing_interaction_id || null,
  });

  if (r.error) {
    const code = (r.error as { code?: string }).code;
    if (code === "42501" || /invalid_outbound_secret/i.test(r.error.message || "")) {
      return bad(401, "invalid secret");
    }
    return bad(500, r.error.message || "rpc failed");
  }

  return NextResponse.json({ ok: true, interaction_id: r.data });
}

export async function GET() {
  return bad(405, "POST only");
}
