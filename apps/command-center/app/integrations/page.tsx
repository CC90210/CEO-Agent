import { cookies } from "next/headers";
import { Card, PageHeader, Tag } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth, aiServicesWithKey } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import {
  DEMO_CLIENT_PROFILE_COOKIE,
  getClientCommandCenterProfileById,
} from "@/lib/client-profiles";
import {
  INTEGRATION_CATEGORIES,
  KNOWN_INTEGRATIONS,
  type IntegrationCategory,
} from "@/lib/integrations-registry";
import type { IntegrationHealth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function IntegrationsPage() {
  const profile = await safe("integrations.profile", getActiveProfile(), null);
  const demoProfile = getClientCommandCenterProfileById(
    (await cookies()).get(DEMO_CLIENT_PROFILE_COOKIE)?.value || null
  );
  const isSunProfile =
    demoProfile.id === "sun" ||
    profile?.primary_agent === "sunbiz" ||
    (profile?.agents_enabled || []).includes("sunbiz");

  const [dbRows, connectedAiSet] = await Promise.all([
    safe("integrations.health", integrationsHealth(profile?.tenant_id || null), []),
    safe("integrations.ai_keys", aiServicesWithKey(profile?.tenant_id || null), new Set<string>()),
  ]);

  const visibleDefinitions = KNOWN_INTEGRATIONS.filter((definition) =>
    !isSunProfile || definition.service === "turso" || definition.used_by?.includes("sunbiz")
  );

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
          isSunProfile
            ? `${allRows.length} core connections that keep Solara running`
            : `${allRows.length} services in your stack — click any card to sign up or grab an API key`
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
        title={isSunProfile ? "How to read this page" : "How pings work"}
        subtitle={
          isSunProfile
            ? "Green means connected. Gray means Solara is still waiting on that connection."
            : "A green dot means the service was successfully called recently. 'Not connected' means we haven't seen activity yet — click the card to sign up."
        }
      >
        <div className="text-sm text-fg-muted space-y-2 leading-relaxed">
          {isSunProfile ? (
            <>
              <p>
                Solara only needs a few visible connections to do her job well: lead intake, follow-up, and her Local Brain.
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
