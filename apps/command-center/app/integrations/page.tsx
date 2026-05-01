import { Card, PageHeader, Tag } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";
import { INTEGRATION_CATEGORIES, KNOWN_INTEGRATIONS, type IntegrationCategory } from "@/lib/integrations-registry";

export const dynamic = "force-dynamic";

export default async function IntegrationsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.tenant_id || null);

  // Group by category from the registry
  const byCategory: Record<string, typeof integrations> = {};
  for (const h of integrations) {
    const def = KNOWN_INTEGRATIONS.find((i) => i.service === h.service);
    const cat = (def?.category || "infra") as IntegrationCategory;
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(h);
  }

  const healthy = integrations.filter((i) => i.status === "healthy").length;
  const degraded = integrations.filter((i) => i.status === "degraded").length;
  const down = integrations.filter((i) => i.status === "down").length;
  const unconfigured = integrations.filter((i) => i.status === "unconfigured").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Integrations"
        subtitle={`${integrations.length} services in your stack — pings come from background workers and the dashboard reads the freshest snapshot`}
        action={
          <div className="flex items-center gap-2">
            <Tag tone="engaged">{healthy} live</Tag>
            {degraded > 0 && <Tag tone="warm">{degraded} degraded</Tag>}
            {down > 0 && <Tag tone="hot">{down} down</Tag>}
            {unconfigured > 0 && <Tag tone="neutral">{unconfigured} idle</Tag>}
          </div>
        }
      />

      {INTEGRATION_CATEGORIES.map(({ key, label }) => {
        const rows = byCategory[key] || [];
        if (rows.length === 0) return null;
        return (
          <Card key={key} title={label} subtitle={`${rows.length} service${rows.length === 1 ? "" : "s"}`}>
            <div className="grid sm:grid-cols-2 gap-3">
              {rows.map((h) => (
                <IntegrationDot key={h.service} health={h} />
              ))}
            </div>
          </Card>
        );
      })}

      <Card title="How pings work" subtitle="If a service shows 'idle' / 'unconfigured', nothing is pinging it yet">
        <div className="text-sm text-fg-muted space-y-2 leading-relaxed">
          <p>
            Every script that touches an external service can ping its row in <code className="bg-bg-elev px-1.5 py-0.5 rounded text-accent text-xs">integrations_health</code> via the shared utility:
          </p>
          <pre className="bg-bg-elev border border-bg-border rounded p-3 text-xs font-mono overflow-x-auto text-fg">{`from integration_health import ping
ping("late", status="healthy", metadata={"posts_today": 5})`}</pre>
          <p>
            Already wired: <code className="text-accent text-xs">send_gateway</code> (gmail), <code className="text-accent text-xs">stripe_tool.cmd_balance</code> (stripe), <code className="text-accent text-xs">email_engine.check_inbox</code> (n8n_inbound).
          </p>
          <p>
            <strong className="text-fg">For a new integration:</strong> add the row to <code className="text-accent text-xs">lib/integrations-registry.ts</code>, then have the script that uses it call <code className="text-accent text-xs">ping(&quot;your-service&quot;)</code> on success.
          </p>
        </div>
      </Card>
    </div>
  );
}
