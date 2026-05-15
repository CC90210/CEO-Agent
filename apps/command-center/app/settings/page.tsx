import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import {
  getActiveProfile,
  integrationsHealth,
  getTenant,
  getPlanTemplates,
  aiServicesWithKey,
  getBridgeOnline,
} from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { ProfileEditor } from "@/components/settings/ProfileEditor";
import { PlanTemplateEditor } from "@/components/settings/PlanTemplateEditor";
import { AgentConfigEditor } from "@/components/settings/AgentConfigEditor";
import { DevicesEditor } from "@/components/settings/DevicesEditor";
import { ProviderAccountsCard } from "@/components/settings/ProviderAccountsCard";
import { chatAgentKeys } from "@/lib/agent-personas";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getManifest } from "@/lib/manifest/loader";
import { visibleIntegrationsForTenant } from "@/lib/integrations-registry";
import { resolveAgentKey } from "@/lib/agents";
import { isOperatorEmail } from "@/lib/operator-credentials";
import { getSessionUser } from "@/lib/supabase-server";
import type { IntegrationHealth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await safe("settings.profile", getActiveProfile(), null);
  const [integrations, tenant, templates, connectedAiSet, user, bridgeOnline] = await Promise.all([
    safe("settings.integrations_health", integrationsHealth(profile?.tenant_id || null), []),
    profile?.tenant_id ? safe("settings.tenant", getTenant(profile.tenant_id), null) : Promise.resolve(null),
    profile ? safe("settings.plan_templates", getPlanTemplates(profile.id), []) : Promise.resolve([]),
    safe("settings.ai_keys", aiServicesWithKey(profile?.tenant_id || null), new Set<string>()),
    getSessionUser().catch(() => null),
    safe("settings.bridge_online", getBridgeOnline(profile?.tenant_id ?? null), false),
  ]);
  const weekday = templates.find((t) => t.kind === "weekday") || null;
  const weekend = templates.find((t) => t.kind === "weekend") || null;

  // Load the tenant's manifest so the Settings page can render tenant-
  // specific blocks (compliance posture, brand). Falls back gracefully if
  // the slug can't be resolved or the manifest load errors — Settings still
  // renders, the compliance card just stays hidden.
  const manifestSlug = tenant ? resolveClientProfileSlug(tenant) : null;
  const manifest = manifestSlug
    ? await safe("settings.manifest", getManifest(manifestSlug), null)
    : null;

  // Tenant-aware integration visibility. Show only what this tenant's
  // enabled agents actually need + AI providers (no used_by). Operators
  // (OASIS) see everything including platform infra (Vercel, Cloudflare,
  // GitHub, etc.). Client tenants only see what their agent mix exposes —
  // re-enable an agent later and the integrations grow back.
  const enabledAgents = (profile?.agents_enabled || []).map(resolveAgentKey);
  const isOperator = isOperatorEmail(user?.email || undefined);
  const visibleDefs = visibleIntegrationsForTenant(enabledAgents, { isOperator });
  const visibleServices = new Set(visibleDefs.map((d) => d.service));
  const visibleIntegrations = integrations.filter((h: IntegrationHealth) => visibleServices.has(h.service));

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title="Settings" subtitle="Profile, password, plan templates, integrations." />

      {!profile ? (
        <Card title="No profile loaded">
          <EmptyState message="Sign in to edit your profile." />
        </Card>
      ) : (
        <>
          <Card
            title="Profile"
            subtitle={`Signed in as ${profile.email}`}
            action={
              tenant && (
                <Tag tone={tenant.purchase_status === "active" ? "engaged" : "warm"}>
                  {tenant.plan_tier} · {tenant.purchase_status}
                </Tag>
              )
            }
          >
            <ProfileEditor profile={profile} />
          </Card>

          <Card title="Password" subtitle="Change your sign-in password">
            <ChangePasswordForm />
          </Card>

          <Card
            title="Devices"
            subtitle="Local installs paired to this dashboard. Each runs `bravo bridge start` and pings every 60s with what's installed on that machine."
          >
            <DevicesEditor />
          </Card>

          {manifest?.compliance?.tcpa && (
            <Card
              title="Compliance posture"
              subtitle="Read-only summary of the consent + send-window rules this tenant's outbound agents are bound by. Edit via the manifest editor; agents reference these rules in every draft."
              action={<Tag tone="engaged">TCPA</Tag>}
            >
              <dl className="grid sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-xs uppercase tracking-wider text-fg-dim font-bold">Send window</dt>
                  <dd className="mt-0.5 text-fg">{manifest.compliance.tcpa.send_window_local} local</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wider text-fg-dim font-bold">Weekend sends</dt>
                  <dd className="mt-0.5 text-fg">
                    {manifest.compliance.tcpa.weekend_sends ? "Allowed" : "Blocked"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wider text-fg-dim font-bold">Honor opt-outs</dt>
                  <dd className="mt-0.5 text-fg">
                    {manifest.compliance.tcpa.honor_opt_outs ? "Yes (enforced)" : "No"}
                  </dd>
                </div>
                {manifest.compliance.tcpa.opt_out_phrase && (
                  <div>
                    <dt className="text-xs uppercase tracking-wider text-fg-dim font-bold">First-touch opt-out</dt>
                    <dd className="mt-0.5 text-fg font-mono text-xs">
                      &ldquo;{manifest.compliance.tcpa.opt_out_phrase}&rdquo;
                    </dd>
                  </div>
                )}
              </dl>
            </Card>
          )}

          {/* Top-level "Connect a provider" surface. Lives ABOVE the
              per-agent Agents card so the very first thing operators see
              under Settings is the provider-account grid. The per-agent
              paste-key UX is one click away (anchor #agents). */}
          <Card
            id="providers"
            title="AI provider accounts"
            subtitle="Connect at least one model provider so your agents can think. Anthropic gets you the native tool_use loop (Claude-Code-class power); OpenRouter is one key for every model; OpenAI / Google are direct."
          >
            <ProviderAccountsCard
              connectedServices={connectedAiSet}
              bridgeOnline={bridgeOnline}
            />
          </Card>

          <Card
            id="agents"
            title="Agents"
            subtitle="Each enabled agent runs on its own provider + model + API key. Bring your own key — keys are encrypted at rest and never returned to the browser. Toggle which agents are enabled in the Profile section above."
            action={
              <Tag tone={bridgeOnline ? "engaged" : "neutral"}>
                {bridgeOnline ? "Tool access: bridge online" : "Tool access: cloud only"}
              </Tag>
            }
          >
            <AgentConfigEditor
              agentKeys={chatAgentKeys().filter((k) =>
                (profile.agents_enabled || chatAgentKeys()).includes(k)
              )}
              bridgeOnline={bridgeOnline}
            />
          </Card>

          <Card
            title="Weekday template"
            subtitle="Monday–Friday recurring schedule. Materializes nightly via cron."
          >
            <PlanTemplateEditor kind="weekday" existing={weekday} />
          </Card>

          <Card
            title="Weekend template"
            subtitle="Saturday + Sunday recurring schedule"
          >
            <PlanTemplateEditor kind="weekend" existing={weekend} />
          </Card>

          <Card
            title="Integrations"
            subtitle={
              isOperator
                ? "Health across every connected system (operator view — includes platform infra). Open the Integrations page for the full setup grid."
                : "Health across the systems your enabled agents actually use. Enable more agents to unlock additional integrations."
            }
          >
            <div className="grid sm:grid-cols-2 gap-3">
              {visibleIntegrations.map((h: IntegrationHealth) => (
                <IntegrationDot
                  key={h.service}
                  health={h}
                  connection={{ hasCredentials: connectedAiSet.has(h.service) }}
                />
              ))}
              {visibleIntegrations.length === 0 && (
                <div className="col-span-full text-sm text-fg-muted">
                  No integrations active for your current agent set. Enable an agent above to see what they need.
                </div>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
