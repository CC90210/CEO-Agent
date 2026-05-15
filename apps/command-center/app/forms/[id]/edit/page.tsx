/**
 * /forms/[id]/edit — operator form-builder page.
 *
 * Phase 3.3 of the SunBiz CRM build. Server component loads the form
 * row (tenant-scoped via service-role + explicit user_profiles join),
 * then hands it to FormBuilderClient which owns the JSON editor +
 * live preview.
 *
 * 404 when the form doesn't belong to this user's tenant — defends
 * against a guessed-UUID URL.
 */

import { PageHeader } from "@/components/Card";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { FormBuilderClient } from "@/components/forms/FormBuilderClient";
import Link from "next/link";
import { redirect, notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import {
  parseFormSteps,
  parseFormBranding,
  parseStepOutcomes,
  type FormStep,
  type FormBranding,
} from "@/lib/forms/types";

export const dynamic = "force-dynamic";

type FormDbRow = {
  id: string;
  tenant_id: string;
  slug: string;
  name: string;
  description: string | null;
  branding: unknown;
  steps: unknown;
  on_complete_stage: string | null;
  step_outcomes: unknown;
  enabled: boolean;
  redirect_url: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

async function loadForm(id: string, userId: string): Promise<FormDbRow | null> {
  const db = getServiceSupabase();
  const profileRow = await db
    .from("user_profiles")
    .select("tenant_id")
    .eq("auth_user_id", userId)
    .maybeSingle();
  const tenantId = (profileRow.data as { tenant_id: string | null } | null)?.tenant_id;
  if (!tenantId) return null;
  const { data, error } = await db
    .from("forms")
    .select("*")
    .eq("id", id)
    .eq("tenant_id", tenantId)
    .maybeSingle();
  if (error || !data) return null;
  return data as FormDbRow;
}

export default async function EditFormPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  const { id } = await params;
  const row = await loadForm(id, user.id);
  if (!row) notFound();

  // Parse the jsonb columns once on the server — if they're somehow
  // malformed (manual DB edit, schema migration drift), the parsers
  // throw which Next.js renders as a 500 page. Builder UI handles
  // the validation case via the live preview's error pane instead.
  let steps: FormStep[];
  let branding: FormBranding;
  let stepOutcomes: Record<string, string>;
  try {
    steps = parseFormSteps(row.steps);
    branding = parseFormBranding(row.branding);
    stepOutcomes = parseStepOutcomes(row.step_outcomes);
  } catch (err) {
    // Surface a clean error page rather than the default 500. Operators
    // who somehow end up here can use the JSON editor to fix the bad row.
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader
          title="Form definition corrupt"
          subtitle={`forms.id=${row.id} has malformed jsonb. Drop into the editor to fix.`}
        />
        <pre className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs font-mono text-rose-400 overflow-x-auto">
          {err instanceof Error ? err.message : String(err)}
        </pre>
        <Link href="/forms" className="text-sm text-accent hover:text-accent-bright">
          ← Back to forms
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/forms"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent"
      >
        <ChevronLeft className="w-3 h-3" />
        Back to forms
      </Link>
      <PageHeader
        title={row.name || "Untitled form"}
        subtitle={`Slug: ${row.slug} · ${row.enabled ? "Live" : "Disabled"}`}
      />
      <FormBuilderClient
        initialForm={{
          id: row.id,
          slug: row.slug,
          name: row.name,
          description: row.description,
          branding,
          steps,
          on_complete_stage: row.on_complete_stage,
          step_outcomes: stepOutcomes,
          enabled: row.enabled,
          redirect_url: row.redirect_url,
        }}
      />
    </div>
  );
}
