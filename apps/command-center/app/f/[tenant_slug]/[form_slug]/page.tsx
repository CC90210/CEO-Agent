/**
 * /f/[tenant_slug]/[form_slug] — anonymous share-link form page.
 *
 * Sibling of /f/[tenant_slug]/[form_slug]/[lead_token]/page.tsx (the
 * Solara-minted personalized flow). This route is the one operators
 * copy from the Forms dashboard and paste into Slack / SMS / etc —
 * anyone with the URL can fill the form, and the server creates a
 * fresh lead on submit (NOT on page-load, to avoid bot-driven row
 * inflation). The first call to /api/forms/submit goes out with
 * anonymous_init = { tenant_slug, form_slug } and no token; the
 * server replies with a signed token the client uses for subsequent
 * steps in the same session.
 *
 * No HMAC verification on this route — auth is bound to the form's
 * `enabled` flag and the (tenant_slug, form_slug) uniqueness check in
 * the submit route.
 */

import { notFound } from "next/navigation";
import { getServiceSupabase } from "@/lib/supabase-server";
import { FormPublicClient } from "@/components/forms/FormPublicClient";
import {
  parseFormSteps,
  parseFormBranding,
  type FormStep,
  type FormBranding,
} from "@/lib/forms/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type RouteParams = {
  tenant_slug: string;
  form_slug: string;
};

type LoadResult =
  | {
      ok: true;
      form: {
        id: string;
        tenant_id: string;
        slug: string;
        name: string;
        branding: FormBranding;
        steps: FormStep[];
        redirect_url: string | null;
      };
      tenant_slug: string;
    }
  | {
      ok: false;
      reason: "not_found" | "form_corrupt";
      detail?: string;
    };

async function loadForm(params: RouteParams): Promise<LoadResult> {
  const tenantSlug = params.tenant_slug.toLowerCase();
  const formSlug = params.form_slug.toLowerCase();
  const db = getServiceSupabase();
  // Resolve tenant_id first, then look up the form by (tenant_id, slug).
  // The schema permits same form_slug across different tenants
  // (UNIQUE constraint is per-tenant), so a global slug query can hit
  // the wrong row. All negative responses collapse to 404 so this
  // route can't be used to enumerate which tenants exist by diffing
  // status codes.
  const tenantRowQ = await db
    .from("tenants")
    .select("id, logo_url")
    .eq("slug", tenantSlug)
    .maybeSingle();
  const tenantRow = tenantRowQ.data as
    | { id: string; logo_url: string | null }
    | null;
  if (!tenantRow) {
    return { ok: false, reason: "not_found" };
  }
  const row = await db
    .from("forms")
    .select(
      "id, tenant_id, slug, name, branding, steps, enabled, redirect_url",
    )
    .eq("tenant_id", tenantRow.id)
    .eq("slug", formSlug)
    .maybeSingle();
  if (row.error || !row.data) {
    return { ok: false, reason: "not_found" };
  }
  const form = row.data as {
    id: string;
    tenant_id: string;
    slug: string;
    name: string;
    branding: unknown;
    steps: unknown;
    enabled: boolean;
    redirect_url: string | null;
  };
  if (!form.enabled) {
    return { ok: false, reason: "not_found" };
  }

  let steps: FormStep[];
  let branding: FormBranding;
  try {
    steps = parseFormSteps(form.steps);
    branding = parseFormBranding(form.branding);
  } catch (err) {
    return {
      ok: false,
      reason: "form_corrupt",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  // Tenant-logo fallback (same rule the personalized route uses).
  if (branding.logo_url == null && tenantRow.logo_url) {
    branding = { ...branding, logo_url: tenantRow.logo_url };
  }

  return {
    ok: true,
    form: {
      id: form.id,
      tenant_id: form.tenant_id,
      slug: form.slug,
      name: form.name,
      branding,
      steps,
      redirect_url: form.redirect_url,
    },
    tenant_slug: tenantSlug,
  };
}

export default async function AnonymousFormPage({
  params,
}: {
  params: Promise<RouteParams>;
}) {
  const resolved = await params;
  const result = await loadForm(resolved);

  if (!result.ok) {
    if (result.reason === "form_corrupt") {
      return <FormErrorPage reason={result.reason} detail={result.detail} />;
    }
    notFound();
  }

  return (
    <FormPublicClient
      formId={result.form.id}
      formName={result.form.name}
      branding={result.form.branding}
      steps={result.form.steps}
      redirectUrl={result.form.redirect_url}
      token={null}
      anonymousInit={{
        tenant_slug: result.tenant_slug,
        form_slug: result.form.slug,
      }}
    />
  );
}

function FormErrorPage({
  detail,
}: {
  reason: "form_corrupt";
  detail?: string;
}) {
  const copy = {
    title: "Form configuration error",
    body: "The form's definition is malformed. Operators: open the form in /forms/[id]/edit to fix.",
  };
  return (
    <main className="min-h-screen bg-bg-deep text-fg flex items-center justify-center px-6 py-10">
      <div className="max-w-md w-full rounded-2xl border border-bg-border bg-bg-elev/50 p-8 text-center space-y-3">
        <h1 className="text-xl font-bold">{copy.title}</h1>
        <p className="text-sm text-fg-muted leading-relaxed">{copy.body}</p>
        {detail && (
          <pre className="text-[10px] font-mono text-fg-dim text-left bg-bg-deep border border-bg-border rounded p-2 overflow-x-auto">
            {detail}
          </pre>
        )}
      </div>
    </main>
  );
}
