import { Card, EmptyState } from "@/components/Card";
import { timeAgo, truncate, statusColor } from "@/lib/fmt";
import { recentLeads, pipelineBreakdown } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function LeadsPage() {
  const [leads, pipeline] = await Promise.all([
    recentLeads(50),
    pipelineBreakdown(),
  ]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Leads</h1>
        <p className="text-sm text-fg-muted mt-1">
          The CRM pipeline, most-recently-updated first.
        </p>
      </header>

      <section className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {(["new", "contacted", "qualified", "proposal", "won", "lost"] as const).map(
          (stage) => (
            <div key={stage} className="rounded border border-bg-border p-3">
              <div className="text-xs uppercase tracking-wider text-fg-muted">
                {stage}
              </div>
              <div className={`text-2xl font-bold mt-1 ${statusColor(stage)}`}>
                {pipeline.stages[stage] || 0}
              </div>
            </div>
          ),
        )}
      </section>

      <Card title="Recent leads" subtitle={`${leads.length} shown of ${pipeline.total} total`}>
        {leads.length === 0 ? (
          <EmptyState message="No leads in the CRM yet. Try python scripts/lead_engine.py list." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-fg-muted uppercase tracking-wider border-b border-bg-border">
                  <th className="py-2 pr-4">Last touch</th>
                  <th className="py-2 pr-4">Stage</th>
                  <th className="py-2 pr-4">Score</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Company</th>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Source</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr key={l.id} className="border-b border-bg-border last:border-0">
                    <td className="py-2 pr-4 text-fg-dim">
                      {timeAgo(l.last_contacted_at || l.updated_at)}
                    </td>
                    <td className={`py-2 pr-4 text-xs ${statusColor(l.status)}`}>
                      {l.status || "new"}
                    </td>
                    <td className="py-2 pr-4 text-fg font-mono text-xs">
                      {l.score ?? "—"}
                    </td>
                    <td className="py-2 pr-4 text-fg">{truncate(l.name, 28)}</td>
                    <td className="py-2 pr-4 text-fg-muted">
                      {truncate(l.company, 28)}
                    </td>
                    <td className="py-2 pr-4 text-fg-muted font-mono text-xs">
                      {truncate(l.email, 32)}
                    </td>
                    <td className="py-2 pr-4 text-fg-dim text-xs">
                      {l.source || "—"}
                    </td>
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
