import { Card, PageHeader, Tag } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth, aiServicesWithKey } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import {
  INTEGRATION_CATEGORIES,
  visibleIntegrationsForTenant,
  type IntegrationCategory,
} from "@/lib/integrations-registry";
import { resolveAgentKey } from "@/lib/agents";
import { isOperatorEmail } from "@/lib/operator-credentials";
import { getSessionUser } from "@/lib/supabase-server";
import type { IntegrationHealth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// Note: the /demo/sun public shell is gated by middleware to its own
// route prefix, never reaches /integrations. Agent-intersection rules
// below are authoritative for every caller that gets through auth.
export default async function IntegrationsPage() {
  const profile = await safe("integrations.profile", getActiveProfile(), null);

  const [dbRows, connectedAiSet, user] = await Promise.all([
    safe("integrations.health", integrationsHealth(profile?.tenant_id || null), []),
    safe("integrations.ai_keys", aiServicesWithKey(profile?.tenant_id || null), new Set<string>()),
    getSessionUser().catch(() => null),
  ]);

  const enabledAgents = (profile?.agents_enabled || []).map(resolveAgentKey);
  const isOperator = isOperatorEmail(user?.email || undefined);
  const visibleDefinitions = visibleIntegrationsForTenant(enabledAgents, { isOperator });

  const dbByService = new Map(dbRows.map((row) => [row.service, row] as const));
  const allRows: IntegrationHealth[] = visibleDefinitions.map((definition) => {
    const live = dbByService.get(definition.service);
    if (live) return live;
    return {
      id: `placeholder-${definition.service}`,
      profile_id: null,
      tenant_id: profile?.tenant_id || null,
      service: definition.service,
      status: "unconfigured" as const,
      last_ping_at: null,
      last_error: null,
      metadata: {},
      updated_at: new Date().toISOString(),
    };
  });

  const byCategory: Record<string, IntegrationHealth[]> = {};
  for (const row of allRows) {
    const definition = visibleDefinitions.find((item) => item.service === row.service);
    const category = (definition?.category || "infra") as IntegrationCategory;
    if (!byCategory[category]) byCategory[category] = [];
    byCategory[category].push(row);
  }

  const healthy = allRows.filter((row) => row.status === "healthy").length;
  const degraded = allRows.filter((row) => row.status === "degraded").length;
  const down = allRows.filter((row) => row.status === "down").length;
  const unconfigured = allRows.filter((row) => row.status === "unconfigured").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Integrations"
        subtitle={
          isOperator
            ? `${allRows.length} services in your stack — click any card to sign up or grab an API key`
            : `${allRows.length} services your enabled agents actually use. Enable more agents to unlock additional integrations.`
        }
        action={
          <div className="flex items-center gap-2">
            <Tag tone="engaged">{healthy} live</Tag>
            {degraded > 0 && <Tag tone="warm">{degraded} degraded</Tag>}
            {down > 0 && <Tag tone="hot">{down} down</Tag>}
            {unconfigured > 0 && <Tag tone="neutral">{unconfigured} not connected</Tag>}
          </div>
        }
      />

      {INTEGRATION_CATEGORIES.map(({ key, label }) => {
        const rows = byCategory[key] || [];
        if (rows.length === 0) return null;
        return (
          <Card key={key} title={label} subtitle={`${rows.length} service${rows.length === 1 ? "" : "s"}`}>
            <div className="grid sm:grid-cols-2 gap-3">
              {rows.map((row) => (
                <IntegrationDot
                  key={row.service}
                  health={row}
                  connection={{ hasCredentials: connectedAiSet.has(row.service) }}
                />
              ))}
            </div>
          </Card>
        );
      })}

      <Card
        title={isOperator ? "How pings work" : "How to read this page"}
        subtitle={
          isOperator
            ? "A green dot means the service was successfully called recently. 'Not connected' means we haven't seen activity yet — click the card to sign up."
            : "Green means connected. Gray means your agents are still waiting on that connection."
        }
      >
        <div className="text-sm text-fg-muted space-y-2 leading-relaxed">
          {!isOperator ? (
            <>
              <p>
                Each agent you enable brings the integrations it needs to do its job. Add a sales-facing agent and SMS / messaging tools appear; add a finance agent and the money tools appear.
              </p>
              <p>
                If something here drops offline, reconnect it, then come back to the dashboard and confirm the pulse check turns green again.
              </p>
            </>
          ) : (
            <>
              <p>
                Every script that touches an external service pings its row in <code className="bg-bg-elev px-1.5 py-0.5 rounded text-accent text-xs">integrations_health</code> via the shared utility:
              </p>
              <pre className="bg-bg-elev border border-bg-border rounded p-3 text-xs font-mono overflow-x-auto text-fg">{`from integration_health import ping
ping("late", status="healthy", metadata={"posts_today": 5})`}</pre>
              <p>
                <strong className="text-fg">For a new integration:</strong> add the row to <code className="text-accent text-xs">lib/integrations-registry.ts</code> with signup + API key URLs, then have your script call <code className="text-accent text-xs">ping(&quot;your-service&quot;)</code> on success.
              </p>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
