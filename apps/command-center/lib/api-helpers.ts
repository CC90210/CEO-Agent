/**
 * Shared helpers for /api routes. Extracted to kill the duplication that was
 * starting to drift across 4 route files (bad()/profileForUser()).
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { createHash } from "crypto";
import { getServiceSupabase, getSessionUser } from "./supabase-server";

export function bad(status: number, error: string) {
  return NextResponse.json({ ok: false, error }, { status });
}

/**
 * SHA-256 of a UTF-8 string, hex-encoded. Used to hash bridge tokens
 * + HMAC secrets before storage / lookup. Five routes (auth/pair,
 * auth/pair-code/redeem, bridge/ping, inbound/n8n, outbound/log) were
 * each defining this same 3-line helper inline; consolidated
 * 2026-05-09 so future security tweaks (switching to BLAKE3,
 * normalizing input, etc.) happen in one place.
 *
 * Usage: const tokenHash = sha256(tokenPlain);
 */
export function sha256(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

/**
 * Promise-with-fallback. Wrap any reader so a single thrown query can't
 * 500 a server-rendered page. Used in /today, /pipeline, /analytics,
 * /reasoning, /integrations, /settings — every dynamic page that does a
 * Promise.all over Supabase readers.
 *
 * The `label` is required: it surfaces in Vercel function logs as
 * `[safe:<label>] <error>` so failed readers are searchable instead of
 * silently rendering zeros. Use dotted scope-y names like "today.counts",
 * "pipeline.breakdown", "operations.events".
 *
 * Usage: const value = await safe("today.counts", readerPromise(), defaultValue);
 */
export async function safe<T>(label: string, p: Promise<T>, fallback: T): Promise<T> {
  try {
    return await p;
  } catch (err) {
    console.error(`[safe:${label}]`, err);
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

/**
 * Resolve the authed user's tenant_id directly. Thin wrapper over
 * profileForUser when the caller only needs the tenant.
 *
 * Consolidates the ~9 inline `resolveTenantId()` implementations that
 * spread across /api/forms, /api/sequences, /api/cron-jobs,
 * /api/applications/* during the SunBiz CRM build. Each had its own
 * identical body — getSessionUser -> db.user_profiles.select(tenant_id)
 * -> return value-or-null. New routes should import this helper.
 */
export async function tenantIdForUser(): Promise<string | null> {
  const p = await profileForUser();
  return p?.tenant_id ?? null;
}

/**
 * Resolve both tenant + user IDs in one call. Some routes need the
 * user_id too (cron-jobs records created_by, forms records created_by).
 */
export async function tenantAndUserIds(): Promise<{
  tenant_id: string | null;
  user_id: string | null;
}> {
  const user = await getSessionUser();
  if (!user) return { tenant_id: null, user_id: null };
  const db = getServiceSupabase();
  const r = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return {
    tenant_id: (r.data as { tenant_id: string | null } | null)?.tenant_id ?? null,
    user_id: user.id,
  };
}

/**
 * Detect "the table doesn't exist in the schema cache" — usually means
 * the operator has the dashboard deployed but hasn't applied the latest
 * SQL migration yet. PostgREST's error string is the canonical signal
 * (PGRST205), with the Postgres-side `42P01 undefined_table` as a
 * secondary check. The literal "Could not find the table" string also
 * appears in some response shapes.
 *
 * Five routes (/api/cron-jobs, /api/forms, /forms page, CronJobsManager,
 * lib/queries.ts) duplicated this regex+code-check before consolidation.
 * Anyone adding a new feature that depends on a fresh migration should
 * call this helper and return the standard structured 503 below.
 *
 * Usage:
 *   if (error) {
 *     if (isMissingTableError(error, "public.tenant_cron_jobs")) {
 *       return NextResponse.json(missingTablePayload({
 *         migration: "database/041_tenant_cron_jobs.sql",
 *         feature: "Automations",
 *       }), { status: 503 });
 *     }
 *     return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
 *   }
 */
export function isMissingTableError(
  err: { message?: string; code?: string } | null | undefined,
  tableHint?: string,
): boolean {
  if (!err) return false;
  // Error codes first — cheap and unambiguous.
  //   PGRST205: PostgREST when the API can't find the table in its
  //             schema cache (most common when the dashboard runs
  //             against Supabase but the SQL migration hasn't applied
  //             yet — cache reloads ~30s after migration).
  //   42P01:    Postgres-direct undefined_table — happens when something
  //             bypasses PostgREST and the relation isn't there.
  if (err.code === "PGRST205" || err.code === "42P01") return true;
  // Fall through to message-pattern matching for cases where the error
  // object lost its code (some PostgREST proxy paths drop it). Two
  // formats to cover both API and direct-SQL responses:
  const msg = err.message || "";
  const lower = msg.toLowerCase();
  if (tableHint && msg.includes(tableHint)) return true;
  if (lower.includes("could not find the table")) return true;     // PostgREST
  if (lower.includes("relation") && lower.includes("does not exist")) return true; // Postgres
  return false;
}

/**
 * Standard structured 503 payload for the "migration not applied" case.
 * Routes hand this to NextResponse.json with status: 503; UI components
 * branch on `error === "migration_not_applied"` to render the
 * actionable apply_migration.py banner instead of a generic red error.
 *
 * Keeping the shape stable across routes means UI components like
 * CronJobsManager can be re-used / generalized for future migration-
 * gated features without per-feature copy.
 */
export function missingTablePayload(opts: {
  /** Path under database/ — e.g. "database/041_tenant_cron_jobs.sql". */
  migration: string;
  /** Operator-facing feature name — e.g. "Automations", "Forms". */
  feature: string;
}): {
  ok: false;
  error: "migration_not_applied";
  migration: string;
  how_to_apply: string;
  hint: string;
} {
  return {
    ok: false,
    error: "migration_not_applied",
    migration: opts.migration,
    how_to_apply: `python scripts/apply_migration.py ${opts.migration}`,
    hint: `The ${opts.feature} feature needs ${opts.migration.split("/").pop()} applied to your Supabase project. Run the command above on the operator machine. After it completes, Supabase's PostgREST cache picks up the new table within ~30 seconds — refresh the page after that.`,
  };
}
