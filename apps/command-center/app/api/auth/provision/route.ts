/**
 * POST /api/auth/provision
 *
 * Idempotently creates a tenant + user_profile pair for the current
 * Supabase Auth session. The browser may not choose auth_user_id; the route
 * binds provisioning to the signed-in session so a malicious client cannot
 * link or create profiles for another user.
 *
 * Body: { full_name, brand }
 * Returns: { ok, tenant_id, profile_id, slug, already_provisioned? }
 */

import { NextResponse, type NextRequest } from "next/server";
import { provisionAuthenticatedUser } from "@/lib/auth-provisioning";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let body: { full_name?: string; brand?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON" }, { status: 400 });
  }

  const email = user.email;
  const fullName =
    body.full_name?.trim() ||
    (user.user_metadata?.full_name as string | undefined)?.trim() ||
    (user.user_metadata?.name as string | undefined)?.trim() ||
    email?.split("@")[0] ||
    "";

  if (!email || !fullName) {
    return NextResponse.json(
      { ok: false, error: "session_email_and_full_name_required" },
      { status: 400 },
    );
  }

  try {
    const out = await provisionAuthenticatedUser({
      db: getServiceSupabase(),
      authUserId: user.id,
      email,
      fullName,
      brand: body.brand,
    });
    return NextResponse.json(out);
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "provisioning failed" },
      { status: 500 },
    );
  }
}
