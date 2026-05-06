import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import {
  getActiveProfile,
  integrationsHealth,
  getTenant,
  getPlanTemplates,
  aiServicesWithKey,
} from "@/lib/queries";
import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { ProfileEditor } from "@/components/settings/ProfileEditor";
import { PlanTemplateEditor } from "@/components/settings/PlanTemplateEditor";
import { AgentConfigEditor } from "@/components/settings/AgentConfigEditor";
import { DevicesEditor } from "@/components/settings/DevicesEditor";
import { chatAgentKeys } from "@/lib/agent-personas";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.tenant_id || null);
  const tenant = profile?.tenant_id ? await getTenant(profile.tenant_id) : null;
  const templates = profile ? await getPlanTemplates(profile.id) : [];
  const weekday = templates.find((t) => t.kind === "weekday") || null;
  const weekend = templates.find((t) => t.kind === "weekend") || null;
  const connectedAiSet = await aiServicesWithKey(profile?.tenant_id || null);

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
