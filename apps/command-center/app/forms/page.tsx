/**
 * /forms — operator-facing list of tenant-defined forms.
 *
 * Phase 3.3 of the SunBiz CRM build. Lists every form the tenant has
 * created, with quick actions: enable/disable, copy slug, open editor,
 * delete. "New form" button creates a stub form with one empty step,
 * then redirects to the editor for the operator to flesh out.
 */

import { PageHeader } from "@/components/Card";
import { getActiveProfile } from "@/lib/queries";
import { getSessionUser, getServiceSupabase } from "@/lib/supabase-server";
import { safe, isMissingTableError } from "@/lib/api-helpers";
import { FormsListClient } from "@/components/forms/FormsListClient";
import { AlertCircle } from "lucide-react";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

type FormRow = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

async function loadForms(tenantId: string | null): Promise<
  | { ok: true; rows: FormRow[] }
  | { ok: false; reason: "no_tenant" | "migration_not_applied" | "db_error"; detail?: string }
> {
  if (!tenantId) return { ok: false, reason: "no_tenant" };
  const db = getServiceSupabase();
  const { data, error } = await db
    .from("forms")
    .select("id, slug, name, description, enabled, created_at, updated_at")
    .eq("tenant_id", tenantId)
    .order("created_at", { ascending: false });
  if (error) {
    if (isMissingTableError(error, "public.forms")) {
      return { ok: false, reason: "migration_not_applied" };
    }
    return { ok: false, reason: "db_error", detail: error.message };
  }
  return { ok: true, rows: (data as FormRow[]) || [] };
}

export default async function FormsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const profile = await safe("forms.profile", getActiveProfile(), null);
  const result = await loadForms(profile?.tenant_id || null);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Forms"
        subtitle="First-party forms with personalized lead links. Built-in replacement for JotForm + similar 3rd-party intake."
      />

      {!result.ok && result.reason === "no_tenant" && (
        <div className="rounded-xl border border-status-warm/40 bg-status-warm/5 p-4 text-sm text-status-warm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>No tenant resolved for this user. Complete onboarding first.</span>
        </div>
      )}

      {!result.ok && result.reason === "migration_not_applied" && (
        <div className="rounded-xl border border-accent/40 bg-accent/5 p-4 space-y-2">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-accent shrink-0 mt-0.5" />
            <div className="flex-1 text-sm">
              <div className="font-bold text-fg">One-time setup required</div>
              <p className="text-xs text-fg-muted mt-1 leading-relaxed">
                The Forms feature needs migration 042 applied to your Supabase
                project. Run the command below on the operator machine. After
                it completes, refresh the page.
              </p>
            </div>
          </div>
          <div className="rounded-md bg-bg-deep border border-bg-border p-2.5 font-mono text-[11px] text-fg-muted select-all">
            python scripts/apply_migration.py database/042_tenant_forms.sql
          </div>
        </div>
      )}

      {!result.ok && result.reason === "db_error" && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-400">
          <div className="font-bold">Couldn&apos;t load forms.</div>
          <div className="text-xs mt-1 font-mono">{result.detail}</div>
        </div>
      )}

      {result.ok && <FormsListClient initialRows={result.rows} />}
    </div>
  );
}
