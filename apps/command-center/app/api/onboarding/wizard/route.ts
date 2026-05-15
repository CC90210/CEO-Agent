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
import { SEED_MANIFESTS } from "@/lib/manifest/seeds";
import {
  getManifestRow,
  ManifestPersistenceError,
  saveManifest,
} from "@/lib/manifest/persistence";
import { PROTECTED_SLUGS } from "@/lib/manifest/guards";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Body = {
  template?: string;
  slug?: string;
  answers?: WizardAnswers;
  /** Phase J — per-agent setup questionnaire answers from the wizard's
   *  agent_setup step. Map<agentSlug, Record<questionId, value>>. We
   *  stamp these onto each matching manifest.agents[] binding's
   *  setup_answers field after the template is finalized. */
  agent_setup_answers?: Record<string, Record<string, string | number | boolean>>;
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
  // Platform seed slugs (default/oasis/sun/suga) are owned by the platform;
  // tenants pick their own slug instead of overwriting the safety-net seeds.
  // Uses the shared PROTECTED_SLUGS set so guard adds in lib/manifest/guards.ts
  // automatically reach the wizard too.
  if (SEED_MANIFESTS[slug] || PROTECTED_SLUGS.has(slug)) {
    return NextResponse.json({ ok: false, error: "reserved_slug", reason: `"${slug}" is reserved — pick a different URL slug.` }, { status: 409 });
  }
  const answers = body.answers || {};

  // Authorisation — wizard is the CREATE path, so any authenticated user
  // with a tenant_id can run it for an unclaimed slug. Edits go through
  // /api/manifest/<slug> POST which still gates on admin/owner role.
  const service = getServiceSupabase();
  const profileQuery = await service
    .from("user_profiles")
    .select("id, tenant_id, team_role, is_owner")
    .eq("auth_user_id", user.id)
    .maybeSingle();
  const profile = profileQuery.data as
    | { id: string; tenant_id: string | null; team_role: string; is_owner: boolean }
    | null;
  if (!profile?.tenant_id) {
    return NextResponse.json({ ok: false, error: "no_tenant" }, { status: 403 });
  }

  // Slug collision + cross-tenant claim check. The wizard is CREATE only —
  // an existing row means the slug is taken (whether by this tenant or
  // another) and the caller should pick a different name.
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

  // Phase J — stamp per-agent setup_answers onto matching agent bindings.
  // The wizard collected these in its agent_setup step; we drop them onto
  // the manifest before the schema parser runs so they get round-trip
  // validated like every other field. Unknown agent slugs in the answers
  // map are silently ignored (operator might have toggled an agent off
  // after answering its questions).
  if (body.agent_setup_answers && typeof body.agent_setup_answers === "object") {
    const setupBySlug = body.agent_setup_answers;
    manifest = {
      ...manifest,
      agents: (manifest.agents || []).map((a: { slug: string }) => {
        const answersForSlug = setupBySlug[a.slug.toLowerCase()];
        if (answersForSlug && typeof answersForSlug === "object" && !Array.isArray(answersForSlug)) {
          // Sanitize — only keep scalar values, drop nulls / undefined.
          const cleaned: Record<string, string | number | boolean> = {};
          for (const [k, v] of Object.entries(answersForSlug)) {
            if (v === null || v === undefined) continue;
            if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
              cleaned[k] = v;
            }
          }
          if (Object.keys(cleaned).length > 0) {
            return { ...a, setup_answers: cleaned };
          }
        }
        return a;
      }),
    };
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

    // First-owner auto-promotion. If this tenant has no `is_owner=true`
    // user_profile yet, the wizard caller becomes the owner. Migration 037b
    // does the same backfill manually; this closes the gap for self-service
    // signups so a brand-new user can keep editing the manifest they just
    // created (the POST /api/manifest/<slug> endpoint still gates on admin/
    // owner role). Existing tenants with an established owner are not
    // affected.
    //
    // Race-safe: two users hitting the wizard at the same instant both pass
    // the existence check; the second UPDATE collides with the partial
    // unique index `user_profiles_one_owner_per_tenant` and Postgres
    // returns code 23505. We swallow that — the first user won the race
    // and is now the legitimate owner, which is the correct outcome. Any
    // other DB error still surfaces (manifest persisted, audit logged, so
    // the caller already has the v1 row and can retry the promotion via
    // the team-management UI if it ever matters).
    const ownerCheck = await service
      .from("user_profiles")
      .select("id")
      .eq("tenant_id", profile.tenant_id)
      .eq("is_owner", true)
      .limit(1)
      .maybeSingle();
    if (!ownerCheck.data && !profile.is_owner) {
      const promote = await service
        .from("user_profiles")
        .update({ is_owner: true, team_role: "owner" })
        .eq("id", profile.id);
      if (promote.error && promote.error.code !== "23505") {
        // Log but don't fail the response — the manifest is already saved.
        console.warn(
          `[onboarding.wizard] owner-promotion failed for profile ${profile.id}: ${promote.error.message}`
        );
      }
    }

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
