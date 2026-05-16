/**
 * /leads — operator-facing pipeline view.
 *
 * 2026-05-15 rebuild: the prior static table couldn't handle scale.
 * LeadsTableClient adds stage tabs, search, sortable columns,
 * pagination — built for thousands of rows, not dozens. Per CC's
 * post-meeting feedback ("boxes too small, build proper
 * infrastructure for thousands of leads").
 */

import { PageHeader } from "@/components/Card";
import { getActiveProfile, getLeadsForTenant } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { cookies } from "next/headers";
import { DEMO_CLIENT_PROFILE_COOKIE } from "@/lib/client-profiles";
import { SUNBIZ_DEMO_LEADS } from "@/lib/sunbiz-demo-data";
import { LeadsTableClient } from "@/components/leads/LeadsTableClient";

export const dynamic = "force-dynamic";

export default async function LeadsPage() {
  const demoProfile = (await cookies()).get(DEMO_CLIENT_PROFILE_COOKIE)?.value || null;
  const demoMode = demoProfile === "sun";
  const profile = await safe("leads.profile", getActiveProfile(), null);
  const tenantId = demoMode ? "" : profile?.tenant_id || "";

  // Pull up to 500 leads — the client component paginates locally at
  // 50/page, so 500 is "10 pages of in-memory data" which feels
  // instant to the operator. Beyond that we'd want server-side cursor
  // pagination (Phase 13).
  const leads = demoMode
    ? SUNBIZ_DEMO_LEADS
    : tenantId
      ? await safe("leads.list", getLeadsForTenant(tenantId, 500), [])
      : [];

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Leads"
        subtitle={
          demoMode
            ? "Sun demo mode — sample leads loaded so you can see Solara's workflow."
            : tenantId
              ? leads.length === 0
                ? "Send the application form to your first prospect to get started."
                : `${leads.length} lead${leads.length === 1 ? "" : "s"} in the pipeline.`
              : "Finish onboarding to connect this workspace."
        }
      />

      {tenantId || demoMode ? (
        <LeadsTableClient initialLeads={leads} />
      ) : (
        <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-8 text-center text-fg-muted">
          Sign in to see your leads.
        </div>
      )}
    </div>
  );
}
