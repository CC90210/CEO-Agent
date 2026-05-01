/**
 * Shared helpers for /api routes. Extracted to kill the duplication that was
 * starting to drift across 4 route files (bad()/profileForUser()).
 */
import { NextResponse } from "next/server";
import { getServiceSupabase, getSessionUser } from "./supabase-server";

export function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

/**
 * Resolve the authed user's profile row. Returns null when no session OR
 * no profile linked to that auth user. Routes should `return bad(401, ...)`
 * on null.
 */
export async function profileForUser(): Promise<{
  id: string;
  tenant_id: string | null;
} | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const r = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return r.data || null;
}
