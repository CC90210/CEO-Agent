import { NextResponse, type NextRequest } from "next/server";
import { getManifest } from "@/lib/manifest/loader";
import { SEED_MANIFESTS } from "@/lib/manifest/seeds";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/manifest/<slug>
 *
 * Phase 1 read endpoint — returns the tenant manifest for a slug. The
 * onboarding wizard, the marketplace, and the (Phase 2) AI editor all read
 * through this single endpoint so they share validation + caching semantics.
 *
 * POST/PATCH land in Phase 2 alongside the AI chat editor. They will go
 * through SECURITY DEFINER RPCs (record_manifest_mutation_v1) with HMAC
 * signing, audit logging, and rollback support — keeping the live shell
 * one mutation away from a known-good prior version.
 */
export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ slug: string }> }
) {
  const { slug } = await ctx.params;
  const normalised = slug.toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{1,62}$/.test(normalised)) {
    return NextResponse.json({ ok: false, error: "invalid slug" }, { status: 400 });
  }
  if (!SEED_MANIFESTS[normalised]) {
    return NextResponse.json({ ok: false, error: "unknown tenant" }, { status: 404 });
  }
  const manifest = await getManifest(normalised);
  return NextResponse.json({ ok: true, manifest });
}
