/**
 * Supabase server-side client factories.
 *
 * Two clients, two roles:
 *   - getServiceSupabase() — service role, bypasses RLS, used for internal
 *     queries the dashboard needs (cross-tenant admin views, etc.)
 *   - getAuthedSupabase()  — anon key + the user's session cookie. RLS
 *     enforces tenant isolation. This is the safe default for any query
 *     scoped to "the logged-in user's tenant."
 *
 * The session is read from Next.js cookies via @supabase/ssr.
 */

import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let _serviceCached: SupabaseClient | null = null;

export function getServiceSupabase(): SupabaseClient {
  if (_serviceCached) return _serviceCached;
  const url = process.env.BRAVO_SUPABASE_URL;
  const key = process.env.BRAVO_SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Service Supabase misconfigured: BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY required."
    );
  }
  _serviceCached = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return _serviceCached;
}

/** Authed Supabase — RLS enforced via the user's session. */
export async function getAuthedSupabase() {
  const url = process.env.BRAVO_SUPABASE_URL;
  const anon =
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.BRAVO_SUPABASE_ANON_KEY;
  if (!url || !anon) {
    throw new Error(
      "Authed Supabase misconfigured: BRAVO_SUPABASE_URL + anon key required."
    );
  }
  const cookieStore = await cookies();
  return createServerClient(url, anon, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(toSet) {
        try {
          toSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          );
        } catch {
          // Called from a Server Component — set is a no-op there
        }
      },
    },
  });
}

/** Resolve the currently signed-in user. Returns null if unauthenticated. */
export async function getSessionUser() {
  const supa = await getAuthedSupabase();
  const { data, error } = await supa.auth.getUser();
  if (error || !data.user) return null;
  return data.user;
}

/**
 * True iff the caller is the OASIS operator (CC). Used to gate the legacy
 * `/onboarding` flow — only the operator should see the C-suite picker;
 * everyone else (client tenants) is routed through `/onboarding/wizard`.
 *
 * Resolution order:
 *   1. If the user's email is in ADMIN_EMAILS, they're the operator.
 *      Same env var as the rest of the dashboard's admin checks
 *      (app/agent/page.tsx, etc.) — single source of truth.
 *
 * Returns false on any error or missing input — false-negative is safe
 * (just routes to wizard) while a false-positive would leak operator chrome.
 */
export function isOasisOperator(emailOrUser: string | { email?: string | null } | null | undefined): boolean {
  const email = (typeof emailOrUser === "string"
    ? emailOrUser
    : emailOrUser?.email || ""
  ).trim().toLowerCase();
  if (!email) return false;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(email);
}
