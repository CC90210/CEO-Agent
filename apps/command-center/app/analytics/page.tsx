import { Card, PageHeader, Stat, EmptyState } from "@/components/Card";
import { MRRProgressChart } from "@/components/charts/MRRProgressChart";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import {
  mrrSnapshot,
  mrrHistory,
  pipelineBreakdown,
  getActiveProfile,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const profile = await getActiveProfile();
  const tenantId = profile?.tenant_id || "";
  const [mrr, history, pipeline] = await Promise.all([
    mrrSnapshot(),
    mrrHistory(60),
    pipelineBreakdown(tenantId),
  ]);

  const totalLeads = pipeline.total;
  const won = pipeline.stages["won"] || 0;
  const lost = pipeline.stages["lost"] || 0;
  const conversion = totalLeads ? ((won / totalLeads) * 100).toFixed(1) : "—";

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title="Analytics" subtitle="The numbers that matter, charted." />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Net MRR" value={`$${Math.round(mrr.current).toLocaleString()}`} accent />
        <Stat label="Conversion" value={`${conversion}%`} hint={`${won} won / ${totalLeads} total`} />
        <Stat label="Won" value={won} />
        <Stat label="Lost" value={lost} />
      </section>

      <Card
        title="MRR · 60 days"
        subtitle={
          history[0]?.synthetic
            ? `Target $${mrr.target.toLocaleString()} · projected (no history table yet)`
            : `Target $${mrr.target.toLocaleString()}`
        }
      >
        <MRRProgressChart data={history} target={mrr.target} />
      </Card>

      <Card title="Pipeline" subtitle="Funnel by stage">
        <PipelineFunnel stages={pipeline.stages} />
      </Card>

      <Card title="Lead sources" subtitle="Where leads come from">
        {Object.keys(pipeline.sources || {}).length === 0 ? (
          <EmptyState message="No source data yet." />
        ) : (
          <ul className="space-y-2">
            {Object.entries(pipeline.sources)
              .sort((a, b) => b[1] - a[1])
              .map(([src, count]) => (
                <li key={src} className="flex items-center gap-3">
                  <div className="w-32 text-xs uppercase tracking-wider text-fg-muted font-bold">
                    {src}
                  </div>
                  <div className="flex-1 h-6 bg-bg-elev rounded-md overflow-hidden border border-bg-border">
                    <div
                      className="h-full bg-accent flex items-center px-2 text-xs font-bold text-bg"
                      style={{ width: `${(count / totalLeads) * 100}%` }}
                    >
                      {count > 0 && count}
                    </div>
                  </div>
                </li>
              ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
