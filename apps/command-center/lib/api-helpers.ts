/**
 * Shared helpers for /api routes. Extracted to kill the duplication that was
 * starting to drift across 4 route files (bad()/profileForUser()).
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getServiceSupabase, getSessionUser } from "./supabase-server";

export function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

/**
 * Promise-with-fallback. Wrap any reader so a single thrown query can't
 * 500 a server-rendered page. Used in /today, /pipeline, /analytics,
 * /reasoning, /integrations, /settings — every dynamic page that does a
 * Promise.all over Supabase readers. Pattern was open-coded inline in 6
 * files until it landed here.
 *
 * Usage: const value = await safe(maybeThrowingPromise(), defaultValue);
 */
export async function safe<T>(p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p;
  } catch {
    return fallback;
  }
}

/**
 * Verify a "Bearer <secret>" header against an env-provided shared secret.
 * Used by /api/auth/provision-cli, /api/auth/pair, and any other CLI-only
 * route where the caller is the wizard / installer, not a logged-in user.
 *
 * Returns true on match. Routes should `return bad(401, "...")` on false.
 * Constant-time compare so timing attacks don't leak the secret.
 */
export function checkBearerSecret(req: NextRequest, envVar: string): boolean {
  const expected = (process.env[envVar] || "").trim();
  if (!expected) return false;
  const auth = req.headers.get("authorization") || "";
  if (!auth.toLowerCase().startsWith("bearer ")) return false;
  const provided = auth.slice(7).trim();
  if (provided.length !== expected.length) return false;
  let mismatch = 0;
  for (let i = 0; i < expected.length; i++) {
    mismatch |= provided.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return mismatch === 0;
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
