import Link from "next/link";
import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import { timeAgo, truncate } from "@/lib/fmt";
import {
  recentLeads,
  pipelineBreakdown,
  recentOutbound,
  recentInbound,
  getActiveProfile,
} from "@/lib/queries";
import { safe } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

export default async function PipelinePage({
  searchParams,
}: {
  searchParams: Promise<{ show?: string }>;
}) {
  const params = await searchParams;
  const includeAll = params.show === "all";

  const profile = await safe(getActiveProfile(), null);
  const tenantId = profile?.tenant_id || "";
  const [leads, pipeline, outbound, inbound] = await Promise.all([
    safe(
      recentLeads(tenantId, 80, {
        include_archived: includeAll,
        include_no_email: includeAll,
        include_lost: includeAll,
      }),
      []
    ),
    safe(pipelineBreakdown(tenantId, includeAll), { stages: {} as Record<string, number>, total: 0, sources: {} as Record<string, number> }),
    safe(recentOutbound(tenantId, 20), []),
    safe(recentInbound(tenantId, 20), []),
  ]);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Pipeline"
        subtitle={
          includeAll
            ? `${pipeline.total} leads (showing all — including lost + archived + no-email)`
            : `${pipeline.total} active leads · clean view (lost / archived / no-email hidden)`
        }
        action={
          includeAll ? (
            <Link href="/pipeline" className="btn-secondary !text-xs !py-1.5">
              Hide noise
            </Link>
          ) : (
            <Link href="/pipeline?show=all" className="btn-secondary !text-xs !py-1.5">
              Show everything
            </Link>
          )
        }
      />

      <section>
        <Card title="Funnel" subtitle="By stage — clean view default">
          <PipelineFunnel stages={pipeline.stages} />
        </Card>
      </section>

      <Card title="Active leads" subtitle={`${leads.length} shown of ${pipeline.total}`} noPadding>
        {leads.length === 0 ? (
          <div className="p-5">
            <EmptyState message="No active leads. Run `python scripts/lead_engine.py bulk-import` from Bravo." />
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
                  <tr key={l.id} className="border-b border-bg-border last:border-0 hover:bg-bg-hover/30 transition-colors">
                    <td className="px-5 py-3 text-fg-dim text-sm">
                      {timeAgo(l.last_contacted_at || l.updated_at)}
                    </td>
                    <td className="px-5 py-3">
                      <Tag
                        tone={
                          l.status === "qualified"
                            ? "engaged"
                            : l.status === "lost" || l.status === "archived"
                              ? "neutral"
                              : l.status === "won"
                                ? "engaged"
                                : "info"
                        }
                      >
                        {l.status || "new"}
                      </Tag>
                    </td>
                    <td className="px-5 py-3 text-fg font-mono text-sm">{l.score ?? "—"}</td>
                    <td className="px-5 py-3 text-fg text-sm">{truncate(l.name, 28)}</td>
                    <td className="px-5 py-3 text-fg-muted text-sm">{truncate(l.company, 28)}</td>
                    <td className="px-5 py-3 text-fg-muted font-mono text-xs">{truncate(l.email, 32)}</td>
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
            <EmptyState message="No sends through gateway today." />
          ) : (
            <ul className="divide-y divide-bg-border">
              {outbound.map((o) => {
                const meta = (o.metadata || {}) as Record<string, unknown>;
                return (
                  <li key={o.id} className="py-1">
                    <Link
                      href={`/interactions/${o.id}`}
                      className="flex items-start gap-3 py-2 px-2 -mx-2 rounded-md hover:bg-bg-elev transition-colors"
                    >
                      <Tag tone="info">{o.channel}</Tag>
                      <div className="flex-1 min-w-0">
                        <div className="text-fg text-sm truncate">
                          {truncate(o.subject || "(no subject)", 70)}
                        </div>
                        <div className="text-xs text-fg-dim mt-0.5">
                          {(meta.brand as string) || "—"} · {o.agent_source || "—"} · {timeAgo(o.created_at)}
                        </div>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Recent inbound" subtitle={`${inbound.length} most recent`}>
          {inbound.length === 0 ? (
            <EmptyState message="No inbound today. Wire n8n via Settings → Integrations." />
          ) : (
            <ul className="divide-y divide-bg-border">
              {inbound.map((i) => {
                const meta = (i.metadata || {}) as Record<string, unknown>;
                const cls = (meta.classification || {}) as Record<string, unknown>;
                const intent = (cls.intent as string) || "—";
                const summary = (cls.summary as string) || "";
                const tone =
                  intent === "hot_lead" || intent === "frustrated"
                    ? "hot"
                    : intent === "sales" || intent === "business_opportunity" || intent === "partnership" || intent === "booking"
                      ? "engaged"
                      : intent === "strategic" || intent === "pricing_question"
                        ? "accent"
                        : intent === "ambiguous" || intent === "security"
                          ? "warm"
                          : "neutral";
                return (
                  <li key={i.id} className="py-1">
                    <Link
                      href={`/interactions/${i.id}`}
                      className="flex items-start gap-3 py-2 px-2 -mx-2 rounded-md hover:bg-bg-elev transition-colors"
                    >
                      <Tag tone={tone}>{intent}</Tag>
                      <div className="flex-1 min-w-0">
                        <div className="text-fg text-sm truncate">{truncate(i.subject, 70)}</div>
                        <div className="text-xs text-fg-dim mt-0.5 truncate">
                          {summary
                            ? truncate(summary, 100)
                            : `${(meta.from_identity as string) || "—"} · ${timeAgo(i.created_at)}`}
                        </div>
                      </div>
                    </Link>
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
