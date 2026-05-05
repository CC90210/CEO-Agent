import { Card, PageHeader, Tag } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";
import { getServiceSupabase } from "@/lib/supabase-server";
import {
  INTEGRATION_CATEGORIES,
  KNOWN_INTEGRATIONS,
  type IntegrationCategory,
} from "@/lib/integrations-registry";
import type { IntegrationHealth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// Map an AI provider name (anthropic / openai / google / openrouter) to the
// service slug in the integrations registry, so we can mark the row as
// "Configured" when the tenant has a key on file in agent_model_config.
const PROVIDER_TO_SERVICE: Record<string, string> = {
  anthropic: "anthropic",
  openai: "openai_codex",
  google: "google_ai",
  openrouter: "openrouter",
};

export default async function IntegrationsPage() {
  const profile = await getActiveProfile();
  const dbRows = await integrationsHealth(profile?.tenant_id || null);

  // Look up which AI providers have a key on file for this tenant — this
  // makes the integration cards reflect real credentials, not just pings.
  const aiServicesWithKey = new Set<string>();
  if (profile?.tenant_id) {
    const db = getServiceSupabase();
    const { data } = await db
      .from("agent_model_config")
      .select("provider, encrypted_api_key, enabled")
      .eq("tenant_id", profile.tenant_id);
    for (const row of data || []) {
      if (!row.encrypted_api_key || !row.enabled) continue;
      const svc = PROVIDER_TO_SERVICE[row.provider];
      if (svc) aiServicesWithKey.add(svc);
    }
  }

  // Merge: every registry service shows up; if no DB ping row exists, render
  // as `unconfigured` so the user sees the Connect CTA.
  const dbByService = new Map(dbRows.map((r) => [r.service, r] as const));
  const allRows: IntegrationHealth[] = KNOWN_INTEGRATIONS.map((def) => {
    const live = dbByService.get(def.service);
    if (live) return live;
    return {
      id: `placeholder-${def.service}`,
      profile_id: null,
      tenant_id: profile?.tenant_id || null,
      service: def.service,
      status: "unconfigured" as const,
      last_ping_at: null,
      last_error: null,
      metadata: {},
      updated_at: new Date().toISOString(),
    };
  });

  // Group by category from the registry
  const byCategory: Record<string, IntegrationHealth[]> = {};
  for (const h of allRows) {
    const def = KNOWN_INTEGRATIONS.find((i) => i.service === h.service);
    const cat = (def?.category || "infra") as IntegrationCategory;
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(h);
  }

  const healthy = allRows.filter((i) => i.status === "healthy").length;
  const degraded = allRows.filter((i) => i.status === "degraded").length;
  const down = allRows.filter((i) => i.status === "down").length;
  const unconfigured = allRows.filter((i) => i.status === "unconfigured").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Integrations"
        subtitle={`${allRows.length} services in your stack — click any card to sign up or grab an API key`}
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
              {rows.map((h) => (
                <IntegrationDot
                  key={h.service}
                  health={h}
                  connection={{ hasCredentials: aiServicesWithKey.has(h.service) }}
                />
              ))}
            </div>
          </Card>
        );
      })}

      <Card title="How pings work" subtitle="A green dot means the service was successfully called recently. 'Not connected' means we haven't seen activity yet — click the card to sign up.">
        <div className="text-sm text-fg-muted space-y-2 leading-relaxed">
          <p>
            Every script that touches an external service pings its row in <code className="bg-bg-elev px-1.5 py-0.5 rounded text-accent text-xs">integrations_health</code> via the shared utility:
          </p>
          <pre className="bg-bg-elev border border-bg-border rounded p-3 text-xs font-mono overflow-x-auto text-fg">{`from integration_health import ping
ping("late", status="healthy", metadata={"posts_today": 5})`}</pre>
          <p>
            <strong className="text-fg">For a new integration:</strong> add the row to <code className="text-accent text-xs">lib/integrations-registry.ts</code> with signup + API key URLs, then have your script call <code className="text-accent text-xs">ping(&quot;your-service&quot;)</code> on success.
          </p>
        </div>
      </Card>
    </div>
  );
}
