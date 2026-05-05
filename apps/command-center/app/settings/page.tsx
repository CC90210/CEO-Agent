import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import {
  getActiveProfile,
  integrationsHealth,
  getTenant,
  getPlanTemplates,
} from "@/lib/queries";
import { getServiceSupabase } from "@/lib/supabase-server";
import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { ProfileEditor } from "@/components/settings/ProfileEditor";
import { PlanTemplateEditor } from "@/components/settings/PlanTemplateEditor";
import { AgentConfigEditor } from "@/components/settings/AgentConfigEditor";
import { chatAgentKeys } from "@/lib/agent-personas";

export const dynamic = "force-dynamic";

const PROVIDER_TO_SERVICE: Record<string, string> = {
  anthropic: "anthropic",
  openai: "openai_codex",
  google: "google_ai",
  openrouter: "openrouter",
};

export default async function SettingsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.tenant_id || null);
  const tenant = profile?.tenant_id ? await getTenant(profile.tenant_id) : null;
  const templates = profile ? await getPlanTemplates(profile.id) : [];
  const weekday = templates.find((t) => t.kind === "weekday") || null;
  const weekend = templates.find((t) => t.kind === "weekend") || null;

  // Same enrichment as /integrations — mark AI providers connected when a
  // key is on file for this tenant.
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
                  connection={{ hasCredentials: aiServicesWithKey.has(h.service) }}
                />
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
