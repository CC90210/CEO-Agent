/**
 * POST   /api/tenant/logo  — upload a brand logo for the current tenant.
 * DELETE /api/tenant/logo  — clear the logo.
 *
 * Multipart upload (FormData with a `file` field, max 2 MB). We verify the
 * caller manages the tenant before touching storage, push the bytes to the
 * tenant-assets bucket (public read — public form pages need it), then
 * write the resolved URL onto tenants.logo_url. The settings UI optimistic-
 * renders the new logo using the URL we return.
 *
 * Tenant scoping: every object lands under <tenant_id>/<timestamp>_<name>
 * so a misconfigured bucket policy can't leak across tenants.
 */
import { NextRequest, NextResponse } from "next/server";
import { getServiceSupabase, getSessionUser } from "@/lib/supabase-server";
import { sanitizeStorageFilename } from "@/lib/storage-helpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BYTES = 2 * 1024 * 1024; // 2 MB cap — logos are small
const ALLOWED_MIME = new Set([
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
  "image/svg+xml",
  "image/gif",
]);

async function resolveOwnerTenant(): Promise<{
  tenantId: string;
  canManage: boolean;
} | { error: string; status: number }> {
  const user = await getSessionUser().catch(() => null);
  if (!user) return { error: "unauthorized", status: 401 };
  const db = getServiceSupabase();
  const profile = await db
    .from("user_profiles")
    .select("tenant_id, is_owner, team_role")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const row = profile.data as
    | { tenant_id: string | null; is_owner: boolean | null; team_role: string | null }
    | null;
  const tenantId = row?.tenant_id;
  if (!tenantId) return { error: "no_tenant", status: 403 };
  const canManage =
    !!row?.is_owner || row?.team_role === "owner" || row?.team_role === "admin";
  if (!canManage) return { error: "forbidden", status: 403 };
  return { tenantId, canManage: true };
}

export async function POST(req: NextRequest) {
  const ctx = await resolveOwnerTenant();
  if ("error" in ctx) {
    return NextResponse.json({ ok: false, error: ctx.error }, { status: ctx.status });
  }
  const { tenantId } = ctx;

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return NextResponse.json(
      { ok: false, error: "invalid_form_data" },
      { status: 400 },
    );
  }
  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json(
      { ok: false, error: "file_field_missing" },
      { status: 400 },
    );
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json(
      {
        ok: false,
        error: "file_too_large",
        hint: `Logos must be under ${MAX_BYTES / (1024 * 1024)} MB.`,
      },
      { status: 400 },
    );
  }
  if (!ALLOWED_MIME.has(file.type)) {
    return NextResponse.json(
      {
        ok: false,
        error: "unsupported_mime",
        hint: "Use PNG, JPG, WEBP, SVG, or GIF.",
      },
      { status: 400 },
    );
  }

  const db = getServiceSupabase();
  const clean = sanitizeStorageFilename(file.name);
  const storagePath = `${tenantId}/${Date.now()}_${clean}`;
  const bytes = Buffer.from(await file.arrayBuffer());

  const upload = await db.storage
    .from("tenant-assets")
    .upload(storagePath, bytes, {
      contentType: file.type,
      upsert: false,
    });
  if (upload.error) {
    return NextResponse.json(
      { ok: false, error: upload.error.message },
      { status: 500 },
    );
  }
  const publicUrl = db.storage.from("tenant-assets").getPublicUrl(storagePath)
    .data.publicUrl;

  const update = await db
    .from("tenants")
    .update({ logo_url: publicUrl })
    .eq("id", tenantId);
  if (update.error) {
    return NextResponse.json(
      { ok: false, error: update.error.message },
      { status: 500 },
    );
  }

  return NextResponse.json({ ok: true, logo_url: publicUrl });
}

export async function DELETE() {
  const ctx = await resolveOwnerTenant();
  if ("error" in ctx) {
    return NextResponse.json({ ok: false, error: ctx.error }, { status: ctx.status });
  }
  const db = getServiceSupabase();
  // Leave the storage objects in place — they're cheap and prior forms
  // may still reference the URL. Clearing tenants.logo_url is enough to
  // stop the auto-prefill on new surfaces.
  const update = await db
    .from("tenants")
    .update({ logo_url: null })
    .eq("id", ctx.tenantId);
  if (update.error) {
    return NextResponse.json(
      { ok: false, error: update.error.message },
      { status: 500 },
    );
  }
  return NextResponse.json({ ok: true });
}
