/**
 * Single source of truth for "which tenant_id should scope records for
 * this manifest slug + this caller?"
 *
 * The rule that all three call sites (the tenant-root page renderer,
 * the catch-all page renderer, and the records API) MUST agree on:
 *
 *   - If the manifest has a DB row whose tenant_id matches the
 *     caller's tenant_id → grant data access. This is the operator's
 *     legitimately-claimed slug (created via the onboarding wizard).
 *
 *   - If no DB row exists (code-seed manifest like the platform's
 *     "default" / "oasis" / "sun" / "suga") AND the caller's home
 *     tenant_slug matches this URL slug → grant data access. Covers
 *     legacy pre-wizard tenants that map via tenants.custom_fields.
 *
 *   - Otherwise → null. Preview mode for page renderers; 403 for
 *     write APIs. Prevents:
 *       a) cross-shell data bleed (records of tenant X rendering
 *          inside the shell of slug Y);
 *       b) cross-tenant writes (POST /api/manifest/<slug-not-yours>/
 *          records/<entity> writing into the caller's records under
 *          someone else's manifest namespace).
 *
 * One DB hop on the happy path (getManifestRow); two on the fallback
 * path (also getTenant). Acceptable cost for the correctness guarantee.
 */

import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getTenant } from "@/lib/queries";
import { getManifestRow } from "./persistence";

/**
 * Resolve the tenant_id that should scope tenant_records reads/writes
 * for `slug`, called by `userTenantId`. Returns null when the caller
 * doesn't own the slug — primitives render preview mode, write APIs
 * should return 403.
 */
export async function resolveDataTenant(
  slug: string,
  userTenantId: string | null
): Promise<string | null> {
  if (!userTenantId) return null;
  const row = await getManifestRow(slug).catch(() => null);
  if (row?.tenant_id && row.tenant_id === userTenantId) return userTenantId;
  if (!row) {
    const tenant = await getTenant(userTenantId).catch(() => null);
    const userSlug = resolveClientProfileSlug(tenant || null);
    if (userSlug && userSlug.toLowerCase() === slug.toLowerCase()) {
      return userTenantId;
    }
  }
  return null;
}

/** True when the caller owns the slug (data access granted). */
export async function ownsSlug(
  slug: string,
  userTenantId: string | null
): Promise<boolean> {
  return (await resolveDataTenant(slug, userTenantId)) !== null;
}
