/**
 * Shared resolver for the public-form surfaces (/f/[tenant_slug]/[form_slug]
 * page and the anonymous_init path in /api/forms/submit). Both surfaces need
 * to:
 *   1. Resolve tenant_id from tenant_slug (NOT trust slug equality alone —
 *      schema allows the same form_slug across different tenants).
 *   2. Look up forms by (tenant_id, slug).
 *   3. Verify enabled.
 *   4. Collapse every negative case to a single 'not_found' so the public
 *      route can't be used to enumerate tenants / form names.
 *
 * Without this helper the two callers drifted: one returned form_disabled
 * vs tenant_mismatch vs not_found (Codex MEDIUM 3, 2026-05-18).
 */
import type { SupabaseClient } from "@supabase/supabase-js";

export type PublicFormLookup =
  | {
      ok: true;
      tenant_id: string;
      tenant_slug: string;
      tenant_logo_url: string | null;
      form: {
        id: string;
        tenant_id: string;
        slug: string;
        name: string;
        branding: unknown;
        steps: unknown;
        on_complete_stage: string | null;
        step_outcomes: unknown;
        redirect_url: string | null;
      };
    }
  | { ok: false; reason: "not_found" };

export async function resolvePublicForm(
  db: SupabaseClient,
  tenantSlugRaw: string,
  formSlugRaw: string,
): Promise<PublicFormLookup> {
  const tenantSlug = tenantSlugRaw.trim().toLowerCase();
  const formSlug = formSlugRaw.trim().toLowerCase();
  if (!tenantSlug || !formSlug) return { ok: false, reason: "not_found" };

  const tenantQ = await db
    .from("tenants")
    .select("id, slug, logo_url")
    .eq("slug", tenantSlug)
    .maybeSingle();
  const tenantRow = tenantQ.data as
    | { id: string; slug: string; logo_url: string | null }
    | null;
  if (!tenantRow) return { ok: false, reason: "not_found" };

  const formQ = await db
    .from("forms")
    .select(
      "id, tenant_id, slug, name, branding, steps, on_complete_stage, step_outcomes, enabled, redirect_url",
    )
    .eq("tenant_id", tenantRow.id)
    .eq("slug", formSlug)
    .maybeSingle();
  const form = formQ.data as
    | {
        id: string;
        tenant_id: string;
        slug: string;
        name: string;
        branding: unknown;
        steps: unknown;
        on_complete_stage: string | null;
        step_outcomes: unknown;
        enabled: boolean;
        redirect_url: string | null;
      }
    | null;
  if (!form || !form.enabled) return { ok: false, reason: "not_found" };

  return {
    ok: true,
    tenant_id: tenantRow.id,
    tenant_slug: tenantRow.slug,
    tenant_logo_url: tenantRow.logo_url,
    form: {
      id: form.id,
      tenant_id: form.tenant_id,
      slug: form.slug,
      name: form.name,
      branding: form.branding,
      steps: form.steps,
      on_complete_stage: form.on_complete_stage,
      step_outcomes: form.step_outcomes,
      redirect_url: form.redirect_url,
    },
  };
}
