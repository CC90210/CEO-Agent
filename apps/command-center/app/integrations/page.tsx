import { Card, PageHeader } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function IntegrationsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.id || null);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Integrations"
        subtitle="Health status across every connected system. Background workers ping these endpoints; this page reads the freshest snapshot."
      />

      <Card title="Connected services" subtitle={`${integrations.length} known services`}>
        <div className="grid sm:grid-cols-2 gap-3">
          {integrations.map((h) => (
            <IntegrationDot key={h.service} health={h} />
          ))}
        </div>
      </Card>

      <Card title="n8n inbound webhook" subtitle="The bridge that makes inbound flow into Pipeline">
        <div className="space-y-4 text-sm">
          <p className="text-fg leading-relaxed">
            The OASIS Inbound Qualifier workflow in n8n is the source of truth for inbound classification (intent, sentiment, priority).
            It posts every classified email to{" "}
            <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
              POST /api/inbound/n8n
            </code>
            , which calls the{" "}
            <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
              record_inbound_from_n8n_v2
            </code>{" "}
            RPC and bumps this dashboard's green dot.
          </p>
          <p className="text-fg-muted leading-relaxed">
            Setup details and the copy-paste node config are in{" "}
            <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
              docs/N8N_INBOUND_WEBHOOK.md
            </code>
            . Generate a fresh secret with{" "}
            <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
              python scripts/n8n_webhook_secret.py issue
            </code>
            .
          </p>
        </div>
      </Card>
    </div>
  );
}
