/**
 * GET  /api/agents — list marketplace agents (seeds + tenant publics + tenant customs).
 *      Query params:
 *        category=<AgentCategory>       optional filter
 *        include_customs=true|false     default true; set false to hide user-created
 *      Returns: { ok: true, agents: AgentLibraryEntry[] }
 *
 * POST /api/agents — create a new custom agent for the caller's tenant.
 *      Body: { slug, name, category, short_description, description?,
 *              base_prompt, required_tools?, suggested_model?, pricing?,
 *              is_public? }
 *      Auth: requires session + tenant_id. Custom agents start as
 *      private (is_public=false) unless explicitly opted public.
 */

import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { listAgents } from "@/lib/agents/loader";
import { CATEGORY_LABELS } from "@/lib/agents/library";
import {
  AgentPersistenceError,
  createCustomAgent,
  type CreateAgentInput,
} from "@/lib/agents/persistence";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const sp = req.nextUrl.searchParams;
  const categoryParam = sp.get("category");
  const includeCustoms = sp.get("include_customs") !== "false";

  let category: keyof typeof CATEGORY_LABELS | undefined;
  if (categoryParam) {
    if (!(categoryParam in CATEGORY_LABELS)) {
      return NextResponse.json({ ok: false, error: "unknown_category" }, { status: 400 });
    }
    category = categoryParam as keyof typeof CATEGORY_LABELS;
  }

  const service = getServiceSupabase();
  const profileRes = await service
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const tenantId = (profileRes.data as { tenant_id: string | null } | null)?.tenant_id || null;

  const agents = await listAgents({ category, tenant_id: tenantId, include_customs: includeCustoms });
  return NextResponse.json({ ok: true, agents, categories: CATEGORY_LABELS });
}

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  let body: Partial<CreateAgentInput> & { is_public?: boolean };
  try {
    body = (await req.json()) as Partial<CreateAgentInput> & { is_public?: boolean };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const service = getServiceSupabase();
  const profileRes = await service
    .from("user_profiles")
    .select("tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileRes.data as
    | { tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  if (!profile?.tenant_id) {
    return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  }
  if (!profile.is_owner && profile.team_role !== "admin" && profile.team_role !== "owner") {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  // Required fields
  const required: (keyof CreateAgentInput)[] = ["slug", "name", "category", "short_description", "base_prompt"];
  for (const k of required) {
    if (typeof body[k] !== "string" || !(body[k] as string).trim()) {
      return NextResponse.json({ ok: false, error: "validation", field: k, reason: "required" }, { status: 422 });
    }
  }

  try {
    const created = await createCustomAgent({
      slug: body.slug as string,
      name: body.name as string,
      category: body.category as CreateAgentInput["category"],
      short_description: body.short_description as string,
      description: body.description,
      base_prompt: body.base_prompt as string,
      required_tools: body.required_tools,
      suggested_model: body.suggested_model,
      pricing: body.pricing,
      is_public: body.is_public ?? false,
      created_by: user.id,
      tenant_id: profile.tenant_id,
    });
    return NextResponse.json({ ok: true, agent: created });
  } catch (err) {
    if (err instanceof AgentPersistenceError) {
      const status = err.code === "duplicate_slug" ? 409 : err.code === "validation" ? 422 : 500;
      return NextResponse.json({ ok: false, error: err.code, message: err.message }, { status });
    }
    throw err;
  }
}
