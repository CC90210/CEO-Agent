/**
 * /api/forms — operator-facing CRUD for tenant-defined forms (Phase 3.2).
 *
 * GET  → list this tenant's forms (RLS-scoped via the authed user).
 * POST → create a new form. Body shape mirrors lib/forms/types.ts:
 *          { slug, name, description?, branding?, steps,
 *            on_complete_stage?, step_outcomes?, enabled?, redirect_url? }
 *
 * Per-row update / delete + link minting live at /api/forms/[id]/...
 *
 * Public form-submission + view-tracking lives at /api/forms/submit and
 * /api/forms/view — those routes use HMAC bearer auth, not session
 * cookies, so prospects can submit without an OASIS account.
 */

import { NextRequest, NextResponse } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { isMissingTableError, missingTablePayload } from "@/lib/api-helpers";
import {
  parseFormSteps,
  parseFormBranding,
  parseStepOutcomes,
  FormDefinitionError,
} from "@/lib/forms/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{1,62}$/;

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

async function resolveUserId(): Promise<string | null> {
  const user = await getSessionUser();
  return user?.id ?? null;
}

export async function GET() {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("forms")
    .select(
      "id, tenant_id, slug, name, description, branding, steps, on_complete_stage, step_outcomes, enabled, redirect_url, created_by, created_at, updated_at",
    )
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false });

  if (error) {
    if (isMissingTableError(error, "public.forms")) {
      return NextResponse.json(
        missingTablePayload({
          migration: "database/042_tenant_forms.sql",
          feature: "Forms",
        }),
        { status: 503 },
      );
    }
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, forms: data || [] });
}

export async function POST(req: NextRequest) {
  const tenantId = await resolveTenantId();
  if (!tenantId) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const userId = await resolveUserId();

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  // Slug — operator-supplied, immutable after create (URLs depend on it).
  const slug = String(body.slug || "").trim().toLowerCase();
  if (!SLUG_RE.test(slug)) {
    return NextResponse.json(
      { ok: false, error: "invalid_slug", hint: "must match /^[a-z0-9][a-z0-9_-]{1,62}$/" },
      { status: 400 },
    );
  }

  const name = String(body.name || "").trim();
  if (!name) {
    return NextResponse.json({ ok: false, error: "name_required" }, { status: 400 });
  }

  // Validate jsonb shapes via the shared parsers. parseFormSteps throws
  // when steps is empty / malformed; we catch + 400 with the path so the
  // builder UI can highlight the field.
  let steps, branding, stepOutcomes;
  try {
    steps = parseFormSteps(body.steps);
    branding = parseFormBranding(body.branding);
    stepOutcomes = parseStepOutcomes(body.step_outcomes);
  } catch (err) {
    if (err instanceof FormDefinitionError) {
      return NextResponse.json(
        { ok: false, error: "invalid_definition", path: err.path, reason: err.reason },
        { status: 400 },
      );
    }
    throw err;
  }

  const db = getServiceSupabase();
  const { data, error } = await db
    .from("forms")
    .insert({
      tenant_id: tenantId,
      slug,
      name: name.slice(0, 200),
      description: body.description ? String(body.description).slice(0, 1000) : null,
      branding,
      steps,
      on_complete_stage: body.on_complete_stage ? String(body.on_complete_stage) : null,
      step_outcomes: stepOutcomes,
      enabled: body.enabled !== false,
      redirect_url: body.redirect_url ? String(body.redirect_url).slice(0, 2000) : null,
      created_by: userId,
    })
    .select()
    .single();

  if (error) {
    // Slug uniqueness violation — surface as a 409 with a friendly
    // message so the builder UI can prompt for a different slug.
    if (error.code === "23505") {
      return NextResponse.json(
        { ok: false, error: "slug_taken", hint: `A form with slug "${slug}" already exists for this tenant.` },
        { status: 409 },
      );
    }
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, form: data });
}
