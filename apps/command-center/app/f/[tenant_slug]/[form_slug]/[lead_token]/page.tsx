/**
 * /f/[tenant_slug]/[form_slug]/[lead_token] — public-facing form page.
 *
 * Phase 3.4 of the SunBiz CRM build. The personalized URL Solara mints
 * via /api/forms/[id]/mint-link drops a prospect here. Server component
 * verifies the HMAC token before rendering anything; on success it
 * loads the form definition + hands off to FormPublicClient for the
 * multi-step interactive funnel.
 *
 * No session cookie required — the HMAC token IS the auth boundary.
 * Failures (malformed / expired / tampered token, disabled form,
 * tenant-slug mismatch) render a clean error page instead of 500.
 */

import { notFound } from "next/navigation";
import { getServiceSupabase } from "@/lib/supabase-server";
import { verifyFormLink } from "@/lib/form-links";
import { FormPublicClient } from "@/components/forms/FormPublicClient";
import {
  parseFormSteps,
  parseFormBranding,
  parseStepOutcomes,
  type FormStep,
  type FormBranding,
} from "@/lib/forms/types";

export const dynamic = "force-dynamic";

// No-store on the public form page — personalized links are per-lead;
// caching one prospect's render and serving it to another would be a
// data-leak vector even if the HMAC verification still gates submits.
export const revalidate = 0;

type RouteParams = {
  tenant_slug: string;
  form_slug: string;
  lead_token: string;
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
        on_complete_stage: string | null;
        step_outcomes: Record<string, string>;
        redirect_url: string | null;
      };
      tenant_slug: string;
      lead_id: string;
      token: string;
    }
  | { ok: false; reason: "token" | "tenant_mismatch" | "form_disabled" | "form_corrupt" | "not_found"; detail?: string };

async function loadAndVerify(params: RouteParams): Promise<LoadResult> {
  const sig = verifyFormLink(params.lead_token);
  if (!sig.ok) {
    return { ok: false, reason: "token", detail: sig.reason };
  }
  if (sig.payload.tenant !== params.tenant_slug.toLowerCase()) {
    // The URL's tenant_slug doesn't match the signed token. Means
    // someone copied the token into a different tenant's URL space.
    return { ok: false, reason: "tenant_mismatch" };
  }

  const db = getServiceSupabase();
  const row = await db
    .from("forms")
    .select(
      "id, tenant_id, slug, name, branding, steps, on_complete_stage, step_outcomes, enabled, redirect_url, tenant:tenants!inner(slug)",
    )
    .eq("id", sig.payload.form_id)
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
    on_complete_stage: string | null;
    step_outcomes: unknown;
    enabled: boolean;
    redirect_url: string | null;
    tenant: { slug: string } | { slug: string }[] | null;
  };
  // The URL slug must also match the form's stored slug — defends
  // against a token paired with a swapped form_slug.
  if (form.slug !== params.form_slug.toLowerCase()) {
    return { ok: false, reason: "not_found" };
  }
  const tenantRow = Array.isArray(form.tenant) ? form.tenant[0] : form.tenant;
  if (!tenantRow || tenantRow.slug !== sig.payload.tenant) {
    return { ok: false, reason: "tenant_mismatch" };
  }
  if (!form.enabled) {
    return { ok: false, reason: "form_disabled" };
  }

  let steps: FormStep[];
  let branding: FormBranding;
  let stepOutcomes: Record<string, string>;
  try {
    steps = parseFormSteps(form.steps);
    branding = parseFormBranding(form.branding);
    stepOutcomes = parseStepOutcomes(form.step_outcomes);
  } catch (err) {
    return {
      ok: false,
      reason: "form_corrupt",
      detail: err instanceof Error ? err.message : String(err),
    };
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
      on_complete_stage: form.on_complete_stage,
      step_outcomes: stepOutcomes,
      redirect_url: form.redirect_url,
    },
    tenant_slug: sig.payload.tenant,
    lead_id: sig.payload.lead_id,
    token: params.lead_token,
  };
}

export default async function PublicFormPage({
  params,
}: {
  params: Promise<RouteParams>;
}) {
  const resolved = await params;
  const result = await loadAndVerify(resolved);

  if (!result.ok) {
    if (result.reason === "not_found" || result.reason === "tenant_mismatch") {
      notFound();
    }
    // Surface a clean error page rather than 500 — operators routinely
    // copy links around; expired / disabled / corrupt-form cases need
    // honest copy.
    return <FormErrorPage reason={result.reason} detail={result.detail} />;
  }

  return (
    <FormPublicClient
      formId={result.form.id}
      formName={result.form.name}
      branding={result.form.branding}
      steps={result.form.steps}
      redirectUrl={result.form.redirect_url}
      token={result.token}
    />
  );
}

function FormErrorPage({
  reason,
  detail,
}: {
  reason: "token" | "form_disabled" | "form_corrupt";
  detail?: string;
}) {
  const copy =
    reason === "token"
      ? detail === "expired"
        ? {
            title: "This link has expired",
            body: "Personalized form links are valid for 60 days. Reach out to your contact at OASIS and they'll send you a fresh link.",
          }
        : {
            title: "This link isn't valid",
            body: "The form link looks tampered with. If you copied it from an email or text, try clicking the original link instead of pasting it.",
          }
      : reason === "form_disabled"
        ? {
            title: "This form isn't accepting submissions right now",
            body: "Reach out to your contact at OASIS — we'll let you know when it reopens.",
          }
        : {
            title: "Form configuration error",
            body: "The form's definition is malformed. Operators: open the form in /forms/[id]/edit to fix.",
          };

  return (
    <main className="min-h-screen bg-bg-deep text-fg flex items-center justify-center px-6 py-10">
      <div className="max-w-md w-full rounded-2xl border border-bg-border bg-bg-elev/50 p-8 text-center space-y-3">
        <h1 className="text-xl font-bold">{copy.title}</h1>
        <p className="text-sm text-fg-muted leading-relaxed">{copy.body}</p>
        {detail && reason === "form_corrupt" && (
          <pre className="text-[10px] font-mono text-fg-dim text-left bg-bg-deep border border-bg-border rounded p-2 overflow-x-auto">
            {detail}
          </pre>
        )}
      </div>
    </main>
  );
}
