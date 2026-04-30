import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import { ChannelGauge } from "@/components/charts/ChannelGauge";
import { timeAgo, truncate } from "@/lib/fmt";
import {
  recentLeads,
  pipelineBreakdown,
  recentOutbound,
  recentInbound,
  channelUtilization,
  getActiveProfile,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const profile = await getActiveProfile();
  const tenantId = profile?.tenant_id || "";
  const [leads, pipeline, outbound, inbound, caps] = await Promise.all([
    recentLeads(tenantId, 40),
    pipelineBreakdown(tenantId),
    recentOutbound(tenantId, 20),
    recentInbound(tenantId, 20),
    channelUtilization(tenantId),
  ]);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Pipeline"
        subtitle={`${pipeline.total} leads · outbound + inbound + leads, in one view`}
      />

      <section className="grid lg:grid-cols-2 gap-6">
        <Card title="Funnel" subtitle="By stage">
          <PipelineFunnel stages={pipeline.stages} />
        </Card>
        <Card title="Today's send caps" subtitle="Gateway-enforced">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {caps.map((c) => (
              <ChannelGauge key={c.channel} {...c} />
            ))}
          </div>
        </Card>
      </section>

      <Card
        title="Recent leads"
        subtitle={`${leads.length} most recent of ${pipeline.total}`}
        noPadding
      >
        {leads.length === 0 ? (
          <div className="p-5">
            <EmptyState message="No leads. python scripts/lead_engine.py bulk-import" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-bg-border">
                <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold">
                  <th className="px-5 py-3">Last touch</th>
                  <th className="px-5 py-3">Stage</th>
                  <th className="px-5 py-3">Score</th>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Company</th>
                  <th className="px-5 py-3">Email</th>
                  <th className="px-5 py-3">Source</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr
                    key={l.id}
                    className="border-b border-bg-border last:border-0 hover:bg-bg-hover/30 transition-colors"
                  >
                    <td className="px-5 py-3 text-fg-dim text-sm">
                      {timeAgo(l.last_contacted_at || l.updated_at)}
                    </td>
                    <td className="px-5 py-3">
                      <Tag
                        tone={
                          l.status === "qualified"
                            ? "engaged"
                            : l.status === "lost"
                              ? "neutral"
                              : l.status === "won"
                                ? "engaged"
                                : "info"
                        }
                      >
                        {l.status || "new"}
                      </Tag>
                    </td>
                    <td className="px-5 py-3 text-fg font-mono text-sm">
                      {l.score ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-fg text-sm">{truncate(l.name, 28)}</td>
                    <td className="px-5 py-3 text-fg-muted text-sm">
                      {truncate(l.company, 28)}
                    </td>
                    <td className="px-5 py-3 text-fg-muted font-mono text-xs">
                      {truncate(l.email, 32)}
                    </td>
                    <td className="px-5 py-3 text-fg-dim text-xs">{l.source || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <section className="grid lg:grid-cols-2 gap-6">
        <Card title="Recent outbound" subtitle={`${outbound.length} most recent`}>
          {outbound.length === 0 ? (
            <EmptyState message="No sends through gateway yet." />
          ) : (
            <ul className="divide-y divide-bg-border">
              {outbound.map((o) => {
                const meta = (o.metadata || {}) as Record<string, unknown>;
                return (
                  <li key={o.id} className="py-3 flex items-start gap-3">
                    <Tag tone="info">{o.channel}</Tag>
                    <div className="flex-1 min-w-0">
                      <div className="text-fg text-sm truncate">
                        {truncate(o.subject || "(no subject)", 70)}
                      </div>
                      <div className="text-xs text-fg-dim mt-0.5">
                        {(meta.brand as string) || "—"} · {o.agent_source || "—"} ·{" "}
                        {timeAgo(o.created_at)}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Recent inbound" subtitle={`${inbound.length} most recent`}>
          {inbound.length === 0 ? (
            <EmptyState message="No inbound. Wire n8n via Settings → Integrations." />
          ) : (
            <ul className="divide-y divide-bg-border">
              {inbound.map((i) => {
                const meta = (i.metadata || {}) as Record<string, unknown>;
                const cls = (meta.classification || {}) as Record<string, unknown>;
                return (
                  <li key={i.id} className="py-3 flex items-start gap-3">
                    <Tag
                      tone={
                        (cls.intent as string) === "booking"
                          ? "engaged"
                          : (cls.intent as string) === "objection"
                            ? "hot"
                            : "neutral"
                      }
                    >
                      {(cls.intent as string) || "—"}
                    </Tag>
                    <div className="flex-1 min-w-0">
                      <div className="text-fg text-sm truncate">
                        {truncate(i.subject, 70)}
                      </div>
                      <div className="text-xs text-fg-dim mt-0.5">
                        {(meta.from_identity as string) || "—"} · {timeAgo(i.created_at)}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}
