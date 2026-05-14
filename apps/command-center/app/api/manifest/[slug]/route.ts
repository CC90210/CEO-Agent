import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { getManifest, manifestExists } from "@/lib/manifest/loader";
import { applyMutations, type MutationArgs, ManifestMutationError } from "@/lib/manifest/mutators";
import { diffManifests } from "@/lib/manifest/diff";
import {
  getManifestRow,
  saveManifest,
  ManifestPersistenceError,
} from "@/lib/manifest/persistence";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/manifest/<slug>
 *
 * Returns the tenant manifest. Auth-gated by middleware (anonymous callers
 * get 401 with JSON envelope). The onboarding wizard, the marketplace, the
 * AI chat editor, and admin tooling all read through this single endpoint.
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
  if (!(await manifestExists(normalised))) {
    return NextResponse.json({ ok: false, error: "unknown tenant" }, { status: 404 });
  }
  const manifest = await getManifest(normalised);
  const row = await getManifestRow(normalised).catch(() => null);
  return NextResponse.json({
    ok: true,
    manifest,
    version: row?.version ?? 0,
    manifest_id: row?.id ?? null,
  });
}

/**
 * POST /api/manifest/<slug>
 *
 * Body: {
 *   mutations: MutationArgs[],     // see lib/manifest/mutators.ts
 *   actor?: "user" | "ai" | "system",  // default "user"
 *   message?: string,              // free-text audit annotation
 *   if_version?: number,           // optimistic concurrency; reject if mismatch
 *   tenant_id?: string | null,     // honoured only on first save for the slug
 * }
 *
 * Returns: { ok, manifest, diff, version, manifest_id, audit_id }
 *
 * Auth flow:
 *   1. require session
 *   2. resolve user's tenant_id + team_role
 *   3. only `owner` and `admin` can mutate manifests
 *   4. (single-tenant for now — Phase 3 marketplace adds per-tenant slug guards)
 */
export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  const { slug } = await ctx.params;
  const normalised = slug.toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{1,62}$/.test(normalised)) {
    return NextResponse.json({ ok: false, error: "invalid slug" }, { status: 400 });
  }
  if (!(await manifestExists(normalised))) {
    return NextResponse.json({ ok: false, error: "unknown tenant" }, { status: 404 });
  }

  let body: {
    mutations?: unknown;
    actor?: unknown;
    message?: unknown;
    if_version?: unknown;
    tenant_id?: unknown;
  };
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const mutations = Array.isArray(body.mutations) ? (body.mutations as MutationArgs[]) : null;
  if (!mutations || mutations.length === 0) {
    return NextResponse.json({ ok: false, error: "mutations required" }, { status: 400 });
  }

  // Authorisation — only owners + admins of the tenant can mutate.
  const service = getServiceSupabase();
  const profileQuery = await service
    .from("user_profiles")
    .select("tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileQuery.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  if (!profile?.tenant_id) {
    return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  }
  if (!profile.is_owner && profile.team_role !== "admin" && profile.team_role !== "owner") {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  // Load current manifest (DB → seed fallback) and apply mutations in order.
  const before = await getManifest(normalised);
  let after;
  try {
    after = applyMutations(before, mutations);
  } catch (err) {
    if (err instanceof ManifestMutationError) {
      return NextResponse.json(
        { ok: false, error: "mutation_rejected", field: err.field, reason: err.reason },
        { status: 422 }
      );
    }
    throw err;
  }

  const diff = diffManifests(before, after);
  if (diff.length === 0) {
    return NextResponse.json({ ok: true, no_op: true, manifest: after, diff: [], version: 0 });
  }

  const actorType =
    body.actor === "ai" || body.actor === "system" ? body.actor : "user";
  const message = typeof body.message === "string" ? body.message : undefined;
  const ifVersion = typeof body.if_version === "number" ? body.if_version : undefined;

  try {
    const result = await saveManifest({
      slug: normalised,
      next: after,
      diff,
      actor: { type: actorType, id: user.id },
      message,
      if_version: ifVersion,
      tenant_id: profile.tenant_id,
    });
    return NextResponse.json({
      ok: true,
      manifest: result.row.manifest,
      diff,
      version: result.row.version,
      manifest_id: result.row.id,
      audit_id: result.audit_id,
    });
  } catch (err) {
    if (err instanceof ManifestPersistenceError) {
      const status = err.code === "version_conflict" ? 409 : err.code === "validation" ? 422 : 500;
      return NextResponse.json({ ok: false, error: err.code, message: err.message }, { status });
    }
    throw err;
  }
}
