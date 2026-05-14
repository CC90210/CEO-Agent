import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser } from "@/lib/supabase-server";
import { SEED_MANIFESTS } from "@/lib/manifest/seeds";
import { getManifestRow, listManifestAudit } from "@/lib/manifest/persistence";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/manifest/<slug>/audit
 *
 * Returns the audit history for a manifest, newest first. Required for the
 * editor's "What changed?" sidebar and the rollback flow. Auth-gated; the
 * SQL RLS policy then narrows to the caller's tenant.
 */
export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ slug: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  const { slug } = await ctx.params;
  const normalised = slug.toLowerCase();
  if (!SEED_MANIFESTS[normalised]) {
    return NextResponse.json({ ok: false, error: "unknown tenant" }, { status: 404 });
  }

  const row = await getManifestRow(normalised);
  if (!row) {
    return NextResponse.json({ ok: true, entries: [], manifest_id: null });
  }
  const entries = await listManifestAudit(row.id, 50);
  return NextResponse.json({ ok: true, entries, manifest_id: row.id });
}
