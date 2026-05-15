import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import {
  getActiveProfile,
  integrationsHealth,
  getTenant,
  getPlanTemplates,
  aiServicesWithKey,
} from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { ProfileEditor } from "@/components/settings/ProfileEditor";
import { PlanTemplateEditor } from "@/components/settings/PlanTemplateEditor";
import { AgentConfigEditor } from "@/components/settings/AgentConfigEditor";
import { DevicesEditor } from "@/components/settings/DevicesEditor";
import { chatAgentKeys } from "@/lib/agent-personas";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getManifest } from "@/lib/manifest/loader";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await safe("settings.profile", getActiveProfile(), null);
  const [integrations, tenant, templates, connectedAiSet] = await Promise.all([
    safe("settings.integrations_health", integrationsHealth(profile?.tenant_id || null), []),
    profile?.tenant_id ? safe("settings.tenant", getTenant(profile.tenant_id), null) : Promise.resolve(null),
    profile ? safe("settings.plan_templates", getPlanTemplates(profile.id), []) : Promise.resolve([]),
    safe("settings.ai_keys", aiServicesWithKey(profile?.tenant_id || null), new Set<string>()),
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

          <Card
            title="Agents"
            subtitle="Each enabled agent runs on its own provider + model + API key. Bring your own key — keys are encrypted at rest and never returned to the browser. Toggle which agents are enabled in the Profile section above."
          >
            <AgentConfigEditor
              agentKeys={chatAgentKeys().filter((k) =>
                (profile.agents_enabled || chatAgentKeys()).includes(k)
              )}
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

          <Card title="Integrations" subtitle="Health across every connected system. Open the Integrations page for the full setup grid.">
            <div className="grid sm:grid-cols-2 gap-3">
              {integrations.map((h) => (
                <IntegrationDot
                  key={h.service}
                  health={h}
                  connection={{ hasCredentials: connectedAiSet.has(h.service) }}
                />
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
