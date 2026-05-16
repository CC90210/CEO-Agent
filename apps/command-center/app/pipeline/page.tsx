import Link from "next/link";
import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import { timeAgo, truncate } from "@/lib/fmt";
import {
  pipelineBreakdown,
  recentOutbound,
  recentInbound,
  getActiveProfile,
} from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { ManifestKanban } from "@/components/manifest/ManifestKanban";
import { OASIS_SEED } from "@/lib/manifest/seeds";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const profile = await safe("pipeline.profile", getActiveProfile(), null);
  const tenantId = profile?.tenant_id || "";
  // Phase 4: kanban-first pipeline. The legacy ?show=all toggle is gone —
  // the kanban exposes lost/won as their own columns instead of hiding
  // them. Funnel chart matches the kanban's stage breakdown so counts
  // can't disagree across the two surfaces.
  const [pipeline, outbound, inbound] = await Promise.all([
    safe("pipeline.breakdown", pipelineBreakdown(tenantId, true), { stages: {} as Record<string, number>, total: 0, sources: {} as Record<string, number> }),
    safe("pipeline.recent_outbound", recentOutbound(tenantId, 20), []),
    safe("pipeline.recent_inbound", recentInbound(tenantId, 20), []),
  ]);

  // Phase 4: OASIS Pipeline becomes a full CRM. Source of stages + card
  // fields is OASIS_SEED.data_model.lead, which the same ManifestKanban
  // SunBiz uses already understands. `linkBase="/pipeline"` swaps the
  // default `/t/oasis/pipeline/<id>` URL shape (which 404s — OASIS isn't
  // a tenant_manifests row) for `/pipeline/<id>` which routes to the
  // empire-side detail + new pages built alongside this.
  const leadEntity = OASIS_SEED.data_model?.find((e) => e.name === "lead");

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Pipeline"
        subtitle={`${pipeline.total} lead${pipeline.total === 1 ? "" : "s"} across the funnel`}
      />

      <section>
        <Card title="Funnel" subtitle="By stage">
          <PipelineFunnel stages={pipeline.stages} />
        </Card>
      </section>

      {leadEntity ? (
        <ManifestKanban
          tenantSlug="oasis"
          tenantId={tenantId || null}
          entity={leadEntity}
          page={{
            path: "pipeline",
            label: "Pipeline",
            kind: "kanban",
            entity: "lead",
            config: { group_by: "stage" },
          }}
          linkBase="/pipeline"
        />
      ) : (
        <Card>
          <EmptyState message="OASIS lead entity not defined in the manifest. Open the AI editor at /t/oasis/editor to add it." />
        </Card>
      )}

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
