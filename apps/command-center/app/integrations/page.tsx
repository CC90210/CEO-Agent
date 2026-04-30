import { Card, PageHeader } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function IntegrationsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.tenant_id || null);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Integrations"
        subtitle="Health status across every connected system. Background workers ping these endpoints; this page reads the freshest snapshot."
      />

      <Card
        title="Connected services"
        subtitle={`${integrations.length} known services`}
      >
        <div className="grid sm:grid-cols-2 gap-3">
          {integrations.map((h) => (
            <IntegrationDot key={h.service} health={h} />
          ))}
        </div>
      </Card>

      <Card
        title="n8n inbound webhook"
        subtitle="The bridge that makes inbound flow into Pipeline"
      >
        <div className="space-y-4 text-sm">
          <p className="text-fg leading-relaxed">
            The OASIS Inbound Qualifier workflow in n8n is the source of truth for
            inbound classification (intent, sentiment, priority). Two paths exist:
          </p>
          <ul className="space-y-2 text-fg-muted leading-relaxed pl-5 list-disc">
            <li>
              <strong className="text-fg">Python scheduler (default)</strong> —{" "}
              <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
                email_engine.py check-inbox
              </code>{" "}
              polls every 5 minutes, classifies, and pings this dashboard
              automatically. Already wired.
            </li>
            <li>
              <strong className="text-fg">n8n HTTP webhook (optional)</strong> — POST
              to{" "}
              <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
                /api/inbound/n8n
              </code>
              . See{" "}
              <code className="bg-bg-elev border border-bg-border px-2 py-0.5 rounded text-accent font-mono text-xs">
                docs/N8N_INBOUND_WEBHOOK.md
              </code>{" "}
              for the 5-min copy-paste setup.
            </li>
          </ul>
        </div>
      </Card>
    </div>
  );
}
