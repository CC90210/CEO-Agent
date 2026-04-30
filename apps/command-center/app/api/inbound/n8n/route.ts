/**
 * POST /api/inbound/n8n
 *
 * The n8n inbound bridge. The "OASIS Inbound Qualifier" workflow POSTs every
 * classified email here; we authenticate via shared-secret header, then call
 * the record_inbound_from_n8n_v2 RPC which:
 *   1. Validates the secret hash
 *   2. Finds-or-creates a lead for the from email
 *   3. Records the interaction with classification metadata
 *   4. Bumps integrations_health for the green dot in Settings
 *
 * Headers required:
 *   x-oasis-profile-id  — the profile the webhook is owned by (uuid)
 *   x-oasis-secret      — the raw secret (we sha256 it server-side)
 *
 * Body schema:
 *   {
 *     from_email: string,
 *     subject: string,
 *     body: string,
 *     classification: { intent, sentiment, priority, ... },  // from n8n classifier
 *     received_at?: ISO timestamp                             // optional, defaults now()
 *   }
 *
 * Returns: { ok: true, interaction_id } on success, { ok: false, error } on auth/validation fail
 */

import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";
import { getSupabase } from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const runtime = "nodejs"; // service role + sha256 → Node, not edge

type IncomingPayload = {
  from_email?: string;
  subject?: string;
  body?: string;
  classification?: Record<string, unknown>;
  received_at?: string;
};

function sha256(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

export async function POST(req: NextRequest) {
  // 1. Auth headers
  const profileId = req.headers.get("x-oasis-profile-id");
  const rawSecret = req.headers.get("x-oasis-secret");
  if (!profileId || !rawSecret) {
    return bad(401, "missing x-oasis-profile-id or x-oasis-secret header");
  }
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(profileId)
  ) {
    return bad(400, "x-oasis-profile-id is not a valid UUID");
  }

  // 2. Body parse
  let body: IncomingPayload;
  try {
    body = (await req.json()) as IncomingPayload;
  } catch {
    return bad(400, "body must be JSON");
  }
  if (!body.from_email || !body.subject) {
    return bad(400, "from_email and subject are required");
  }

  // 3. Hash secret + call RPC (the RPC re-validates the hash against the table)
  const secretHash = sha256(rawSecret);
  const db = getSupabase();
  const r = await db.rpc("record_inbound_from_n8n_v2", {
    p_profile_id: profileId,
    p_secret_hash: secretHash,
    p_from_email: body.from_email,
    p_subject: body.subject,
    p_body: body.body || "",
    p_classification: body.classification || {},
    p_received_at: body.received_at || new Date().toISOString(),
  });

  if (r.error) {
    // The RPC raises 42501 on invalid_n8n_secret — translate to 401
    const code = (r.error as { code?: string }).code;
    if (code === "42501" || /invalid_n8n_secret/i.test(r.error.message || "")) {
      return bad(401, "invalid secret");
    }
    return bad(500, r.error.message || "rpc failed");
  }

  return NextResponse.json({
    ok: true,
    interaction_id: r.data,
  });
}

// Reject other methods
export async function GET() {
  return bad(405, "POST only");
}
