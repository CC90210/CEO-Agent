/**
 * Manifest-route guards.
 *
 * The protected-slug list + cross-tenant check appear in THREE routes
 * (/api/manifest/[slug] POST, /api/manifest/chat POST, /api/onboarding/wizard)
 * and were drifting before this consolidation. Single source of truth lives
 * here so a new guard added in one place propagates to every consumer.
 *
 * Why a `Result` object instead of throwing: every consumer wants to return
 * a JSON response with the same shape. A thrown error would force each
 * caller to translate exception → NextResponse, and the translations were
 * already inconsistent (some returned `error: "protected_slug"`, some
 * returned `error: "forbidden"`). Consolidating the response payload here
 * forces callers to use the canonical shape.
 */

import { getManifestRow } from "./persistence";

export const PROTECTED_SLUGS: ReadonlySet<string> = new Set([
  "default",
  "oasis",
  "sun",
  "suga",
]);

export type GuardOk = { ok: true };
export type GuardFail = {
  ok: false;
  status: number;
  error: string;
  reason?: string;
};
export type GuardResult = GuardOk | GuardFail;

/**
 * Reject mutations against the platform-managed seed slugs.
 * Tenants modify their OWN manifest; the seeds are the safety-net fallback
 * everyone reads when their own row is missing or unreachable.
 */
export function protectedSlugGuard(slug: string): GuardResult {
  if (PROTECTED_SLUGS.has(slug)) {
    return {
      ok: false,
      status: 403,
      error: "protected_slug",
      reason:
        "Platform seed manifests cannot be modified. Create your own tenant via /onboarding/wizard.",
    };
  }
  return { ok: true };
}

/**
 * Reject writes to a manifest already bound to a different tenant.
 *
 * Three valid outcomes:
 *   - row doesn't exist yet     → ok (first-write claims the slug)
 *   - row exists, tenant_id null → ok (legacy seed claim path)
 *   - row exists, same tenant    → ok
 *   - row exists, other tenant   → 403 cross_tenant_forbidden
 *
 * Defensive on DB errors: if the row fetch fails we let it through. The
 * subsequent save will hit the same DB and surface the error to the caller;
 * blocking here would create a false-positive "cross_tenant" 403 during
 * Supabase transients.
 */
export async function crossTenantGuard(
  slug: string,
  callerTenantId: string
): Promise<GuardResult> {
  const existing = await getManifestRow(slug).catch(() => null);
  if (!existing) return { ok: true };
  if (!existing.tenant_id) return { ok: true };
  if (existing.tenant_id === callerTenantId) return { ok: true };
  return {
    ok: false,
    status: 403,
    error: "cross_tenant_forbidden",
    reason: "This manifest belongs to another tenant.",
  };
}

/**
 * Sugar that runs the two guards in canonical order. Returns the first
 * failure or `ok`. Most callers want this, not the individual functions.
 */
export async function manifestWriteGuards(
  slug: string,
  callerTenantId: string
): Promise<GuardResult> {
  const proto = protectedSlugGuard(slug);
  if (!proto.ok) return proto;
  return crossTenantGuard(slug, callerTenantId);
}
