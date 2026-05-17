import Link from "next/link";
import { Bot } from "lucide-react";
import { Card, Stat, Tag } from "@/components/Card";
import { listRecords, type TenantRecord } from "@/lib/manifest/data";
import type { TenantManifest } from "@/lib/manifest/schema";
import { getServiceSupabase } from "@/lib/supabase-server";

type AgentAlertRow = {
  id: string;
  alert_type: string;
  severity: "info" | "warn" | "urgent";
  subject_type: string | null;
  subject_id: string | null;
  title: string;
  body: string | null;
  created_at: string;
};

type Props = {
  manifest: TenantManifest;
  tenantId: string | null;
  /** Per-entity sample rows for the demo mode. */
  demoRowsByEntity?: Record<string, TenantRecord[]>;
};

/**
 * Default dashboard view — manifest-aware metrics over every entity in
 * the data_model. One stat tile per entity showing count + "updated
 * recently" badge. Phase 5.1 will let `page.config` specify which
 * entities to surface and which fields to aggregate (sum / avg / max).
 *
 * Empty state is genuinely informative: zero entities means the
 * manifest hasn't been populated yet, and we link the operator to the
 * AI editor to add some.
 */
export async function ManifestDashboard({ manifest, tenantId, demoRowsByEntity }: Props) {
  const entities = manifest.data_model || [];

  if (entities.length === 0) {
    return (
      <Card title="Dashboard">
        <div className="text-sm text-fg-muted leading-relaxed">
          This manifest has no data model defined yet. Open the AI editor
          and ask: <em>&quot;Add a lead entity with name, phone, and stage fields.&quot;</em>
        </div>
      </Card>
    );
  }

  // Pull counts in parallel.
  const counts = await Promise.all(
    entities.map(async (entity) => {
      if (!tenantId) {
        const rows = demoRowsByEntity?.[entity.name] || [];
        return { entity, total: rows.length, rows };
      }
      const result = await listRecords({
        tenant_id: tenantId,
        entity: entity.name,
        limit: 1,
      }).catch(() => ({ rows: [], total: 0 }));
      return { entity, total: result.total, rows: result.rows };
    })
  );

  const enabledAgents = manifest.agents.filter((a) => a.enabled);

  // Open operator alerts — Phase 20 missing-info classifier raises these
  // on every lead the lender asks for additional docs on. Surfaced here
  // so the dashboard's first impression is "what needs my attention."
  // Skipped in preview mode (no tenant context = no alerts to pull).
  const openAlerts: AgentAlertRow[] = await (async () => {
    if (!tenantId) return [];
    try {
      const sb = getServiceSupabase();
      const { data, error } = await sb
        .from("agent_alerts")
        .select("id, alert_type, severity, subject_type, subject_id, title, body, created_at")
        .eq("tenant_id", tenantId)
        .is("resolved_at", null)
        .order("created_at", { ascending: false })
        .limit(10);
      if (error) return [];
      return (data || []) as AgentAlertRow[];
    } catch {
      return [];
    }
  })();

  return (
    <div className="space-y-4">
      {openAlerts.length > 0 && (
        <Card
          title={`${openAlerts.length} open alert${openAlerts.length === 1 ? "" : "s"}`}
          subtitle="Operator-facing notifications. Resolve from the lead/application detail page."
        >
          <ul className="space-y-2">
            {openAlerts.map((alert) => {
              const tone =
                alert.severity === "urgent"
                  ? "border-red-500/40 bg-red-500/10 text-red-200"
                  : alert.severity === "warn"
                    ? "border-amber-400/40 bg-amber-400/10 text-amber-200"
                    : "border-bg-border bg-bg-elev/40 text-fg-muted";
              const detailHref =
                alert.subject_type === "lead" && alert.subject_id
                  ? `/t/${manifest.tenant_slug}/leads/${alert.subject_id}`
                  : alert.subject_type === "application" && alert.subject_id
                    ? `/t/${manifest.tenant_slug}/applications/${alert.subject_id}`
                    : null;
              const inner = (
                <div className={`rounded-lg border px-3 py-2 text-[12.5px] ${tone}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-semibold">{alert.title}</span>
                    <span className="text-[10.5px] font-mono opacity-70 shrink-0">
                      {new Date(alert.created_at).toLocaleString()}
                    </span>
                  </div>
                  {alert.body && (
                    <div className="mt-1 text-[11.5px] opacity-90 break-words">
                      {alert.body}
                    </div>
                  )}
                </div>
              );
              return (
                <li key={alert.id}>
                  {detailHref ? (
                    <Link href={detailHref} className="block hover:opacity-90 transition-opacity">
                      {inner}
                    </Link>
                  ) : (
                    inner
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {counts.map(({ entity, total }) => (
          <Stat
            key={entity.name}
            label={entity.label}
            value={String(total)}
            hint={`${entity.fields.length} fields`}
          />
        ))}
      </section>

      {enabledAgents.length > 0 && (
        <Card
          title="Your agents"
          subtitle={
            enabledAgents.length === 1
              ? "One agent on this workspace."
              : `${enabledAgents.length} agents on this workspace — switch between them in chat.`
          }
        >
          <ul className="grid gap-2 sm:grid-cols-2">
            {enabledAgents.map((agent) => (
              <li
                key={agent.slug}
                className="flex items-center justify-between rounded-lg border border-bg-border bg-bg-elev/40 px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-accent" aria-hidden />
                  <div>
                    <div className="font-medium text-sm text-fg">{agent.display_name}</div>
                    <div className="text-[10px] uppercase tracking-wider text-fg-dim">
                      {agent.primary ? "primary" : "sub-agent"}
                    </div>
                  </div>
                </div>
                <Link
                  href={`/agent?agent=${encodeURIComponent(agent.slug)}`}
                  className="text-xs font-semibold text-accent hover:text-accent/80"
                >
                  Chat
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card
        title="Live entities"
        subtitle="Every data type defined in this tenant's manifest."
      >
        <ul className="grid gap-2 sm:grid-cols-2">
          {counts.map(({ entity, total }) => (
            <li
              key={entity.name}
              className="rounded-lg border border-bg-border bg-bg-elev/40 px-3 py-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-fg">{entity.label}</span>
                <Tag tone="neutral">{total}</Tag>
              </div>
              <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-fg-dim">
                {entity.fields.slice(0, 6).map((f) => (
                  <span
                    key={f.name}
                    className="rounded-md border border-bg-border bg-bg-deep/40 px-1.5 py-0.5 font-mono"
                  >
                    {f.name}
                    {f.required ? "*" : ""}
                  </span>
                ))}
                {entity.fields.length > 6 && (
                  <span className="text-fg-faint">+{entity.fields.length - 6}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
