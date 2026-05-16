/**
 * Shared session → tenant resolution helpers for API routes.
 *
 * Every operator-facing route needs the same flow: read the session
 * cookie, look up the user_profiles row, return the tenant_id. Before
 * this module that 6-line block was copy-pasted into ~9 routes — small
 * enough each time that it kept landing inline, big enough collectively
 * that drift (different fallback error codes, different null-handling)
 * had started to show up.
 *
 * Two entry points:
 *
 *   resolveTenantId() — Promise<string | null>. Returns null on no
 *     session, no profile, or no tenant_id. Routes that want a
 *     specific HTTP shape for the null case map it themselves.
 *
 *   resolveSessionContext() — fuller shape: { user, profileId, tenantId }
 *     or a typed null reason. Use when the route needs more than
 *     tenantId (e.g. created_by audit fields).
 */

import { getSessionUser, getServiceSupabase } from "./supabase-server";

/**
 * Resolve the active tenant_id from the request's session cookie.
 * Returns null if there's no session, no matching user_profile, or
 * the profile carries no tenant_id (operator hasn't completed
 * onboarding).
 */
export async function resolveTenantId(): Promise<string | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const r = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return (r.data as { tenant_id: string | null } | null)?.tenant_id ?? null;
}

/**
 * Resolve full session context for routes that need more than the
 * tenant_id — typically the user_profiles.id for `created_by` audit
 * trails or the auth user id for downstream RLS lookups.
 *
 * Returns a discriminated union so callers don't have to null-check
 * each field independently.
 */
export type SessionContext =
  | { ok: true; userId: string; profileId: string | null; tenantId: string; email: string | null }
  | { ok: false; reason: "no_session" | "no_profile" | "no_tenant" };

export async function resolveSessionContext(): Promise<SessionContext> {
  const user = await getSessionUser();
  if (!user) return { ok: false, reason: "no_session" };
  const db = getServiceSupabase();
  const r = await db
    .from("user_profiles")
    .select("id, tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = r.data as { id: string | null; tenant_id: string | null } | null;
  if (!profile) return { ok: false, reason: "no_profile" };
  if (!profile.tenant_id) return { ok: false, reason: "no_tenant" };
  return {
    ok: true,
    userId: user.id,
    profileId: profile.id,
    tenantId: profile.tenant_id,
    email: user.email ?? null,
  };
}
