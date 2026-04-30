import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import {
  getActiveProfile,
  integrationsHealth,
  getTenant,
  getPlanTemplates,
} from "@/lib/queries";
import { AGENT_REGISTRY, ALL_AGENT_KEYS } from "@/lib/agents";
import { ChangePasswordForm } from "@/components/ChangePasswordForm";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await getActiveProfile();
  const integrations = await integrationsHealth(profile?.tenant_id || null);
  const tenant = profile?.tenant_id ? await getTenant(profile.tenant_id) : null;
  const templates = profile ? await getPlanTemplates(profile.id) : [];

  const weekday = templates.find((t) => t.kind === "weekday");
  const weekend = templates.find((t) => t.kind === "weekend");

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title="Settings" subtitle="Profile, account, integrations, agents, and your daily plan templates." />

      <Card
        title="Account"
        subtitle={profile ? `Signed in as ${profile.email}` : "Not signed in"}
        action={
          tenant && (
            <Tag tone={tenant.purchase_status === "active" ? "engaged" : "warm"}>
              {tenant.plan_tier} · {tenant.purchase_status}
            </Tag>
          )
        }
      >
        {profile ? (
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <Field label="Full name" value={profile.full_name} />
            <Field label="Display name" value={profile.display_name || "—"} />
            <Field label="Email" value={profile.email} mono />
            <Field label="Brand" value={profile.brand} />
            <Field label="Tenant" value={tenant?.slug || "—"} mono />
            <Field label="Role" value={profile.role} />
            <Field label="Primary agent" value={profile.primary_agent} />
            <Field label="Language" value={profile.preferred_language} />
            <Field
              label="MRR target"
              value={`$${Number(profile.mrr_target_usd).toLocaleString()}`}
            />
            <Field
              label="MRR current"
              value={`$${Number(profile.mrr_current_usd).toLocaleString()}`}
            />
            <Field label="Target date" value={profile.mrr_target_date || "—"} />
            <Field label="Prospect focus" value={profile.prospect_focus.join(", ") || "—"} />
          </div>
        ) : (
          <EmptyState message="Profile missing." />
        )}
      </Card>

      <Card title="Password" subtitle="Update your sign-in password">
        <ChangePasswordForm />
      </Card>

      <Card
        title="Plan templates"
        subtitle="Weekday + weekend recurring schedules. Edit once, applies to every matching day."
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <TemplateCard kind="weekday" template={weekday || null} />
          <TemplateCard kind="weekend" template={weekend || null} />
        </div>
      </Card>

      <Card
        title="Integrations"
        subtitle="Health status across every connected system"
      >
        <div className="grid sm:grid-cols-2 gap-3">
          {integrations.map((h) => (
            <IntegrationDot key={h.service} health={h} />
          ))}
        </div>
      </Card>

      <Card title="Agents" subtitle="Which agents are wired to your Command Center">
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
                  <div className="mt-1 text-xs text-fg-dim font-mono">{a.location}</div>
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
      <div className={`text-fg ${mono ? "font-mono text-xs" : ""}`}>{value}</div>
    </div>
  );
}

function TemplateCard({
  kind,
  template,
}: {
  kind: "weekday" | "weekend";
  template: import("@/lib/supabase").PlanTemplate | null;
}) {
  return (
    <div className="rounded-lg border border-bg-border bg-bg-elev p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-accent font-bold uppercase tracking-wider text-xs">{kind}</span>
        <Tag tone={template ? "engaged" : "neutral"}>
          {template ? `${template.schedule.length} blocks` : "not set"}
        </Tag>
      </div>
      {template ? (
        <>
          <div className="text-fg text-sm">{template.mission || "—"}</div>
          <div className="text-fg-muted text-xs mt-2">
            Targets: {template.target_calls} calls · {template.target_emails} emails ·{" "}
            {template.target_bookings} bookings
          </div>
        </>
      ) : (
        <div className="text-fg-muted text-sm">
          No {kind} template. Create one with{" "}
          <code className="text-accent font-mono text-xs">
            python scripts/seed_plan_template.py --kind {kind}
          </code>
          .
        </div>
      )}
    </div>
  );
}
