/**
 * Records API — manifest-defined entity CRUD.
 *
 * GET    /api/manifest/<slug>/records/<entity>?limit=&offset=&sort=
 * POST   /api/manifest/<slug>/records/<entity>          body: { data }
 * PATCH  /api/manifest/<slug>/records/<entity>?id=<id>  body: { patch }
 * DELETE /api/manifest/<slug>/records/<entity>?id=<id>
 *
 * Auth: requires session + tenant_id. The entity name must exist in the
 * tenant manifest's data_model — otherwise we 404 (don't leak whether
 * other tenants happen to have an entity with that name).
 *
 * Writes are gated to admin/owner role for now; reads are open to any
 * member of the tenant. When marketplace billing ships we'll wire role-
 * to-entity grants per-tenant via the manifest.
 */

import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import {
  RecordsError,
  createRecord,
  deleteRecord,
  listRecords,
  updateRecord,
} from "@/lib/manifest/data";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{1,62}$/;
const ENTITY_RE = /^[a-z][a-z0-9_]{0,62}$/;

async function resolveContext(
  user: { id: string },
  slug: string,
  entity: string
): Promise<
  | { ok: true; tenant_id: string; is_admin: boolean }
  | { ok: false; status: number; error: string }
> {
  if (!SLUG_RE.test(slug)) return { ok: false, status: 400, error: "invalid_slug" };
  if (!ENTITY_RE.test(entity)) return { ok: false, status: 400, error: "invalid_entity" };
  if (!(await manifestExists(slug))) return { ok: false, status: 404, error: "unknown_tenant" };

  const manifest = await getManifest(slug);
  const known = (manifest.data_model || []).some((e) => e.name === entity);
  if (!known) return { ok: false, status: 404, error: "unknown_entity" };

  const service = getServiceSupabase();
  const profileQuery = await service
    .from("user_profiles")
    .select("tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileQuery.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  if (!profile?.tenant_id) return { ok: false, status: 403, error: "no_tenant" };

  return {
    ok: true,
    tenant_id: profile.tenant_id,
    is_admin: !!profile.is_owner || profile.team_role === "admin" || profile.team_role === "owner",
  };
}

function handleRecordsError(err: unknown): NextResponse {
  if (err instanceof RecordsError) {
    const status =
      err.code === "not_found" ? 404 :
      err.code === "forbidden" ? 403 :
      err.code === "validation" ? 422 :
      500;
    return NextResponse.json({ ok: false, error: err.code, message: err.message }, { status });
  }
  throw err;
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string; entity: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { slug, entity } = await ctx.params;
  const r = await resolveContext(user, slug.toLowerCase(), entity.toLowerCase());
  if (!r.ok) return NextResponse.json({ ok: false, error: r.error }, { status: r.status });

  const sp = req.nextUrl.searchParams;
  const limit = Number(sp.get("limit") || "100");
  const offset = Number(sp.get("offset") || "0");
  const sort = sp.get("sort") || undefined;

  try {
    const result = await listRecords({
      tenant_id: r.tenant_id,
      entity: entity.toLowerCase(),
      limit: Number.isFinite(limit) ? limit : 100,
      offset: Number.isFinite(offset) ? offset : 0,
      sort,
    });
    return NextResponse.json({ ok: true, ...result });
  } catch (err) {
    return handleRecordsError(err);
  }
}

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string; entity: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { slug, entity } = await ctx.params;
  const r = await resolveContext(user, slug.toLowerCase(), entity.toLowerCase());
  if (!r.ok) return NextResponse.json({ ok: false, error: r.error }, { status: r.status });
  if (!r.is_admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });

  let body: { data?: Record<string, unknown> };
  try {
    body = (await req.json()) as { data?: Record<string, unknown> };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  if (!body.data || typeof body.data !== "object") {
    return NextResponse.json({ ok: false, error: "data_required" }, { status: 400 });
  }

  try {
    const row = await createRecord({
      tenant_id: r.tenant_id,
      entity: entity.toLowerCase(),
      data: body.data,
    });
    return NextResponse.json({ ok: true, record: row });
  } catch (err) {
    return handleRecordsError(err);
  }
}

export async function PATCH(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string; entity: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { slug, entity } = await ctx.params;
  const r = await resolveContext(user, slug.toLowerCase(), entity.toLowerCase());
  if (!r.ok) return NextResponse.json({ ok: false, error: r.error }, { status: r.status });
  if (!r.is_admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });

  const id = req.nextUrl.searchParams.get("id");
  if (!id) return NextResponse.json({ ok: false, error: "id_required" }, { status: 400 });

  let body: { patch?: Record<string, unknown> };
  try {
    body = (await req.json()) as { patch?: Record<string, unknown> };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  if (!body.patch || typeof body.patch !== "object") {
    return NextResponse.json({ ok: false, error: "patch_required" }, { status: 400 });
  }

  try {
    const row = await updateRecord({
      tenant_id: r.tenant_id,
      entity: entity.toLowerCase(),
      id,
      patch: body.patch,
    });
    return NextResponse.json({ ok: true, record: row });
  } catch (err) {
    return handleRecordsError(err);
  }
}

export async function DELETE(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string; entity: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { slug, entity } = await ctx.params;
  const r = await resolveContext(user, slug.toLowerCase(), entity.toLowerCase());
  if (!r.ok) return NextResponse.json({ ok: false, error: r.error }, { status: r.status });
  if (!r.is_admin) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });

  const id = req.nextUrl.searchParams.get("id");
  if (!id) return NextResponse.json({ ok: false, error: "id_required" }, { status: 400 });

  try {
    await deleteRecord({
      tenant_id: r.tenant_id,
      entity: entity.toLowerCase(),
      id,
    });
    return NextResponse.json({ ok: true });
  } catch (err) {
    return handleRecordsError(err);
  }
}
