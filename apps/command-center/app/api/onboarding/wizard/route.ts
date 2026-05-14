/**
 * POST /api/onboarding/wizard
 *
 * Final step of the industry-template onboarding flow. Body:
 *   {
 *     template: "real_estate" | "business_funding" | "ecommerce" | "agency" | "custom",
 *     slug:     "<url-segment>",
 *     answers:  { brand_name, tagline, ...industry-specific keys }
 *   }
 *
 * Server-side:
 *   1. Auth-gates the caller and resolves their tenant.
 *   2. Folds answers into the chosen template via finalizeManifestFromWizard.
 *   3. Validates the resulting manifest (parseManifest).
 *   4. Saves through the same audit-logged path the AI editor uses (actor=user,
 *      message="onboarding wizard"). The first save for a slug stamps tenant_id.
 *   5. Returns { ok, slug, manifest, version } for the client to redirect to
 *      /t/<slug>/.
 *
 * Slug collisions: if a manifest already exists for `slug`, we return 409 so
 * the client can ask the operator to pick another one.
 */

import { NextResponse, type NextRequest } from "next/server";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import {
  finalizeManifestFromWizard,
  isValidSlug,
  type WizardAnswers,
} from "@/lib/manifest/wizard-finalize";
import { TEMPLATES, type TemplateKey } from "@/lib/manifest/templates";
import { diffManifests } from "@/lib/manifest/diff";
import { parseManifest } from "@/lib/manifest/schema";
import {
  getManifestRow,
  ManifestPersistenceError,
  saveManifest,
} from "@/lib/manifest/persistence";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Body = {
  template?: string;
  slug?: string;
  answers?: WizardAnswers;
};

const TEMPLATE_KEYS: TemplateKey[] = ["real_estate", "business_funding", "ecommerce", "agency", "custom"];

export async function POST(req: NextRequest) {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });

  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const template = (body.template || "").toLowerCase() as TemplateKey;
  if (!TEMPLATE_KEYS.includes(template)) {
    return NextResponse.json({ ok: false, error: "unknown_template" }, { status: 400 });
  }
  const slug = (body.slug || "").trim().toLowerCase();
  if (!isValidSlug(slug)) {
    return NextResponse.json({ ok: false, error: "invalid_slug" }, { status: 400 });
  }
  const answers = body.answers || {};

  // Authorisation — the caller must be an owner or admin of their tenant.
  // Non-owners attempting to spin up a parallel Command Center is a Phase 3
  // marketplace concern; locked down for v1.
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

  // Slug collision check before we bother running mutations.
  const existing = await getManifestRow(slug).catch(() => null);
  if (existing) {
    return NextResponse.json({ ok: false, error: "slug_taken" }, { status: 409 });
  }

  let manifest;
  try {
    manifest = finalizeManifestFromWizard({ template, slug, answers });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: "build_failed", message: err instanceof Error ? err.message : "unknown" },
      { status: 422 }
    );
  }

  // Re-validate via the schema parser so any drift between the template
  // and the parser surface fails loudly before we touch the DB.
  try {
    manifest = parseManifest(manifest);
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: "validation_failed", message: err instanceof Error ? err.message : "unknown" },
      { status: 422 }
    );
  }

  // Audit row diffs against the chosen template's starting state so the
  // history shows what the wizard's answers actually changed vs the
  // out-of-the-box template.
  const baseTemplate = TEMPLATES[template];
  const diff = diffManifests(baseTemplate, manifest);

  try {
    const result = await saveManifest({
      slug,
      next: manifest,
      diff,
      actor: { type: "user", id: user.id },
      message: `Onboarding wizard — template "${template}"`,
      tenant_id: profile.tenant_id,
    });
    return NextResponse.json({
      ok: true,
      slug,
      manifest: result.row.manifest,
      version: result.row.version,
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
