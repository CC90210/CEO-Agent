/**
 * /api/forms/[id] — operator-facing per-form mutations (Phase 3.2).
 *
 * GET    → fetch one form (RLS-scoped).
 * PATCH  → update name / description / branding / steps / step_outcomes /
 *          on_complete_stage / enabled / redirect_url. Slug is NOT
 *          editable (URLs depend on it); operators rename via delete +
 *          create if they truly need a different slug.
 * DELETE → soft-delete by setting enabled=false. Hard-delete via the
 *          DELETE method drops the row + cascades to form_submissions
 *          (rare; only used during cleanup).
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import {
  parseFormSteps,
  parseFormBranding,
  parseStepOutcomes,
  FormDefinitionError,
} from "@/lib/forms/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function resolveTenantId(): Promise<string | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const db = getServiceSupabase();
  const { data } = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  return (data as { tenant_id: string | null } | null)?.tenant_id ?? null;
}

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("forms")
    .select("*")
    .eq("id", id)
    .eq("tenant_id", tenantId)
    .maybeSingle();
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ ok: false, error: "not_found" }, { status: 404 });
  }
  return NextResponse.json({ ok: true, form: data });
}

export async function PATCH(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Build the patch only from keys explicitly present in the body — we
  // don't want to clobber unset columns with undefined.
  const patch: Record<string, unknown> = {};
  if ("name" in body) {
    const v = String(body.name || "").trim();
    if (!v) return NextResponse.json({ ok: false, error: "name_empty" }, { status: 400 });
    patch.name = v.slice(0, 200);
  }
  if ("description" in body) {
    patch.description = body.description ? String(body.description).slice(0, 1000) : null;
  }
  if ("branding" in body) {
    try {
      patch.branding = parseFormBranding(body.branding);
    } catch (err) {
      if (err instanceof FormDefinitionError) {
        return NextResponse.json(
          { ok: false, error: "invalid_branding", path: err.path, reason: err.reason },
          { status: 400 },
        );
      }
      throw err;
    }
  }
  if ("steps" in body) {
    try {
      patch.steps = parseFormSteps(body.steps);
    } catch (err) {
      if (err instanceof FormDefinitionError) {
        return NextResponse.json(
          { ok: false, error: "invalid_steps", path: err.path, reason: err.reason },
          { status: 400 },
        );
      }
      throw err;
    }
  }
  if ("step_outcomes" in body) {
    try {
      patch.step_outcomes = parseStepOutcomes(body.step_outcomes);
    } catch (err) {
      if (err instanceof FormDefinitionError) {
        return NextResponse.json(
          { ok: false, error: "invalid_step_outcomes", path: err.path, reason: err.reason },
          { status: 400 },
        );
      }
      throw err;
    }
  }
  if ("on_complete_stage" in body) {
    patch.on_complete_stage = body.on_complete_stage
      ? String(body.on_complete_stage)
      : null;
  }
  if ("enabled" in body) {
    patch.enabled = Boolean(body.enabled);
  }
  if ("redirect_url" in body) {
    patch.redirect_url = body.redirect_url
      ? String(body.redirect_url).slice(0, 2000)
      : null;
  }

  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ ok: false, error: "no_changes" }, { status: 400 });
  }

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("forms")
    .update(patch)
    .eq("id", id)
    .eq("tenant_id", tenantId)
    .select()
    .single();
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, form: data });
}

export async function DELETE(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  const db = getServiceSupabase();
  const { error } = await db
    .from("forms")
    .delete()
    .eq("id", id)
    .eq("tenant_id", tenantId);
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
