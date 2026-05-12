import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { timeAgo, truncate } from "@/lib/fmt";
import { getActiveProfile, getLeadsForTenant } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { cookies } from "next/headers";
import { DEMO_CLIENT_PROFILE_COOKIE } from "@/lib/client-profiles";
import { SUNBIZ_DEMO_LEADS } from "@/lib/sunbiz-demo-data";

export const dynamic = "force-dynamic";

export default async function LeadsPage() {
  const demoProfile = (await cookies()).get(DEMO_CLIENT_PROFILE_COOKIE)?.value || null;
  const demoMode = demoProfile === "sun";
  const profile = await safe("leads.profile", getActiveProfile(), null);
  const tenantId = demoMode ? "" : profile?.tenant_id || "";
  const leads = demoMode
    ? SUNBIZ_DEMO_LEADS
    : tenantId
      ? await safe("leads.list", getLeadsForTenant(tenantId, 100), [])
      : [];

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Leads"
        subtitle={
          demoMode
            ? "Sun demo mode · sample leads are loaded so you can see Solara's workflow"
            : tenantId
              ? `${leads.length} leads · tenant-scoped`
              : "No tenant configured for this profile yet"
        }
      />

      <Card title="All leads" subtitle="Active funding prospects" noPadding>
        {leads.length === 0 ? (
          <div className="p-5">
            <EmptyState message="No leads yet. Pull from JotForm or run /lead-ingest in the Sun Biz Agent." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-bg-border">
                <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold">
                  <th className="px-5 py-3">Last touch</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Score</th>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Company</th>
                  <th className="px-5 py-3">Email</th>
                  <th className="px-5 py-3">Phone</th>
                  <th className="px-5 py-3">Source</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr
                    key={lead.id}
                    className="border-b border-bg-border last:border-0 hover:bg-bg-hover/30 transition-colors"
                  >
                    <td className="px-5 py-3 text-fg-dim text-sm">
                      {timeAgo(lead.last_contacted_at || lead.updated_at)}
                    </td>
                    <td className="px-5 py-3">
                      <Tag
                        tone={
                          lead.status === "qualified"
                            ? "engaged"
                            : lead.status === "lost" || lead.status === "archived"
                              ? "neutral"
                              : lead.status === "won"
                                ? "engaged"
                                : "info"
                        }
                      >
                        {lead.status || "new"}
                      </Tag>
                    </td>
                    <td className="px-5 py-3 text-fg font-mono text-sm">{lead.score ?? "-"}</td>
                    <td className="px-5 py-3 text-fg text-sm">{truncate(lead.name, 28)}</td>
                    <td className="px-5 py-3 text-fg-muted text-sm">{truncate(lead.company, 28)}</td>
                    <td className="px-5 py-3 text-fg-muted font-mono text-xs">{truncate(lead.email, 32)}</td>
                    <td className="px-5 py-3 text-fg-muted font-mono text-xs">{lead.phone || "-"}</td>
                    <td className="px-5 py-3 text-fg-dim text-xs">{lead.source || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
