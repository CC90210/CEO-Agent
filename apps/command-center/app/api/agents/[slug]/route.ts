/**
 * GET    /api/agents/<slug> — fetch a single agent (seed or DB-resident).
 * PATCH  /api/agents/<slug> — update a custom agent (admin/owner only).
 * DELETE /api/agents/<slug> — delete a custom agent (admin/owner only).
 *
 * Platform-managed seeds (is_oasis_managed=true) are read-only through this
 * endpoint — PATCH/DELETE return 403. Edits to those happen in code via
 * lib/agents/library.ts under code review.
 */

import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { getAgentBySlug } from "@/lib/agents/loader";
import {
  AgentPersistenceError,
  deleteCustomAgent,
  updateCustomAgent,
  type UpdateAgentInput,
} from "@/lib/agents/persistence";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function resolveProfile(authUserId: string) {
  const service = getServiceSupabase();
  const res = await service
    .from("user_profiles")
    .select("tenant_id, team_role, is_owner")
    .eq("auth_user_id", authUserId)
    .maybeSingle();
  return res.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
}

function requireAdmin(profile: { team_role: string; is_owner: boolean } | null): boolean {
  return !!profile && (profile.is_owner || profile.team_role === "admin" || profile.team_role === "owner");
}

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ slug: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { slug } = await ctx.params;
  const profile = await resolveProfile(user.id);
  const agent = await getAgentBySlug(slug, profile?.tenant_id);
  if (!agent) return NextResponse.json({ ok: false, error: "not_found" }, { status: 404 });
  return NextResponse.json({ ok: true, agent });
}

export async function PATCH(
  req: NextRequest,
  ctx: { params: Promise<{ slug: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const profile = await resolveProfile(user.id);
  if (!profile?.tenant_id) return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  if (!requireAdmin(profile)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });

  const { slug } = await ctx.params;
  let body: Partial<UpdateAgentInput>;
  try {
    body = (await req.json()) as Partial<UpdateAgentInput>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  try {
    const updated = await updateCustomAgent({
      ...body,
      slug,
      tenant_id: profile.tenant_id,
    });
    return NextResponse.json({ ok: true, agent: updated });
  } catch (err) {
    if (err instanceof AgentPersistenceError) {
      const status =
        err.code === "not_found" ? 404 :
        err.code === "forbidden" ? 403 :
        err.code === "validation" ? 422 :
        500;
      return NextResponse.json({ ok: false, error: err.code, message: err.message }, { status });
    }
    throw err;
  }
}

export async function DELETE(
  _req: NextRequest,
  ctx: { params: Promise<{ slug: string }> }
) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const profile = await resolveProfile(user.id);
  if (!profile?.tenant_id) return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  if (!requireAdmin(profile)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });

  const { slug } = await ctx.params;
  try {
    await deleteCustomAgent(slug, profile.tenant_id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    if (err instanceof AgentPersistenceError) {
      const status =
        err.code === "not_found" ? 404 :
        err.code === "forbidden" ? 403 :
        500;
      return NextResponse.json({ ok: false, error: err.code, message: err.message }, { status });
    }
    throw err;
  }
}
