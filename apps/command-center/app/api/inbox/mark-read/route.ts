/**
 * POST /api/inbox/mark-read — Move a message file from
 * tmp/agent_inbox/inbox/ to tmp/agent_inbox/read/. Operator-only.
 */

import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { markRead } from "@/lib/agent-inbox-fs";
import { markReadDb } from "@/lib/agent-inbox-db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const e = email.trim().toLowerCase();
  const operator = (process.env.OPERATOR_EMAIL || "").trim().toLowerCase();
  if (operator && e === operator) return true;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(e);
}

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  if (!isAdminEmail(user.email)) {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  let payload: { filename?: string; id?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Resolve tenant for Supabase mark-read.
  const service = getServiceSupabase();
  const profileRes = await service
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id;

  // The UI passes the message's UUID (Supabase id) when the message came
  // from Supabase, or a filename when it came from the legacy filesystem
  // path. Try both — whichever has a hit wins.
  const id = String(payload.id || payload.filename || "");
  const looksLikeUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);

  let dbResult: { ok: boolean; error?: string } = { ok: false, error: "no_tenant_or_id" };
  if (tenantId && looksLikeUuid) {
    dbResult = await markReadDb(tenantId, id);
  }

  // Filesystem mirror — only attempt if the id looks like a filename.
  let fsResult: { ok: boolean; error?: string } = { ok: false, error: "skipped" };
  if (!looksLikeUuid && id.endsWith(".json")) {
    fsResult = await markRead(id);
  }

  if (!dbResult.ok && !fsResult.ok) {
    return NextResponse.json(
      { ok: false, error: dbResult.error || fsResult.error || "mark_failed" },
      { status: 400 }
    );
  }
  return NextResponse.json({ ok: true });
}
