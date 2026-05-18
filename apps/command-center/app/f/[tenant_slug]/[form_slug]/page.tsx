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

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getServiceSupabase } from "@/lib/supabase-server";
import { FormPublicClient } from "@/components/forms/FormPublicClient";
import {
  parseFormSteps,
  parseFormBranding,
  type FormStep,
  type FormBranding,
} from "@/lib/forms/types";
import { resolvePublicForm } from "@/lib/forms/public-resolver";

export const dynamic = "force-dynamic";

/**
 * Per-form metadata so the browser tab shows the tenant brand instead of
 * the dashboard's default "OASIS AI · Agent Command Center". A prospect
 * opening a SunBiz application form sees "SunBiz Funding · Tell us about
 * your business" in their tab — not the operator-side product name.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<RouteParams>;
}): Promise<Metadata> {
  const resolved = await params;
  const db = getServiceSupabase();
  const lookup = await resolvePublicForm(db, resolved.tenant_slug, resolved.form_slug);
  if (!lookup.ok) {
    return { title: "Form" };
  }
  let title = lookup.form.name || "Application";
  try {
    const branding = parseFormBranding(lookup.form.branding);
    if (branding.headline) title = branding.headline;
  } catch {
    // Fall through to form name on parse failure.
  }
  return {
    title,
    // Public form pages should never be indexed — every URL is a single-
    // tenant intake form, not marketing content. noindex,nofollow keeps
    // Google out and avoids "OASIS AI dashboard" pages showing up in
    // tenant-branded search results.
    robots: { index: false, follow: false },
  };
}
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
  const db = getServiceSupabase();
  const resolved = await resolvePublicForm(db, params.tenant_slug, params.form_slug);
  if (!resolved.ok) {
    return { ok: false, reason: "not_found" };
  }

  let steps: FormStep[];
  let branding: FormBranding;
  try {
    steps = parseFormSteps(resolved.form.steps);
    branding = parseFormBranding(resolved.form.branding);
  } catch (err) {
    return {
      ok: false,
      reason: "form_corrupt",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  // Tenant-logo fallback (same rule the personalized route uses).
  if (branding.logo_url == null && resolved.tenant_logo_url) {
    branding = { ...branding, logo_url: resolved.tenant_logo_url };
  }

  return {
    ok: true,
    form: {
      id: resolved.form.id,
      tenant_id: resolved.form.tenant_id,
      slug: resolved.form.slug,
      name: resolved.form.name,
      branding,
      steps,
      redirect_url: resolved.form.redirect_url,
    },
    tenant_slug: resolved.tenant_slug,
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
