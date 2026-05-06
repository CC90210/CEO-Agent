/**
 * GET    /api/devices             — list paired machines for the authed tenant
 * DELETE /api/devices?id=<uuid>   — revoke a pairing (sets revoked_at, the
 *                                   bridge daemon will see 403 on next ping
 *                                   and self-stop)
 */

import { NextResponse, type NextRequest } from "next/server";
import { bad } from "@/lib/api-helpers";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function tenantOf(): Promise<string | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const { data } = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return (data?.tenant_id as string | null) || null;
}

export async function GET() {
  const tenantId = await tenantOf();
  if (!tenantId) return bad(401, "unauthorized");
  const db = getServiceSupabase();
  const { data, error } = await db
    .from("bridge_pairings")
    .select("id, label, machine_fingerprint, last_seen_at, last_seen_ip, created_at, revoked_at")
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false });
  if (error) return bad(500, error.message);
  return NextResponse.json({ ok: true, devices: data || [] });
}

export async function DELETE(req: NextRequest) {
  const tenantId = await tenantOf();
  if (!tenantId) return bad(401, "unauthorized");
  const id = new URL(req.url).searchParams.get("id");
  if (!id) return bad(400, "id required");
  const db = getServiceSupabase();
  // Tenant-scope the update — operator can't revoke another tenant's pairing
  const { error } = await db
    .from("bridge_pairings")
    .update({ revoked_at: new Date().toISOString() })
    .eq("id", id)
    .eq("tenant_id", tenantId);
  if (error) return bad(500, error.message);
  return NextResponse.json({ ok: true });
}
