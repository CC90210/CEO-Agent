/**
 * GET /api/lead-documents/[id]
 *
 * Mints a short-lived signed URL for a lead_documents row so the operator
 * UI can render the file inline (or download it) without exposing the
 * bucket publicly. Tenant scope is verified BEFORE the signed URL is
 * generated — guessing a UUID never produces a working link.
 *
 * Response: { ok: true, url, filename, mime_type } or { ok: false, error }.
 */
import { NextResponse, type NextRequest } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SIGN_TTL_SECONDS = 60 * 10; // 10 minutes

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const user = await getSessionUser().catch(() => null);
  if (!user) {
    return NextResponse.json(
      { ok: false, error: "unauthorized" },
      { status: 401 },
    );
  }
  const { id } = await context.params;
  const db = getServiceSupabase();

  const profile = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profile.data as { tenant_id: string | null } | null)
    ?.tenant_id;
  if (!tenantId) {
    return NextResponse.json(
      { ok: false, error: "no_tenant" },
      { status: 403 },
    );
  }

  const docRow = await db
    .from("lead_documents")
    .select("id, tenant_id, filename, storage_path, mime_type")
    .eq("id", id)
    .eq("tenant_id", tenantId)
    .maybeSingle();
  const doc = docRow.data as
    | {
        id: string;
        tenant_id: string;
        filename: string;
        storage_path: string;
        mime_type: string | null;
      }
    | null;
  if (!doc) {
    return NextResponse.json(
      { ok: false, error: "not_found" },
      { status: 404 },
    );
  }

  // Confused-deputy guard. lead_documents.tenant_id matched the caller
  // — but `storage_path` is operator-writable through RLS (the
  // lead_documents_member_all policy lets authenticated tenant members
  // INSERT rows for their own tenant). A malicious employee could
  // craft a row pointing at another tenant's storage path and then
  // this service-role mint would sign it. Refuse to sign unless the
  // storage path is anchored under THIS tenant's folder.
  const expectedPrefix = `${doc.tenant_id}/`;
  if (!doc.storage_path.startsWith(expectedPrefix)) {
    return NextResponse.json(
      { ok: false, error: "storage_path_mismatch" },
      { status: 403 },
    );
  }

  const signed = await db.storage
    .from("lead-documents")
    .createSignedUrl(doc.storage_path, SIGN_TTL_SECONDS);
  if (signed.error || !signed.data?.signedUrl) {
    return NextResponse.json(
      { ok: false, error: signed.error?.message || "sign_failed" },
      { status: 500 },
    );
  }

  return NextResponse.json({
    ok: true,
    url: signed.data.signedUrl,
    filename: doc.filename,
    mime_type: doc.mime_type,
  });
}
