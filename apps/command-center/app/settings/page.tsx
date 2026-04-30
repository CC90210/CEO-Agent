import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import { getActiveProfile, integrationsHealth } from "@/lib/queries";
import { AGENT_REGISTRY, ALL_AGENT_KEYS } from "@/lib/agents";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.id || null);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Settings"
        subtitle="Profile, integrations, agent wiring."
      />

      {/* Profile */}
      <Card
        title="Profile"
        subtitle={
          profile
            ? `Loaded · ${profile.email}`
            : "No profile · run setup wizard"
        }
        action={profile && <Tag tone="engaged">active</Tag>}
      >
        {profile ? (
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <Field label="Full name" value={profile.full_name} />
            <Field label="Display name" value={profile.display_name || "—"} />
            <Field label="Email" value={profile.email} mono />
            <Field label="Brand" value={profile.brand} />
            <Field label="Role" value={profile.role} />
            <Field label="Primary agent" value={profile.primary_agent} />
            <Field
              label="MRR target"
              value={`$${Number(profile.mrr_target_usd).toLocaleString()}`}
            />
            <Field
              label="MRR current"
              value={`$${Number(profile.mrr_current_usd).toLocaleString()}`}
            />
            <Field
              label="Target date"
              value={profile.mrr_target_date || "—"}
            />
            <Field
              label="Agents enabled"
              value={profile.agents_enabled.join(", ")}
            />
            <Field
              label="Script version"
              value={profile.primary_script_version}
              mono
            />
            <Field
              label="Deal arch version"
              value={profile.deal_architecture_version}
              mono
            />
          </div>
        ) : (
          <EmptyState
            message="Run the OASIS setup wizard or seed a profile manually: python scripts/seed_profile.py"
          />
        )}
      </Card>

      {/* Integrations */}
      <Card
        title="Integrations"
        subtitle="Health status across every connected system"
      >
        <div className="grid sm:grid-cols-2 gap-3">
          {integrations.map((h) => (
            <IntegrationDot key={h.service} health={h} />
          ))}
        </div>
        <div className="mt-5 p-4 rounded-lg border border-status-warm/30 bg-status-warm/5 text-xs">
          <div className="flex items-center gap-2 text-status-warm font-bold uppercase tracking-wider mb-1">
            <span>n8n inbound bridge</span>
          </div>
          <p className="text-fg-muted leading-relaxed">
            If <span className="font-mono text-status-warm">n8n_inbound</span> shows{" "}
            <span className="font-mono">unconfigured</span>, paste the webhook config from
            <span className="font-mono text-accent"> docs/N8N_INBOUND_WEBHOOK.md</span>{" "}
            into your "OASIS Inbound Qualifier" workflow's HTTP Request node. The webhook URL is{" "}
            <span className="font-mono text-accent">/api/inbound/n8n</span>.
          </p>
        </div>
      </Card>

      {/* Agents wiring */}
      <Card
        title="Agents"
        subtitle="Which agents are wired to this Command Center"
      >
        <ul className="grid sm:grid-cols-2 gap-3">
          {ALL_AGENT_KEYS.map((key) => {
            const a = AGENT_REGISTRY[key];
            const enabled = profile?.agents_enabled.includes(key) || false;
            return (
              <li
                key={key}
                className={`p-4 rounded-lg border flex items-start gap-3 transition-all ${
                  enabled
                    ? "bg-bg-elev border-bg-border"
                    : "bg-bg-panel border-bg-border opacity-60"
                }`}
              >
                <div
                  className={`w-2 h-2 rounded-full mt-1.5 ${
                    enabled
                      ? "bg-status-engaged shadow-[0_0_6px_rgba(16,185,129,0.6)]"
                      : "bg-fg-faint"
                  }`}
                />
                <div className="flex-1">
                  <div className="text-fg font-bold uppercase tracking-wider text-xs">
                    {key}
                  </div>
                  <div className="text-fg text-sm mt-1">{a.role}</div>
                  <div className="mt-1 text-xs text-fg-dim font-mono">
                    {a.location}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-0.5">
        {label}
      </div>
      <div className={`text-fg ${mono ? "font-mono text-xs" : ""}`}>
        {value}
      </div>
    </div>
  );
}
